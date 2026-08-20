"""Deterministic pre-model domain guardrail for JeolAI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason: str
    matched_signal: str | None = None


_OFF_DOMAIN = (
    (
        r"\b(reverse|sort|parse|compile|debug)\b.*"
        r"\b(string|array|code|python|javascript|java|sql)\b",
        "programming",
    ),
    (
        r"\b(palindrome|binary search|linked list|leetcode|algorithm)\b",
        "computer science",
    ),
    (
        r"\b(weather|forecast|temperature)\b",
        "weather",
    ),
    (
        r"\b(recipe|cook|cooking)\b",
        "cooking",
    ),
    (
        r"\b(translate|translation)\b",
        "translation",
    ),
    (
        r"\b(stock price|crypto|bitcoin|investment)\b",
        "finance",
    ),
    (
        r"\b(write me a poem|poem|story)\b",
        "creative writing",
    ),
)


_COMMERCE = {
    "buy",
    "shop",
    "shopping",
    "product",
    "item",
    "catalog",
    "price",
    "cost",
    "budget",
    "under",
    "compare",
    "recommend",
    "find",
    "search",
    "stock",
    "inventory",
    "available",
    "promotion",
    "promo",
    "discount",
    "sale",
    "coupon",
    "cart",
    "checkout",
    "purchase",
    "order",
    "add",
    "remove",
    "quantity",
    "jacket",
    "shoe",
    "shoes",
    "boot",
    "boots",
    "sock",
    "socks",
    "backpack",
    "bottle",
    "camera",
    "electronics",
    "fitness",
    "apparel",
    "outfit",
    "bundle",
    "kit",
    "hiking",
    "running",
    "yoga",
    "sweater",
    "vest",
    "hat",
    "sunglasses",
    "swimwear",
    "pants",
    "shirt",
    "gear",
    "size",
    "color",
    "brand",
    "women",
    "men",
}


_GREETING = re.compile(
    r"^\s*(hi|hello|hey|help|what can you do)\s*[!?.]*\s*$",
    re.I,
)


_SIZE_PROMPT = re.compile(
    r"\b("
    r"what size|"
    r"which size|"
    r"select a size|"
    r"choose a size|"
    r"size would you like|"
    r"size do you want"
    r")\b",
    re.I,
)


_SIZE_FOLLOWUP = re.compile(
    r"^\s*"
    r"(?:size\s+)?"
    r"("
    r"\d{1,2}(?:\.\d+)?"
    r"|xxs|xs|s|m|l|xl|xxl|xxxl"
    r"|small|medium|large"
    r")"
    r"(?:\s+(?:size|wide|narrow))?"
    r"\s*$",
    re.I,
)


def _history_message(item: dict[str, Any]) -> str:
    """
    Read a history message from either JeolAI's API history shape:

        {"role": "assistant", "message": "..."}

    or a simpler test/client shape:

        {"role": "assistant", "content": "..."}
    """
    value = item.get("message")

    if value is None:
        value = item.get("content")

    return str(value or "")


def _last_assistant_message(
    history: list[dict[str, Any]] | None,
) -> str:
    if not history:
        return ""

    for item in reversed(history):
        if item.get("role") in {
            "assistant",
            "model",
        }:
            return _history_message(item)

    return ""


def _is_expected_size_followup(
    message: str,
    history: list[dict[str, Any]] | None,
) -> bool:
    """
    Allow a short/ambiguous size response only when the immediately
    preceding shopping conversation expects a size.

    Examples that become valid in this context:

        10
        10.5 wide
        L
        XL
        large

    This does not bypass explicit off-domain rules.
    """
    previous_assistant_message = _last_assistant_message(
        history
    )

    if not previous_assistant_message:
        return False

    if not _SIZE_PROMPT.search(
        previous_assistant_message
    ):
        return False

    return bool(
        _SIZE_FOLLOWUP.match(message)
    )


def evaluate_request(
    message: str,
    history: list[dict[str, Any]] | None = None,
) -> GuardDecision:
    normalized = " ".join(
        message.lower().strip().split()
    )

    if not normalized:
        return GuardDecision(
            False,
            "Empty request",
            "empty",
        )

    if _GREETING.match(normalized):
        return GuardDecision(
            True,
            "Greeting",
            "greeting",
        )

    # Explicit off-domain requests always win, even if the previous
    # assistant turn asked a commerce follow-up question.
    for pattern, label in _OFF_DOMAIN:
        if re.search(
            pattern,
            normalized,
            re.I,
        ):
            return GuardDecision(
                False,
                (
                    f"This is a {label} request, "
                    "not a shopping workflow."
                ),
                label,
            )

    words = set(
        re.findall(
            r"[a-z0-9]+",
            normalized,
        )
    )

    matches = sorted(
        words & _COMMERCE
    )

    if matches:
        return GuardDecision(
            True,
            "Commerce intent detected",
            ", ".join(matches[:6]),
        )

    # A standalone response such as "10.5 wide" has no commerce
    # keyword. It is nevertheless valid when JeolAI just asked
    # the user for a size.
    if _is_expected_size_followup(
        message,
        history,
    ):
        return GuardDecision(
            True,
            "Expected product-size follow-up",
            "size_followup",
        )

    return GuardDecision(
        False,
        "No shopping or commerce intent detected",
        "no_commerce_intent",
    )