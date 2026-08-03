"""FastAPI application for JeolAI's observable shopping assistant."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.genai import types
from pydantic import BaseModel, Field

from backend import budget, db, tracer
from backend.guardrails import evaluate_request
from backend.gemini_client import resume_after_approval, run_turn, user_message

app = FastAPI(title="JeolAI: Shop Smart, Spend Smarter")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Workshop-only in-memory session state. A production implementation should
# use an authenticated durable session store with retention controls.
_conversations: dict[str, list[types.Content]] = {}
_pending_approvals: dict[str, dict[str, Any]] = {}
_chat_history: dict[str, list[dict[str, Any]]] = {}
_session_started_at: dict[str, float] = {}


@app.on_event("startup")
def startup() -> None:
    db.init_db()


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)
    wants_escalation: bool = False


def _append_history(session_id: str, role: str, message: str, **metadata: Any) -> None:
    _chat_history.setdefault(session_id, []).append(
        {
            "role": role,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **metadata,
        }
    )


def _trace_metrics(session_id: str) -> dict[str, Any]:
    steps = tracer.get_trace(session_id)
    model_steps = [step for step in steps if step["step_type"] == "model_call"]
    tool_steps = [step for step in steps if step["step_type"] == "tool_call"]
    return {
        "input_tokens": sum(step["input_tokens"] for step in model_steps),
        "output_tokens": sum(step["output_tokens"] for step in model_steps),
        "total_tokens": sum(
            step["input_tokens"] + step["output_tokens"] for step in model_steps
        ),
        "estimated_cost_usd": round(sum(step["cost_usd"] for step in steps), 6),
        "total_latency_ms": round(sum(step["latency_ms"] for step in steps), 1),
        "model_calls": len(model_steps),
        "tool_calls": len(tool_steps),
        "models": sorted({step["model"] for step in model_steps if step["model"]}),
        "tools": sorted(
            {
                (step.get("details") or {}).get("input") and step["label"].replace("Executed tool: ", "")
                or step["label"].replace("Executed tool: ", "")
                for step in tool_steps
            }
        ),
    }


@app.post("/chat")
def chat(req: ChatRequest):
    session_id = req.session_id
    request_start = time.perf_counter()
    _session_started_at.setdefault(session_id, time.time())

    _append_history(session_id, "user", req.message)
    tracer.record_event(
        session_id,
        "Request received",
        details={"message": req.message},
        step_type="request",
    )

    guard = evaluate_request(req.message)
    tracer.record_event(
        session_id,
        "Domain guard passed" if guard.allowed else "Domain guard blocked request",
        details={
            "allowed": guard.allowed,
            "reason": guard.reason,
            "matched_signal": guard.matched_signal,
        },
        step_type="guardrail",
    )

    if not guard.allowed:
        reply = "I don’t know. I can only help with shopping, products, promotions, inventory, carts, and checkout."
        tracer.record_event(
            session_id,
            "Request stopped before model invocation",
            details={"model_called": False, "cost_usd": 0, "tokens": 0},
            step_type="blocked",
        )
        tracer.record_event(
            session_id,
            "Response returned",
            details={"reply": reply},
            step_type="response",
        )
        _append_history(session_id, "assistant", reply, domain_allowed=False)
        return {
            "reply": reply,
            "requires_approval": False,
            "domain_allowed": False,
            "model_used": None,
            "tokens_this_turn": {"input": 0, "output": 0},
            "turn_latency_ms": round((time.perf_counter() - request_start) * 1000, 1),
            "budget": budget.get_status(session_id).__dict__,
        }

    status_before = budget.get_status(session_id)
    tracer.record_event(
        session_id,
        "Budget policy evaluated",
        details=status_before.__dict__,
        step_type="policy",
    )

    model = budget.choose_model(session_id, wants_escalation=req.wants_escalation)
    tracer.record_event(
        session_id,
        f"Model selected: {model}",
        details={
            "model": model,
            "requested_escalation": req.wants_escalation,
            "budget_tier": status_before.tier,
        },
        step_type="model_selection",
    )

    history = _conversations.setdefault(session_id, [])
    history.append(user_message(req.message))
    result = run_turn(session_id, model, history)
    _conversations[session_id] = result["messages"]

    status = budget.record_usage(
        session_id,
        model,
        result["input_tokens"],
        result["output_tokens"],
    )

    if result["status"] == "needs_approval":
        _pending_approvals[session_id] = {
            "function_name": result["pending_function_name"],
            "model": model,
        }
        reply = (
            "This checkout needs human approval because the session reached "
            "its budget threshold. Approve or deny it to continue."
        )
        requires_approval = True
    else:
        reply = result["text"]
        requires_approval = False

    turn_latency_ms = round((time.perf_counter() - request_start) * 1000, 1)
    tracer.record_event(
        session_id,
        "Response returned",
        details={"reply": reply, "end_to_end_latency_ms": turn_latency_ms},
        step_type="response",
    )
    _append_history(
        session_id,
        "assistant",
        reply,
        domain_allowed=True,
        model=model,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        latency_ms=turn_latency_ms,
    )

    return {
        "reply": reply,
        "requires_approval": requires_approval,
        "domain_allowed": True,
        "model_used": model,
        "tokens_this_turn": {
            "input": result["input_tokens"],
            "output": result["output_tokens"],
        },
        "turn_latency_ms": turn_latency_ms,
        "budget": status.__dict__,
    }


class ApproveRequest(BaseModel):
    session_id: str
    approved: bool


@app.post("/approve")
def approve(req: ApproveRequest):
    pending = _pending_approvals.pop(req.session_id, None)
    if pending is None:
        return {"error": "No pending approval for this session"}

    started = time.perf_counter()
    messages = _conversations.get(req.session_id, [])
    result = resume_after_approval(
        req.session_id,
        pending["model"],
        messages,
        pending["function_name"],
        req.approved,
    )
    _conversations[req.session_id] = result["messages"]
    status = budget.record_usage(
        req.session_id,
        pending["model"],
        result["input_tokens"],
        result["output_tokens"],
    )
    latency = round((time.perf_counter() - started) * 1000, 1)
    _append_history(req.session_id, "assistant", result["text"], latency_ms=latency)
    return {
        "reply": result["text"],
        "requires_approval": result["status"] == "needs_approval",
        "model_used": pending["model"],
        "tokens_this_turn": {
            "input": result["input_tokens"],
            "output": result["output_tokens"],
        },
        "turn_latency_ms": latency,
        "budget": status.__dict__,
    }


@app.get("/budget-status/{session_id}")
def budget_status(session_id: str):
    return budget.get_status(session_id).__dict__


@app.get("/trace/{session_id}")
def trace(session_id: str):
    steps = tracer.get_trace(session_id)
    return {
        "session_id": session_id,
        "steps": steps,
        "metrics": _trace_metrics(session_id),
        "budget": budget.get_status(session_id).__dict__,
    }


class EndChatRequest(BaseModel):
    session_id: str


@app.post("/end-chat")
def end_chat(req: EndChatRequest):
    session_id = req.session_id
    metrics = _trace_metrics(session_id)
    status = budget.get_status(session_id)
    history = _chat_history.get(session_id, [])
    started_at = _session_started_at.get(session_id, time.time())
    duration_seconds = round(max(0, time.time() - started_at), 1)
    user_messages = [item for item in history if item["role"] == "user"]
    assistant_messages = [item for item in history if item["role"] == "assistant"]

    summary = {
        "session_id": session_id,
        "duration_seconds": duration_seconds,
        "user_messages": len(user_messages),
        "assistant_messages": len(assistant_messages),
        "total_messages": len(history),
        **metrics,
        "current_budget_tier": status.tier,
        "budget_cap_usd": status.budget_cap,
        "budget_consumed_percent": status.percent_used,
        "transcript": history,
    }
    tracer.record_event(
        session_id,
        "Session summary generated",
        details={key: value for key, value in summary.items() if key != "transcript"},
        step_type="session_end",
    )
    return summary


@app.delete("/session/{session_id}")
def reset_session(session_id: str):
    _conversations.pop(session_id, None)
    _pending_approvals.pop(session_id, None)
    _chat_history.pop(session_id, None)
    _session_started_at.pop(session_id, None)
    tracer.clear_trace(session_id)
    budget.set_spend_for_demo(session_id, 0.0)
    return {"reset": True, "session_id": session_id}


class DebugSpendRequest(BaseModel):
    session_id: str
    dollars: float


@app.post("/debug/set-spend")
def debug_set_spend(req: DebugSpendRequest):
    return budget.set_spend_for_demo(req.session_id, req.dollars).__dict__


@app.get("/health")
def health():
    return {
        "status": "ok",
        "provider": "Vertex AI",
        "models": [budget.DEFAULT_MODEL, budget.ESCALATION_MODEL],
    }
