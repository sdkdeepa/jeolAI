"""Deterministic pre-model domain guardrail for JeolAI."""
from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason: str
    matched_signal: str | None = None

_OFF_DOMAIN = (
    (r"\b(reverse|sort|parse|compile|debug)\b.*\b(string|array|code|python|javascript|java|sql)\b", "programming"),
    (r"\b(palindrome|binary search|linked list|leetcode|algorithm)\b", "computer science"),
    (r"\b(weather|forecast|temperature)\b", "weather"),
    (r"\b(recipe|cook|cooking)\b", "cooking"),
    (r"\b(translate|translation)\b", "translation"),
    (r"\b(stock price|crypto|bitcoin|investment)\b", "finance"),
    (r"\b(write me a poem|poem|story)\b", "creative writing"),
)
_COMMERCE = {
    "buy","shop","shopping","product","item","catalog","price","cost","budget","under","compare","recommend",
    "find","search","stock","inventory","available","promotion","promo","discount","sale","coupon","cart","checkout",
    "purchase","order","add","remove","quantity","jacket","shoe","shoes","boot","boots","sock","socks","backpack",
    "bottle","camera","electronics","fitness","apparel","outfit","bundle","kit","hiking","running","yoga","sweater",
    "vest","hat","sunglasses","swimwear","pants","shirt","gear","size","color","brand","women","men"
}
_GREETING = re.compile(r"^\s*(hi|hello|hey|help|what can you do)\s*[!?.]*\s*$", re.I)

def evaluate_request(message: str) -> GuardDecision:
    normalized = " ".join(message.lower().strip().split())
    if not normalized:
        return GuardDecision(False, "Empty request", "empty")
    if _GREETING.match(normalized):
        return GuardDecision(True, "Greeting", "greeting")
    for pattern, label in _OFF_DOMAIN:
        if re.search(pattern, normalized, re.I):
            return GuardDecision(False, f"This is a {label} request, not a shopping workflow.", label)
    words = set(re.findall(r"[a-z0-9]+", normalized))
    matches = sorted(words & _COMMERCE)
    if matches:
        return GuardDecision(True, "Commerce intent detected", ", ".join(matches[:6]))
    return GuardDecision(False, "No shopping or commerce intent detected", "no_commerce_intent")
