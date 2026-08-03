"""Deterministic commerce tools exposed to Gemini."""
from __future__ import annotations
from backend import budget, db


def execute_tool(name: str, tool_input: dict, session_id: str) -> dict:
    if name == "catalog_facets":
        return {"categories": db.list_categories()}
    if name == "search_products":
        requested_limit = int(tool_input.get("limit") or 8)
        policy_limit = budget.search_result_limit(session_id)
        limit = min(requested_limit, policy_limit) if policy_limit else requested_limit
        results = db.search_products(
            query=tool_input.get("query"), category=tool_input.get("category"),
            subcategory=tool_input.get("subcategory"), brand=tool_input.get("brand"),
            gender=tool_input.get("gender"), min_price=tool_input.get("min_price"),
            max_price=tool_input.get("max_price"), size=tool_input.get("size"),
            use_case=tool_input.get("use_case"), limit=limit,
        )
        return {"count": len(results), "results": results, "policy_result_limit": limit}
    if name == "check_inventory":
        return db.check_inventory(tool_input["product_name"], tool_input.get("size"))
    if name == "get_promotions":
        return {"promotions": db.get_promotions(
            category=tool_input.get("category"), subcategory=tool_input.get("subcategory"),
            product_name=tool_input.get("product_name"),
        )}
    if name == "update_cart":
        return db.update_cart(session_id, tool_input["product_name"], int(tool_input.get("quantity", 1)), tool_input.get("action", "add"))
    if name == "get_cart":
        return {"cart": db.get_cart(session_id)}
    if name == "checkout":
        return db.checkout(session_id)
    return {"error": f"Unknown tool: {name}"}
