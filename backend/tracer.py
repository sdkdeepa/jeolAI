"""Structured execution tracing for model, tool, policy, and guardrail steps."""

from __future__ import annotations

import json
from typing import Any

from backend.budget import estimate_cost
from backend.db import get_connection


def _safe_details(details: dict[str, Any] | None) -> str | None:
    if details is None:
        return None
    return json.dumps(details, default=str, ensure_ascii=False)


def record_model_call(
    session_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    details: dict[str, Any] | None = None,
) -> None:
    cost = estimate_cost(model, input_tokens, output_tokens)
    _insert(
        session_id=session_id,
        step_type="model_call",
        label=f"Gemini model call: {model}",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        latency_ms=latency_ms,
        details=details,
    )


def record_tool_decision(
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> None:
    _insert(
        session_id=session_id,
        step_type="tool_decision",
        label=f"Gemini selected tool: {tool_name}",
        model=None,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        latency_ms=0.0,
        details={"tool": tool_name, "arguments": arguments},
    )


def record_tool_call(
    session_id: str,
    tool_name: str,
    latency_ms: float,
    tool_input: dict[str, Any] | None = None,
    tool_output: dict[str, Any] | None = None,
) -> None:
    _insert(
        session_id=session_id,
        step_type="tool_call",
        label=f"Executed tool: {tool_name}",
        model=None,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        latency_ms=latency_ms,
        details={"input": tool_input or {}, "output": tool_output or {}},
    )


def record_event(
    session_id: str,
    label: str,
    details: dict[str, Any] | None = None,
    step_type: str = "event",
) -> None:
    _insert(
        session_id=session_id,
        step_type=step_type,
        label=label,
        model=None,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        latency_ms=0.0,
        details=details,
    )


def clear_trace(session_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM trace_steps WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def _insert(
    session_id: str,
    step_type: str,
    label: str,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: float,
    details: dict[str, Any] | None,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO trace_steps
            (session_id, step_type, label, model, input_tokens,
             output_tokens, cost_usd, latency_ms, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            step_type,
            label,
            model,
            input_tokens,
            output_tokens,
            round(cost_usd, 6),
            round(latency_ms, 1),
            _safe_details(details),
        ),
    )
    conn.commit()
    conn.close()


def get_trace(session_id: str) -> list[dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, step_type, label, model, input_tokens, output_tokens,
               cost_usd, latency_ms, details_json, created_at
        FROM trace_steps
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    )
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        raw_details = item.pop("details_json", None)
        item["details"] = json.loads(raw_details) if raw_details else None
        rows.append(item)
    conn.close()
    return rows
