"""Vertex AI Gemini client with observable, multi-step commerce orchestration."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

# config must be imported before reading any environment variable.
from backend import budget, config, tracer  # noqa: F401
from backend.tools import execute_tool

logger = logging.getLogger("jeolai.gemini")

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = config.get_str("GOOGLE_CLOUD_LOCATION", "us-central1")

# Number of times an empty model turn (no text, no function call) is retried
# before the backend falls back to a deterministic response.
EMPTY_RESPONSE_RETRIES = 1

MAX_AGENT_STEPS = 8

if not PROJECT_ID:
    raise RuntimeError("GOOGLE_CLOUD_PROJECT is required in .env")

client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION,
    http_options=types.HttpOptions(api_version="v1"),
)


SYSTEM_PROMPT = """
You are JeolAI, a budget-aware shopping agent for an outdoor ecommerce store.

Use tools for every factual commerce claim. Never invent products, prices,
stock, promotions, cart contents, cart totals, discounts, or orders.

Operating rules:

1. Product discovery, comparisons, recommendations, and outfit requests require
   search_products. Use its price, size, gender, category, subcategory, and
   use_case filters instead of claiming a filter is unsupported.

2. For an outfit, kit, bundle, or packing-list request, create a multi-item plan.
   Use the pre-fetched orchestration results when supplied. Select a practical
   combination whose total stays within the customer's product budget. Explain
   tradeoffs and show the total.

3. Resolve informal names naturally. "Summit GTX" may match "Summit GTX Hiking
   Boots". Tools perform fuzzy resolution, so call them rather than refusing.

4. Use check_inventory for stock or size availability.

5. Use get_promotions for discount questions. Pass product_name when known.

6. Use update_cart to add or remove items. Exact spelling is not required.
   If update_cart returns status=needs_input, ask the user for the missing field
   using the available options.

   Preserve the matched product context so a reply such as "Size 10" retries
   update_cart for that product with size="10".

   Never claim an item was added when the tool rejected it.

7. Use get_cart whenever the user asks what is in the cart and before checkout.

   Cart items may include selected_size. When selected_size is present, mention
   the selected size.

   The cart response includes subtotal_usd. Use that exact value when describing
   the current cart total.

8. NEVER calculate, infer, add, subtract, estimate, or recompute cart totals,
   line totals, discounts, or checkout totals yourself.

   Numeric commerce values must come from deterministic tool output.

   If update_cart or get_cart returns subtotal_usd, repeat that value exactly.
   If checkout returns subtotal_usd, discount_usd, or total_usd, repeat those
   values exactly.

9. Call checkout only after explicit user confirmation.

10. Keep the response concise, useful, and grounded in tool output.
""".strip()


FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="catalog_facets",
        description="List the categories and subcategories available in the store.",
        parameters_json_schema={
            "type": "object",
            "properties": {},
        },
    ),
    types.FunctionDeclaration(
        name="search_products",
        description=(
            "Search and filter the product catalog. Supports price, size, "
            "brand, gender, category, and use case."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "category": {"type": "string"},
                "subcategory": {"type": "string"},
                "brand": {"type": "string"},
                "gender": {"type": "string"},
                "min_price": {"type": "number"},
                "max_price": {"type": "number"},
                "size": {"type": "string"},
                "use_case": {"type": "string"},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 12,
                },
            },
        },
    ),
    types.FunctionDeclaration(
        name="check_inventory",
        description=(
            "Check stock and optional size availability for a product. "
            "Near-match product names are supported."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "size": {"type": "string"},
            },
            "required": ["product_name"],
        },
    ),
    types.FunctionDeclaration(
        name="get_promotions",
        description=(
            "Find active promotions for a product, category, or subcategory."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "category": {"type": "string"},
                "subcategory": {"type": "string"},
            },
        },
    ),
    types.FunctionDeclaration(
        name="update_cart",
        description=(
            "Add, remove, or set the quantity of a product in the current cart. "
            "Sized products require a valid in-stock size. "
            "Near-match product names are supported."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "quantity": {
                    "type": "integer",
                    "minimum": 0,
                },
                "size": {
                    "type": "string",
                    "description": (
                        "Selected product size or variant when required."
                    ),
                },
                "action": {
                    "type": "string",
                    "enum": ["add", "remove", "set"],
                },
            },
            "required": ["product_name"],
        },
    ),
    types.FunctionDeclaration(
        name="get_cart",
        description=(
            "Return the current cart, selected variants, line totals, "
            "and deterministic subtotal_usd."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {},
        },
    ),
    types.FunctionDeclaration(
        name="checkout",
        description=(
            "Complete the simulated purchase. "
            "Use only after explicit confirmation."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {},
        },
    ),
]


GEMINI_TOOLS = [
    types.Tool(
        function_declarations=FUNCTION_DECLARATIONS
    )
]


def user_message(text: str) -> types.Content:
    return types.Content(
        role="user",
        parts=[
            types.Part.from_text(text=text)
        ],
    )


def _usage_details(response: Any) -> dict[str, int]:
    """Return the raw token counters Gemini reported for one call."""
    metadata = getattr(response, "usage_metadata", None)

    def count(field: str) -> int:
        return int(getattr(metadata, field, 0) or 0)

    return {
        "prompt_tokens": count("prompt_token_count"),
        "tool_use_prompt_tokens": count("tool_use_prompt_token_count"),
        "cached_prompt_tokens": count("cached_content_token_count"),
        "candidates_tokens": count("candidates_token_count"),
        "thoughts_tokens": count("thoughts_token_count"),
        "total_tokens": count("total_token_count"),
    }


def _usage(response: Any) -> tuple[int, int]:
    """
    Return (billable_input_tokens, billable_output_tokens).

    Google bills thinking tokens at the output rate, and Gemini reports them
    separately in thoughts_token_count, not in candidates_token_count. Leaving
    them out under-reports output spend for thinking models such as Gemini 3.5.

    tool_use_prompt_token_count covers tokens added by built-in tools and is
    billed as input. JeolAI uses only custom function declarations, so it is
    normally 0.

    Cached-input discounts are not modelled. JeolAI does not use explicit
    context caching, so this remains an estimate.
    """
    details = _usage_details(response)
    input_tokens = details["prompt_tokens"] + details["tool_use_prompt_tokens"]
    output_tokens = details["candidates_tokens"] + details["thoughts_tokens"]
    return input_tokens, output_tokens


def _finish_reason(response: Any) -> str | None:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    if reason is None:
        return None
    return getattr(reason, "name", None) or str(reason)


def _part_has_payload(part: Any) -> bool:
    """
    True when a Part carries anything Gemini will accept.

    An empty-text part that still carries a thought_signature is kept, because
    Gemini 3 requires signatures to be returned exactly as received.
    """
    if part is None:
        return False
    if isinstance(part, types.Part):
        return bool(part.model_dump(exclude_none=True))
    return True


def _valid_parts(content: Any) -> list[Any]:
    return [
        part
        for part in (getattr(content, "parts", None) or [])
        if _part_has_payload(part)
    ]


def _normalize_contents(
    contents: list[types.Content],
) -> list[types.Content]:
    """
    Normalize conversation roles before sending history to Gemini.

    JeolAI may internally represent assistant messages using the conventional
    "assistant" role. Gemini accepts "user" and "model".

    Gemini rejects any Content with no parts ("must include at least one parts
    field"). Such entries are dropped here as a last line of defence; the
    agent loop also avoids storing them in history.

    Normalize only the copy sent to Gemini so application history does not
    need to change.
    """
    normalized: list[types.Content] = []

    for content in contents:
        role = getattr(
            content,
            "role",
            None,
        )

        if role == "assistant":
            role = "model"

        if role not in {"user", "model"}:
            raise ValueError(
                f"Unsupported Gemini conversation role: {role!r}. "
                "Expected 'user' or 'model'."
            )

        parts = _valid_parts(content)
        if not parts:
            logger.warning("Dropping %s content with no parts from Gemini request", role)
            continue

        normalized.append(
            types.Content(
                role=role,
                parts=parts,
            )
        )

    return normalized


def _call_model(
    session_id: str,
    model: str,
    contents: list[types.Content],
):
    start = time.perf_counter()

    response = client.models.generate_content(
        model=model,
        contents=_normalize_contents(contents),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=GEMINI_TOOLS,
            temperature=0.15,
            max_output_tokens=1400,
            automatic_function_calling=(
                types.AutomaticFunctionCallingConfig(
                    disable=True
                )
            ),
        ),
    )

    latency_ms = (
        time.perf_counter() - start
    ) * 1000

    input_tokens, output_tokens = _usage(
        response
    )

    calls = [
        {
            "name": call.name,
            "arguments": dict(
                call.args or {}
            ),
        }
        for call in list(
            response.function_calls or []
        )
    ]

    tracer.record_model_call(
        session_id,
        model,
        input_tokens,
        output_tokens,
        latency_ms,
        details={
            "function_calls_requested": calls,
            "finish_reason": _finish_reason(response),
            "usage": _usage_details(response),
        },
    )

    return response


def _run_tool(
    session_id: str,
    name: str,
    tool_input: dict[str, Any],
) -> dict:
    start = time.perf_counter()

    try:
        result = execute_tool(
            name,
            tool_input,
            session_id,
        )
    except Exception as exc:  # A tool bug must not abort the whole turn.
        logger.exception("Tool %s failed", name)
        result = {
            "success": False,
            "status": "tool_error",
            "error": f"{name} failed: {type(exc).__name__}",
        }

    tracer.record_tool_call(
        session_id,
        name,
        (
            time.perf_counter()
            - start
        )
        * 1000,
        tool_input=tool_input,
        tool_output=result,
    )

    return result


def _response_content(
    response: Any,
) -> types.Content | None:
    """
    Return the model turn to store in history, or None if it is empty.

    Gemini can return a candidate whose content has no parts (observed in
    the failing session: 0 output tokens, no function call). Storing that in
    history produced the 400 "must include at least one parts field" on every
    later request.
    """
    candidates = (
        getattr(
            response,
            "candidates",
            None,
        )
        or []
    )

    if (
        not candidates
        or candidates[0].content is None
    ):
        return None

    parts = _valid_parts(candidates[0].content)
    if not parts:
        return None

    # Keep the original Part objects so thought signatures and function-call
    # ordering are preserved exactly as Gemini returned them.
    return types.Content(role="model", parts=parts)


def _response_text(response: Any) -> str:
    """Join non-thought text parts without triggering SDK warnings."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates or candidates[0].content is None:
        return ""
    texts = [
        part.text
        for part in (candidates[0].content.parts or [])
        if getattr(part, "text", None) and not getattr(part, "thought", False)
    ]
    return "".join(texts).strip()


def _latest_user_text(
    contents: list[types.Content],
) -> str:
    for content in reversed(contents):
        if (
            getattr(
                content,
                "role",
                None,
            )
            != "user"
        ):
            continue

        texts = []

        for part in (
            getattr(
                content,
                "parts",
                [],
            )
            or []
        ):
            text = getattr(
                part,
                "text",
                None,
            )

            if text:
                texts.append(text)

        if texts:
            return " ".join(texts)

    return ""


def _extract_budget(
    text: str,
) -> float | None:
    match = re.search(
        (
            r"(?:under|within|budget(?: of)?|less than)"
            r"\s*\$?\s*(\d+(?:\.\d+)?)"
        ),
        text,
        re.I,
    )

    return (
        float(match.group(1))
        if match
        else None
    )


def _is_bundle_request(
    text: str,
) -> bool:
    return bool(
        re.search(
            (
                r"\b(outfit|bundle|kit|packing list|"
                r"complete look|gear list)\b"
            ),
            text,
            re.I,
        )
    )


def _preplan_bundle(
    session_id: str,
    text: str,
) -> str | None:
    """
    Run visible deterministic sub-searches before Gemini composes a bundle.

    This guarantees a genuine multi-tool trace for workshop prompts while
    still leaving selection and explanation to Gemini.
    """
    if not _is_bundle_request(text):
        return None

    total_budget = (
        _extract_budget(text)
        or 500.0
    )

    use_case = (
        "hiking"
        if "hik" in text.lower()
        else "outdoor"
    )

    if re.search(
        r"\b(women|woman|female)\b",
        text,
        re.I,
    ):
        gender = "women"
    elif re.search(
        r"\b(men|man|male)\b",
        text,
        re.I,
    ):
        gender = "men"
    else:
        gender = None

    plan = [
        (
            "outerwear",
            {
                "query": "waterproof jacket",
                "subcategory": "jackets",
                "use_case": use_case,
                "gender": gender,
                "max_price": round(
                    total_budget * 0.35,
                    2,
                ),
                "limit": 4,
            },
        ),
        (
            "footwear",
            {
                "query": "hiking boots",
                "category": "footwear",
                "use_case": use_case,
                "gender": gender,
                "max_price": round(
                    total_budget * 0.40,
                    2,
                ),
                "limit": 4,
            },
        ),
        (
            "lower body",
            {
                "query": "hiking pants",
                "subcategory": "pants",
                "use_case": use_case,
                "gender": gender,
                "max_price": round(
                    total_budget * 0.25,
                    2,
                ),
                "limit": 4,
            },
        ),
        (
            "base layer",
            {
                "query": "base layer",
                "subcategory": "base layers",
                "use_case": use_case,
                "gender": gender,
                "max_price": round(
                    total_budget * 0.20,
                    2,
                ),
                "limit": 3,
            },
        ),
        (
            "accessory",
            {
                "query": "hiking socks",
                "subcategory": "socks",
                "use_case": use_case,
                "max_price": round(
                    total_budget * 0.12,
                    2,
                ),
                "limit": 3,
            },
        ),
    ]

    tracer.record_event(
        session_id,
        "Planner created multi-step shopping workflow",
        details={
            "requested_budget_usd": (
                total_budget
            ),
            "use_case": use_case,
            "steps": [
                name
                for name, _ in plan
            ],
        },
        step_type="planning",
    )

    gathered: dict[str, Any] = {}

    for label, args in plan:
        clean_args = {
            key: value
            for key, value in args.items()
            if value is not None
        }

        gathered[label] = _run_tool(
            session_id,
            "search_products",
            clean_args,
        )

    return (
        "The orchestration layer completed multiple catalog searches "
        "for this bundle. "
        f"Customer product budget: ${total_budget:.2f}. "
        "Select a practical combination from the JSON below, "
        "keep the total within budget, and mention any category "
        "that has no suitable match.\n"
        + json.dumps(
            gathered,
            ensure_ascii=False,
        )
    )


_CART_REVIEW = re.compile(
    r"\b(show|view|see|review|display|list|what(?:'s| is)?|whats)\b"
    r"[^.?!]{0,40}\b(my |the )?cart\b"
    r"|\bcart\b[^.?!]{0,20}\b(contents|status|total)\b"
    r"|\bin (?:my|the) cart\b",
    re.I,
)


def _is_cart_review_request(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\b(add|remove|delete|checkout|check out|buy|purchase)\b", lowered):
        return False
    return bool(_CART_REVIEW.search(text))


def _format_money(value: Any) -> str:
    return f"${float(value):,.2f}"


def _format_cart(cart: dict[str, Any]) -> str:
    """Deterministic cart summary built only from get_cart output."""
    items = cart.get("items") or []
    if not items:
        return "Your cart is empty."

    lines = ["Here is what is in your cart:"]
    for item in items:
        size = item.get("selected_size")
        size_text = f", size {size}" if size else ""
        lines.append(
            f"- {item['product_name']}{size_text} × {item['quantity']}: "
            f"{_format_money(item['line_total_usd'])}"
        )
    lines.append(f"Subtotal: {_format_money(cart.get('subtotal_usd', 0))}")
    return "\n".join(lines)


def _format_checkout(result: dict[str, Any]) -> str:
    """Deterministic checkout summary built only from checkout output."""
    if result.get("success"):
        text = (
            f"Order {result.get('order_id')} is complete. "
            f"Subtotal {_format_money(result.get('subtotal_usd', 0))}, "
            f"discount {_format_money(result.get('discount_usd', 0))}, "
            f"total {_format_money(result.get('total_usd', 0))}."
        )
        if result.get("promo_code"):
            text += f" Promotion applied: {result['promo_code']}."
        return text
    return f"Checkout was not completed: {result.get('error', 'unknown reason')}."


@dataclass
class TurnUsage:
    """Accumulates billable tokens across every model call in one turn.

    Kept outside the loop so tokens already spent are still charged to the
    session budget when a later call in the same turn fails.
    """

    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, response: Any) -> None:
        input_tokens, output_tokens = _usage(response)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens


def _function_response_part(name: str, result: dict) -> types.Part:
    return types.Part.from_function_response(
        name=name,
        response={"result": result},
    )


def _deterministic_fallback(
    session_id: str,
    contents: list[types.Content],
) -> str:
    """
    Answer from deterministic tools when Gemini returns an empty turn.

    For a cart-review request the backend calls get_cart itself, so the user
    still gets the real cart state rather than a generic failure.
    """
    latest = _latest_user_text(contents)

    if _is_cart_review_request(latest):
        result = _run_tool(session_id, "get_cart", {})
        tracer.record_event(
            session_id,
            "Deterministic cart fallback used after empty model response",
            step_type="fallback",
        )
        return _format_cart(result.get("cart") or {})

    return (
        "I wasn't able to generate a response for that request. "
        "Please try again or rephrase it."
    )


def _agent_loop(
    session_id: str,
    model: str,
    contents: list[types.Content],
    usage: TurnUsage | None = None,
    state: dict[str, Any] | None = None,
) -> dict:
    usage = usage or TurnUsage()
    state = state if state is not None else {}
    empty_responses = 0

    for _ in range(MAX_AGENT_STEPS):
        response = _call_model(
            session_id,
            model,
            contents,
        )
        usage.add(response)

        content = _response_content(response)
        calls = list(response.function_calls or []) if content else []
        text = _response_text(response) if content else ""

        if not calls and not text:
            # Empty turn: do NOT store it in history.
            empty_responses += 1
            tracer.record_event(
                session_id,
                "Gemini returned an empty response",
                details={
                    "finish_reason": _finish_reason(response),
                    "usage": _usage_details(response),
                    "attempt": empty_responses,
                },
                step_type="model_empty_response",
            )

            if empty_responses <= EMPTY_RESPONSE_RETRIES:
                continue

            text = _deterministic_fallback(session_id, contents)
            contents.append(
                types.Content(role="model", parts=[types.Part.from_text(text=text)])
            )
            return _complete(session_id, text, contents, usage, fallback=True)

        contents.append(content)

        if not calls:
            return _complete(session_id, text, contents, usage)

        for call in calls:
            args = dict(
                call.args or {}
            )

            tracer.record_tool_decision(
                session_id,
                call.name,
                args,
            )

        needs_approval = any(
            call.name == "checkout" and not state.get("completed_checkout")
            for call in calls
        ) and budget.checkout_requires_approval(session_id)

        if needs_approval:
            tracer.record_event(
                session_id,
                (
                    "Checkout paused "
                    "for human approval"
                ),
                details={
                    "budget_tier": "gated"
                },
                step_type="approval",
            )

            # Every function call in this model turn must get a response
            # (Gemini rejects partial answers), so all of them are kept and
            # executed together after the approval decision.
            return {
                "status": "needs_approval",
                "pending_function_name": (
                    "checkout"
                ),
                "pending_calls": [
                    {"name": call.name, "args": dict(call.args or {})}
                    for call in calls
                ],
                "messages": contents,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            }

        response_parts = []

        for call in calls:
            args = dict(call.args or {})
            if call.name == "checkout" and state.get("completed_checkout"):
                result = _duplicate_checkout_result(state["completed_checkout"])
            else:
                result = _run_tool(session_id, call.name, args)
                if call.name == "checkout" and result.get("success"):
                    state["completed_checkout"] = result

            response_parts.append(_function_response_part(call.name, result))

        contents.append(
            types.Content(
                role="user",
                parts=response_parts,
            )
        )

    raise RuntimeError(
        "Agent exceeded the maximum number "
        "of tool orchestration steps"
    )


def _duplicate_checkout_result(completed: dict[str, Any]) -> dict[str, Any]:
    """Stop a second checkout in the same turn from reporting an empty cart."""
    return {
        "success": False,
        "status": "already_completed",
        "order_id": completed.get("order_id"),
        "message": (
            "Checkout already completed for this request. Report the "
            "completed order; do not call checkout again."
        ),
        "completed_order": completed,
    }


def _complete(
    session_id: str,
    text: str,
    contents: list[types.Content],
    usage: TurnUsage,
    fallback: bool = False,
) -> dict:
    tracer.record_event(
        session_id,
        "Agent produced final response",
        details={
            "response_preview": text[:500],
            "deterministic_fallback": fallback,
        },
        step_type="final_response",
    )

    return {
        "status": "complete",
        "text": text,
        "messages": contents,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }


_MODEL_ERROR_REPLY = (
    "I couldn't complete that request because the AI model returned an "
    "error. Your cart and conversation are unchanged. Please try again."
)


def _error_result(
    session_id: str,
    exc: Exception,
    contents: list[types.Content],
    usage: TurnUsage,
    text: str = _MODEL_ERROR_REPLY,
) -> dict:
    logger.exception("Agent turn failed for session %s", session_id)
    tracer.record_event(
        session_id,
        "Agent turn failed; conversation state rolled back",
        details={"error_type": type(exc).__name__, "error": str(exc)[:500]},
        step_type="error",
    )
    return {
        "status": "error",
        "text": text,
        "messages": contents,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "error": type(exc).__name__,
    }


def run_turn(
    session_id: str,
    model: str,
    conversation: list[types.Content],
) -> dict:
    """
    Run one user turn.

    On any failure the conversation is truncated back to its length at entry,
    so a failed Gemini call can never leave a malformed message behind for
    the next request.
    """
    snapshot = len(conversation)
    usage = TurnUsage()

    try:
        preplanned = _preplan_bundle(
            session_id,
            _latest_user_text(
                conversation
            ),
        )

        if preplanned:
            conversation.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=preplanned
                        )
                    ],
                )
            )

        return _agent_loop(
            session_id,
            model,
            conversation,
            usage,
        )
    except Exception as exc:
        del conversation[snapshot:]
        return _error_result(session_id, exc, conversation, usage)


def close_pending_calls(
    pending_calls: list[dict[str, Any]],
    reason: str,
) -> list[types.Part]:
    """
    Build function responses for calls left open by an unanswered approval.

    Without these, the history would end with an unanswered function call
    and Gemini would reject the next request.
    """
    return [
        _function_response_part(
            call["name"],
            {"success": False, "status": "not_executed", "error": reason},
        )
        for call in pending_calls
    ]


def resume_after_approval(
    session_id: str,
    model: str,
    messages: list[types.Content],
    function_name: str,
    approved: bool,
    pending_calls: list[dict[str, Any]] | None = None,
) -> dict:
    usage = TurnUsage()
    state: dict[str, Any] = {}
    calls = pending_calls or [{"name": function_name, "args": {}}]
    checkout_result: dict[str, Any] | None = None
    response_parts = []

    for call in calls:
        name = call["name"]
        args = dict(call.get("args") or {})

        if name != "checkout":
            result = _run_tool(session_id, name, args)
        elif approved:
            result = _run_tool(session_id, name, args)
            checkout_result = result
            if result.get("success"):
                state["completed_checkout"] = result
            tracer.record_event(
                session_id,
                (
                    "Checkout approved "
                    "and executed"
                ),
                step_type="approval",
            )
        else:
            result = {
                "success": False,
                "error": (
                    "Checkout denied. "
                    "Cart preserved."
                ),
            }
            checkout_result = result
            tracer.record_event(
                session_id,
                "Checkout denied",
                step_type="approval",
            )

        response_parts.append(_function_response_part(name, result))

    messages.append(
        types.Content(
            role="user",
            parts=response_parts,
        )
    )
    snapshot = len(messages)

    try:
        return _agent_loop(
            session_id,
            model,
            messages,
            usage,
            state,
        )
    except Exception as exc:
        # The checkout decision is already final in the database, so report
        # it deterministically and close the turn with a model message.
        del messages[snapshot:]
        text = (
            _format_checkout(checkout_result)
            if checkout_result is not None
            else _MODEL_ERROR_REPLY
        )
        messages.append(
            types.Content(role="model", parts=[types.Part.from_text(text=text)])
        )
        return _error_result(session_id, exc, messages, usage, text=text)
