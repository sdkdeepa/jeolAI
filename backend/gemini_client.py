"""Vertex AI Gemini client with observable, multi-step commerce orchestration."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from backend import budget, tracer
from backend.tools import execute_tool

load_dotenv()
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
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
stock, promotions, cart contents, or orders.

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
7. Use get_cart before checkout or whenever the user asks what is in the cart.
8. Call checkout only after explicit user confirmation.
9. Keep the response concise, useful, and grounded in tool output.
""".strip()

FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="catalog_facets",
        description="List the categories and subcategories available in the store.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    types.FunctionDeclaration(
        name="search_products",
        description="Search and filter the product catalog. Supports price, size, brand, gender, category, and use case.",
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
                "limit": {"type": "integer", "minimum": 1, "maximum": 12},
            },
        },
    ),
    types.FunctionDeclaration(
        name="check_inventory",
        description="Check stock and optional size availability for a product. Near-match product names are supported.",
        parameters_json_schema={
            "type": "object",
            "properties": {"product_name": {"type": "string"}, "size": {"type": "string"}},
            "required": ["product_name"],
        },
    ),
    types.FunctionDeclaration(
        name="get_promotions",
        description="Find active promotions for a product, category, or subcategory.",
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
        description="Add, remove, or set the quantity of a product in the current cart. Near-match names are supported.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 0},
                "action": {"type": "string", "enum": ["add", "remove", "set"]},
            },
            "required": ["product_name"],
        },
    ),
    types.FunctionDeclaration(
        name="get_cart",
        description="Return the current cart with line totals.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    types.FunctionDeclaration(
        name="checkout",
        description="Complete the simulated purchase. Use only after explicit confirmation.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
]
GEMINI_TOOLS = [types.Tool(function_declarations=FUNCTION_DECLARATIONS)]


def user_message(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part.from_text(text=text)])


def _usage(response: Any) -> tuple[int, int]:
    metadata = getattr(response, "usage_metadata", None)
    return (
        int(getattr(metadata, "prompt_token_count", 0) or 0),
        int(getattr(metadata, "candidates_token_count", 0) or 0),
    )


def _call_model(session_id: str, model: str, contents: list[types.Content]):
    start = time.perf_counter()
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=GEMINI_TOOLS,
            temperature=0.15,
            max_output_tokens=1400,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    latency_ms = (time.perf_counter() - start) * 1000
    input_tokens, output_tokens = _usage(response)
    calls = [{"name": c.name, "arguments": dict(c.args or {})} for c in list(response.function_calls or [])]
    tracer.record_model_call(
        session_id, model, input_tokens, output_tokens, latency_ms,
        details={"function_calls_requested": calls},
    )
    return response


def _run_tool(session_id: str, name: str, tool_input: dict[str, Any]) -> dict:
    start = time.perf_counter()
    result = execute_tool(name, tool_input, session_id)
    tracer.record_tool_call(
        session_id, name, (time.perf_counter() - start) * 1000,
        tool_input=tool_input, tool_output=result,
    )
    return result


def _response_content(response: Any) -> types.Content:
    candidates = getattr(response, "candidates", None) or []
    if not candidates or candidates[0].content is None:
        raise RuntimeError("Gemini returned no candidate content")
    return candidates[0].content


def _latest_user_text(contents: list[types.Content]) -> str:
    for content in reversed(contents):
        if getattr(content, "role", None) != "user":
            continue
        texts = []
        for part in getattr(content, "parts", []) or []:
            text = getattr(part, "text", None)
            if text:
                texts.append(text)
        if texts:
            return " ".join(texts)
    return ""


def _extract_budget(text: str) -> float | None:
    match = re.search(r"(?:under|within|budget(?: of)?|less than)\s*\$?\s*(\d+(?:\.\d+)?)", text, re.I)
    return float(match.group(1)) if match else None


def _is_bundle_request(text: str) -> bool:
    return bool(re.search(r"\b(outfit|bundle|kit|packing list|complete look|gear list)\b", text, re.I))


def _preplan_bundle(session_id: str, text: str) -> str | None:
    """Run visible deterministic sub-searches before Gemini composes a bundle.

    This guarantees a genuine multi-tool trace for workshop prompts while still
    leaving selection and explanation to Gemini.
    """
    if not _is_bundle_request(text):
        return None
    total_budget = _extract_budget(text) or 500.0
    use_case = "hiking" if "hik" in text.lower() else "outdoor"
    gender = "women" if re.search(r"\b(women|woman|female)\b", text, re.I) else "men" if re.search(r"\b(men|man|male)\b", text, re.I) else None
    plan = [
        ("outerwear", {"query": "waterproof jacket", "subcategory": "jackets", "use_case": use_case, "gender": gender, "max_price": round(total_budget * 0.35, 2), "limit": 4}),
        ("footwear", {"query": "hiking boots", "category": "footwear", "use_case": use_case, "gender": gender, "max_price": round(total_budget * 0.40, 2), "limit": 4}),
        ("lower body", {"query": "hiking pants", "subcategory": "pants", "use_case": use_case, "gender": gender, "max_price": round(total_budget * 0.25, 2), "limit": 4}),
        ("base layer", {"query": "base layer", "subcategory": "base layers", "use_case": use_case, "gender": gender, "max_price": round(total_budget * 0.20, 2), "limit": 3}),
        ("accessory", {"query": "hiking socks", "subcategory": "socks", "use_case": use_case, "max_price": round(total_budget * 0.12, 2), "limit": 3}),
    ]
    tracer.record_event(
        session_id, "Planner created multi-step shopping workflow",
        details={"requested_budget_usd": total_budget, "use_case": use_case, "steps": [name for name, _ in plan]},
        step_type="planning",
    )
    gathered: dict[str, Any] = {}
    for label, args in plan:
        clean_args = {k: v for k, v in args.items() if v is not None}
        gathered[label] = _run_tool(session_id, "search_products", clean_args)
    return (
        "The orchestration layer completed multiple catalog searches for this bundle. "
        f"Customer product budget: ${total_budget:.2f}. Select a practical combination from the JSON below, "
        "keep the total within budget, and mention any category that has no suitable match.\n"
        + json.dumps(gathered, ensure_ascii=False)
    )


def _agent_loop(session_id: str, model: str, contents: list[types.Content]) -> dict:
    total_input = total_output = 0
    for _ in range(8):
        response = _call_model(session_id, model, contents)
        i, o = _usage(response); total_input += i; total_output += o
        contents.append(_response_content(response))
        calls = list(response.function_calls or [])
        if not calls:
            text = response.text or "I could not generate a grounded response."
            tracer.record_event(session_id, "Agent produced final response", details={"response_preview": text[:500]}, step_type="final_response")
            return {"status": "complete", "text": text, "messages": contents, "input_tokens": total_input, "output_tokens": total_output}

        for call in calls:
            args = dict(call.args or {})
            tracer.record_tool_decision(session_id, call.name, args)
            if call.name == "checkout" and budget.checkout_requires_approval(session_id):
                tracer.record_event(session_id, "Checkout paused for human approval", details={"budget_tier": "gated"}, step_type="approval")
                return {"status": "needs_approval", "pending_function_name": "checkout", "messages": contents, "input_tokens": total_input, "output_tokens": total_output}

        response_parts = []
        for call in calls:
            result = _run_tool(session_id, call.name, dict(call.args or {}))
            response_parts.append(types.Part.from_function_response(name=call.name, response={"result": result}))
        contents.append(types.Content(role="user", parts=response_parts))

    raise RuntimeError("Agent exceeded the maximum number of tool orchestration steps")


def run_turn(session_id: str, model: str, conversation: list[types.Content]) -> dict:
    preplanned = _preplan_bundle(session_id, _latest_user_text(conversation))
    if preplanned:
        conversation.append(types.Content(role="user", parts=[types.Part.from_text(text=preplanned)]))
    return _agent_loop(session_id, model, conversation)


def resume_after_approval(session_id: str, model: str, messages: list[types.Content], function_name: str, approved: bool) -> dict:
    if approved:
        result = _run_tool(session_id, function_name, {})
        tracer.record_event(session_id, "Checkout approved and executed", step_type="approval")
    else:
        result = {"success": False, "error": "Checkout denied. Cart preserved."}
        tracer.record_event(session_id, "Checkout denied", step_type="approval")
    messages.append(types.Content(role="user", parts=[types.Part.from_function_response(name=function_name, response={"result": result})]))
    return _agent_loop(session_id, model, messages)
