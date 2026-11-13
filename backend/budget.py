"""Session-level budget policy for JeolAI.

Cost values are estimates based on configurable per-million-token rates. Set
rates in the environment to match the current pricing for the selected Gemini
models and deployment region.

Output rates apply to response tokens AND thinking tokens: Google bills
thinking tokens at the output rate. gemini_client._usage() therefore reports
output_tokens = candidates_token_count + thoughts_token_count.
"""

from __future__ import annotations

from dataclasses import dataclass

# Importing config loads .env before any constant below is evaluated.
from backend import config
from backend.db import get_connection

# The defaults below are only used when a variable is absent (for example in
# CI, which has no .env). They mirror the documented .env so a missing file
# cannot silently switch model families or pricing. /health reports any
# setting that fell back to a default.
DEFAULT_MODEL = config.get_str("GEMINI_DEFAULT_MODEL", "gemini-3.5-flash-lite")
ESCALATION_MODEL = config.get_str("GEMINI_ESCALATION_MODEL", "gemini-3.5-flash")

# Defaults match Google Cloud Vertex AI Standard PayGo, global endpoint, as
# published in Nov 2026. Non-global (regional) endpoints are priced ~10% higher.
MODEL_RATES = {
    DEFAULT_MODEL: {
        "input": config.get_float("GEMINI_DEFAULT_INPUT_USD_PER_M", 0.30),
        "output": config.get_float("GEMINI_DEFAULT_OUTPUT_USD_PER_M", 2.50),
    },
    ESCALATION_MODEL: {
        "input": config.get_float("GEMINI_ESCALATION_INPUT_USD_PER_M", 1.50),
        "output": config.get_float("GEMINI_ESCALATION_OUTPUT_USD_PER_M", 9.00),
    },
}

SESSION_BUDGET_USD = config.get_float("SESSION_BUDGET_USD", 0.10)
WARN_THRESHOLD = config.get_float("WARN_THRESHOLD", 0.70)
HARD_THRESHOLD = config.get_float("HARD_THRESHOLD", 0.95)
SEARCH_RESULT_CAP = config.get_int("SEARCH_RESULT_CAP", 3)


@dataclass
class BudgetStatus:
    session_id: str
    dollars_spent: float
    budget_cap: float
    percent_used: float
    tier: str


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = MODEL_RATES.get(model)
    if rates is None:
        raise ValueError(f"No pricing configuration found for model: {model}")
    return (
        (input_tokens / 1_000_000) * rates["input"]
        + (output_tokens / 1_000_000) * rates["output"]
    )


def _get_or_create_session(session_id: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO sessions (session_id) VALUES (?)", (session_id,))
        conn.commit()
    conn.close()


def get_status(session_id: str) -> BudgetStatus:
    _get_or_create_session(session_id)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT dollars_spent FROM sessions WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()

    spent = row["dollars_spent"] if row else 0.0
    percent_used = min(spent / SESSION_BUDGET_USD, 1.0)

    if percent_used >= HARD_THRESHOLD:
        tier = "gated"
    elif percent_used >= WARN_THRESHOLD:
        tier = "downgraded"
    else:
        tier = "normal"

    return BudgetStatus(
        session_id=session_id,
        dollars_spent=round(spent, 6),
        budget_cap=SESSION_BUDGET_USD,
        percent_used=round(percent_used * 100, 1),
        tier=tier,
    )


def choose_model(session_id: str, wants_escalation: bool) -> str:
    status = get_status(session_id)
    if wants_escalation and status.tier == "normal":
        return ESCALATION_MODEL
    return DEFAULT_MODEL


def search_result_limit(session_id: str) -> int | None:
    status = get_status(session_id)
    return None if status.tier == "normal" else SEARCH_RESULT_CAP


def checkout_requires_approval(session_id: str) -> bool:
    return get_status(session_id).tier == "gated"


def set_spend_for_demo(session_id: str, dollars: float) -> BudgetStatus:
    _get_or_create_session(session_id)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET dollars_spent = ? WHERE session_id = ?",
        (max(dollars, 0.0), session_id),
    )
    conn.commit()
    conn.close()
    return get_status(session_id)


def record_usage(
    session_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> BudgetStatus:
    _get_or_create_session(session_id)
    cost = estimate_cost(model, input_tokens, output_tokens)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE sessions
        SET input_tokens = input_tokens + ?,
            output_tokens = output_tokens + ?,
            dollars_spent = dollars_spent + ?
        WHERE session_id = ?
        """,
        (input_tokens, output_tokens, cost, session_id),
    )
    conn.commit()
    conn.close()

    return get_status(session_id)
