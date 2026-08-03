"""SQLite persistence and a realistic outdoor-commerce catalog for JeolAI.

The catalog is deliberately rich enough to support natural workshop prompts:
product discovery, price-constrained recommendations, inventory checks,
promotions, carts, checkout, and multi-item hiking bundles.
"""

from __future__ import annotations

import json
import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shop_agent.db"
CATALOG_VERSION = "2026-08-rich-outdoor-v2"

# sku, name, brand, category, subcategory, gender, price, description, stock,
# sizes, colors, tags
SEED_PRODUCTS = [
    ("JKT-001", "Alpine Rain Shell", "North Ridge", "apparel", "jackets", "unisex", 119.00, "Waterproof breathable shell for hiking and backpacking", 18, ["XS","S","M","L","XL"], ["Navy","Sage","Black"], ["waterproof","hiking","rain","shell","backpacking"]),
    ("JKT-002", "Storm Pro Jacket", "TrailForge", "apparel", "jackets", "men", 149.00, "Three-layer waterproof jacket with pit zips and helmet hood", 12, ["S","M","L","XL"], ["Blue","Black"], ["waterproof","storm","hiking","technical"]),
    ("JKT-003", "Cascade Women’s Rain Jacket", "North Ridge", "apparel", "jackets", "women", 109.00, "Packable waterproof rain jacket with adjustable hood", 21, ["XS","S","M","L","XL"], ["Rose","Teal","Black"], ["waterproof","women","rain","packable"]),
    ("JKT-004", "Summit Softshell Jacket", "PeakLine", "apparel", "jackets", "unisex", 96.00, "Wind-resistant stretch softshell for cool-weather hiking", 25, ["S","M","L","XL"], ["Charcoal","Olive"], ["softshell","windproof","hiking","fall"]),
    ("JKT-005", "Glacier Down Jacket", "PeakLine", "apparel", "jackets", "unisex", 179.00, "Lightweight insulated down jacket for cold trail conditions", 14, ["XS","S","M","L","XL"], ["Plum","Black"], ["insulated","winter","down","hiking"]),
    ("JKT-006", "Trail Windbreaker", "Canyon Works", "apparel", "jackets", "unisex", 64.00, "Ultralight windbreaker that packs into its own pocket", 31, ["S","M","L","XL"], ["Mint","Navy"], ["windbreaker","lightweight","trail","running"]),
    ("BOT-001", "Summit GTX Hiking Boots", "PeakLine", "footwear", "hiking boots", "unisex", 159.00, "Waterproof Gore-Tex hiking boots with high-traction outsole", 24, ["6","7","8","9","10","11","12"], ["Brown","Black"], ["waterproof","gtx","hiking","boots","backpacking"]),
    ("BOT-002", "Ridge Trek Mid Boots", "TrailForge", "footwear", "hiking boots", "unisex", 129.00, "Supportive mid-height hiking boots for mixed terrain", 29, ["6","7","8","9","10","11","12"], ["Tan","Gray"], ["hiking","boots","ankle support","trail"]),
    ("BOT-003", "Canyon Hiker Low", "Canyon Works", "footwear", "hiking shoes", "unisex", 99.00, "Low-cut hiking shoe with rock plate and grippy outsole", 33, ["6","7","8","9","10","11","12"], ["Olive","Gray"], ["hiking","shoes","lightweight","trail"]),
    ("BOT-004", "Alpine Trek Women’s Boot", "North Ridge", "footwear", "hiking boots", "women", 139.00, "Women’s waterproof hiking boot with cushioned midsole", 17, ["5","6","7","8","9","10"], ["Burgundy","Gray"], ["women","waterproof","hiking","boots"]),
    ("SHO-001", "Trail Runner Pro", "MotionPeak", "footwear", "trail running", "unisex", 112.00, "Responsive trail-running shoe with aggressive lugs", 37, ["6","7","8","9","10","11","12"], ["Coral","Black"], ["trail running","shoes","running","grip"]),
    ("SHO-002", "River Trek Sandal", "Canyon Works", "footwear", "sandals", "unisex", 72.00, "Quick-drying hiking sandal with toe protection", 20, ["6","7","8","9","10","11","12"], ["Blue","Brown"], ["sandals","water","summer","hiking"]),
    ("TOP-001", "Merino Base Layer Top", "WoolPath", "apparel", "base layers", "unisex", 58.00, "Moisture-wicking merino base layer for cold-weather hiking", 42, ["XS","S","M","L","XL"], ["Cream","Charcoal"], ["merino","base layer","warm","hiking"]),
    ("TOP-002", "Thermal Grid Fleece", "North Ridge", "apparel", "midlayers", "unisex", 69.00, "Breathable grid fleece midlayer for active insulation", 28, ["S","M","L","XL"], ["Sage","Navy"], ["fleece","midlayer","warm","hiking"]),
    ("TOP-003", "SunShield Trail Shirt", "Canyon Works", "apparel", "shirts", "unisex", 44.00, "UPF 50 quick-dry long-sleeve hiking shirt", 36, ["XS","S","M","L","XL"], ["Sky","Sand"], ["sun protection","shirt","hiking","quick dry"]),
    ("PNT-001", "Granite Hiking Pants", "TrailForge", "apparel", "pants", "unisex", 79.00, "Stretch hiking pants with water-resistant finish", 34, ["28","30","32","34","36","38"], ["Olive","Charcoal"], ["pants","hiking","water resistant","stretch"]),
    ("PNT-002", "Women’s TrailFlex Pants", "North Ridge", "apparel", "pants", "women", 74.00, "Women’s articulated hiking pants with zip pockets", 27, ["2","4","6","8","10","12","14"], ["Sage","Black"], ["women","pants","hiking","stretch"]),
    ("PNT-003", "Convertible Trek Pants", "Canyon Works", "apparel", "pants", "unisex", 82.00, "Zip-off hiking pants that convert to shorts", 19, ["28","30","32","34","36","38"], ["Khaki","Gray"], ["convertible","pants","hiking","summer"]),
    ("SOC-001", "Merino Hiking Socks 2-Pack", "WoolPath", "apparel", "socks", "unisex", 24.00, "Cushioned moisture-wicking merino hiking socks", 65, ["S","M","L"], ["Heather","Forest"], ["merino","socks","hiking","warm"]),
    ("SOC-002", "Lightweight Trail Socks 3-Pack", "MotionPeak", "apparel", "socks", "unisex", 21.00, "Breathable lightweight socks for warm-weather trails", 58, ["S","M","L"], ["Mixed"], ["socks","lightweight","trail","summer"]),
    ("BAG-001", "Trail Daypack 20L", "PackWorks", "gear", "backpacks", "unisex", 69.00, "Compact hydration-compatible daypack for short hikes", 30, [], ["Lilac","Black"], ["backpack","daypack","hiking","20l"]),
    ("BAG-002", "Summit Pack 35L", "PackWorks", "gear", "backpacks", "unisex", 119.00, "Ventilated 35-liter pack for weekend hiking trips", 22, [], ["Sage","Navy"], ["backpack","35l","weekend","hiking"]),
    ("BAG-003", "Expedition Pack 50L", "TrailForge", "gear", "backpacks", "unisex", 179.00, "Adjustable 50-liter backpack for multi-day trips", 11, [], ["Rust","Black"], ["backpack","50l","backpacking","multi-day"]),
    ("HAT-001", "Wide-Brim Sun Hat", "Canyon Works", "apparel", "hats", "unisex", 29.00, "UPF 50 wide-brim hat with adjustable chin strap", 31, ["S/M","L/XL"], ["Sand","Sage"], ["sun hat","hiking","upf","summer"]),
    ("HAT-002", "Alpine Merino Beanie", "WoolPath", "apparel", "hats", "unisex", 27.00, "Warm merino beanie for cold mornings", 44, [], ["Plum","Charcoal"], ["beanie","winter","merino","warm"]),
    ("ACC-001", "Carbon Trekking Poles", "TrailForge", "gear", "trekking poles", "unisex", 89.00, "Collapsible carbon trekking poles with cork grips", 23, [], ["Black"], ["trekking poles","hiking","backpacking","carbon"]),
    ("ACC-002", "Trail Headlamp 450", "CampSpark", "gear", "lighting", "unisex", 39.00, "Rechargeable 450-lumen headlamp with red-light mode", 53, [], ["Mint","Black"], ["headlamp","camping","lighting","hiking"]),
    ("ACC-003", "Insulated Bottle 750ml", "HydraPeak", "gear", "hydration", "unisex", 32.00, "Vacuum-insulated stainless bottle with leakproof cap", 68, [], ["Rose","Blue","Black"], ["bottle","hydration","water","hiking"]),
    ("ACC-004", "Compact First Aid Kit", "CampSpark", "gear", "safety", "unisex", 28.00, "Trail-ready first aid kit for day hikes", 47, [], ["Red"], ["first aid","safety","hiking","emergency"]),
    ("ACC-005", "Microspike Traction Set", "PeakLine", "gear", "traction", "unisex", 59.00, "Steel traction spikes for icy trails", 18, ["S","M","L","XL"], ["Black"], ["microspikes","ice","winter","traction"]),
    ("ACC-006", "Packable Rain Cover", "PackWorks", "gear", "backpack accessories", "unisex", 22.00, "Waterproof rain cover for 20-40L backpacks", 39, [], ["Orange","Black"], ["rain cover","backpack","waterproof"]),
    ("ACC-007", "Polarized Trail Sunglasses", "SunLine", "accessories", "sunglasses", "unisex", 54.00, "Polarized UV400 sunglasses with impact-resistant lenses", 35, [], ["Black","Tortoise"], ["sunglasses","polarized","sun","hiking"]),
    ("ACC-008", "Photochromic Summit Sunglasses", "SunLine", "accessories", "sunglasses", "unisex", 89.00, "Photochromic lenses that adapt to changing light", 16, [], ["Gray"], ["sunglasses","photochromic","mountain","hiking"]),
    ("CAM-001", "TrailCam 4K Action Camera", "VistaGo", "electronics", "cameras", "unisex", 149.00, "Waterproof stabilized 4K action camera", 15, [], ["Black"], ["camera","4k","waterproof","outdoor"]),
    ("PWR-001", "Adventure Power Bank 20000", "VoltTrail", "electronics", "power", "unisex", 49.00, "Rugged USB-C power bank with weather-resistant shell", 40, [], ["Black","Orange"], ["power bank","usb-c","camping","outdoor"]),
    ("GPS-001", "TrailNav GPS Mini", "VistaGo", "electronics", "navigation", "unisex", 229.00, "Compact handheld GPS with offline topographic maps", 9, [], ["Orange"], ["gps","navigation","hiking","maps"]),
    ("FIT-001", "Recovery Foam Roller", "MotionPeak", "fitness", "recovery", "unisex", 34.00, "Textured foam roller for post-hike recovery", 41, [], ["Lavender","Black"], ["recovery","foam roller","fitness"]),
    ("FIT-002", "Travel Yoga Mat", "MotionPeak", "fitness", "yoga", "unisex", 38.00, "Foldable non-slip yoga mat for travel", 32, [], ["Mint","Lilac"], ["yoga","mat","travel","fitness"]),
    ("SWM-001", "Women’s Trail Swim Top", "RiverLine", "apparel", "swimwear", "women", 48.00, "Supportive quick-dry swim top for lake and river trips", 20, ["XS","S","M","L","XL"], ["Teal","Rose"], ["women","swimwear","quick dry","water"]),
    ("SWM-002", "Women’s High-Waist Swim Bottom", "RiverLine", "apparel", "swimwear", "women", 42.00, "High-waist swim bottom with secure trail-to-water fit", 23, ["XS","S","M","L","XL"], ["Teal","Black"], ["women","swimwear","water"]),
    ("SWM-003", "Men’s Adventure Swim Shorts", "RiverLine", "apparel", "swimwear", "men", 46.00, "Quick-dry swim shorts with zip security pocket", 26, ["S","M","L","XL"], ["Navy","Coral"], ["men","swimwear","quick dry","water"]),
]

SEED_PROMOTIONS = [
    ("OUTDOOR20", "apparel", None, 20.0, "20% off apparel", 1),
    ("TRAIL15", "footwear", None, 15.0, "15% off hiking footwear", 1),
    ("PACK10", "gear", "backpacks", 10.0, "10% off backpacks", 1),
    ("SUN12", "accessories", "sunglasses", 12.0, "12% off sunglasses", 1),
    ("TECH10", "electronics", None, 10.0, "10% off outdoor electronics", 1),
]


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return {row["name"] for row in cur.fetchall()}


def _add_column(cur: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
    if column not in _columns(cur, table):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT, name TEXT NOT NULL, brand TEXT,
            category TEXT NOT NULL, subcategory TEXT, gender TEXT,
            price_usd REAL NOT NULL, description TEXT NOT NULL, stock INTEGER NOT NULL,
            sizes_json TEXT, colors_json TEXT, tags_json TEXT
        )
    """)
    for col, ddl in [
        ("sku", "TEXT"), ("brand", "TEXT"), ("subcategory", "TEXT"),
        ("gender", "TEXT"), ("sizes_json", "TEXT"), ("colors_json", "TEXT"),
        ("tags_json", "TEXT")
    ]:
        _add_column(cur, "products", col, ddl)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS promotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL, category TEXT, subcategory TEXT,
            discount_pct REAL NOT NULL, description TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)
    _add_column(cur, "promotions", "subcategory", "TEXT")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cart_items (
            session_id TEXT NOT NULL, product_name TEXT NOT NULL, quantity INTEGER NOT NULL,
            PRIMARY KEY (session_id, product_name)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            items_json TEXT NOT NULL, subtotal_usd REAL NOT NULL,
            discount_usd REAL NOT NULL, total_usd REAL NOT NULL,
            promo_code TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY, input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0, dollars_spent REAL NOT NULL DEFAULT 0.0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trace_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            step_type TEXT NOT NULL, label TEXT NOT NULL, model TEXT,
            input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0.0, latency_ms REAL NOT NULL DEFAULT 0.0,
            details_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _add_column(cur, "trace_steps", "details_json", "TEXT")

    cur.execute("SELECT value FROM app_metadata WHERE key='catalog_version'")
    row = cur.fetchone()
    if row is None or row["value"] != CATALOG_VERSION:
        cur.execute("DELETE FROM products")
        cur.execute("DELETE FROM promotions")
        cur.executemany("""
            INSERT INTO products
            (sku, name, brand, category, subcategory, gender, price_usd, description, stock,
             sizes_json, colors_json, tags_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [p[:-3] + (json.dumps(p[-3]), json.dumps(p[-2]), json.dumps(p[-1])) for p in SEED_PRODUCTS])
        cur.executemany("""
            INSERT INTO promotions
            (code, category, subcategory, discount_pct, description, active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, SEED_PROMOTIONS)
        cur.execute("INSERT OR REPLACE INTO app_metadata(key,value) VALUES('catalog_version',?)", (CATALOG_VERSION,))

    conn.commit()
    conn.close()


def _normalize(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _product_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["sizes"] = json.loads(item.pop("sizes_json") or "[]")
    item["colors"] = json.loads(item.pop("colors_json") or "[]")
    item["tags"] = json.loads(item.pop("tags_json") or "[]")
    return item


def list_categories() -> dict[str, list[str]]:
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT DISTINCT category, subcategory FROM products ORDER BY category, subcategory")
    facets: dict[str, list[str]] = {}
    for row in cur.fetchall():
        facets.setdefault(row["category"], []).append(row["subcategory"])
    conn.close()
    return facets


def search_products(
    query: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    brand: str | None = None,
    gender: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    size: str | None = None,
    use_case: str | None = None,
    limit: int | None = 8,
) -> list[dict[str, Any]]:
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT * FROM products")
    products = [_product_dict(r) for r in cur.fetchall()]
    conn.close()

    q_tokens = set(_normalize(" ".join(filter(None, [query, use_case]))).split())
    category_n, subcategory_n = _normalize(category), _normalize(subcategory)
    brand_n, gender_n, size_n = _normalize(brand), _normalize(gender), _normalize(size)
    ranked: list[tuple[float, dict[str, Any]]] = []

    for p in products:
        if category_n and category_n not in _normalize(p["category"]):
            continue
        if subcategory_n and subcategory_n not in _normalize(p["subcategory"]):
            continue
        if brand_n and brand_n not in _normalize(p["brand"]):
            continue
        if gender_n and p["gender"] not in {"unisex", gender_n}:
            continue
        if min_price is not None and p["price_usd"] < min_price:
            continue
        if max_price is not None and p["price_usd"] > max_price:
            continue
        if size_n and size_n not in {_normalize(s) for s in p["sizes"]}:
            continue

        haystack = _normalize(" ".join([
            p["name"], p["brand"], p["category"], p["subcategory"], p["description"],
            " ".join(p["tags"]), " ".join(p["colors"]),
        ]))
        hay_tokens = set(haystack.split())
        if q_tokens:
            overlap = len(q_tokens & hay_tokens) / max(len(q_tokens), 1)
            phrase = 1.0 if _normalize(query) and _normalize(query) in haystack else 0.0
            fuzzy = SequenceMatcher(None, _normalize(query), _normalize(p["name"])).ratio() if query else 0.0
            score = overlap * 6 + phrase * 4 + fuzzy * 2
            if score < 0.8:
                continue
        else:
            score = 1.0
        if p["stock"] > 0:
            score += 0.2
        ranked.append((score, p))

    ranked.sort(key=lambda pair: (-pair[0], pair[1]["price_usd"]))
    return [p for _, p in ranked[: (limit or 50)]]


def resolve_product(product_name: str) -> dict[str, Any] | None:
    conn = get_connection(); cur = conn.cursor(); cur.execute("SELECT * FROM products")
    products = [_product_dict(r) for r in cur.fetchall()]; conn.close()
    target = _normalize(product_name)
    exact = next((p for p in products if _normalize(p["name"]) == target or _normalize(p["sku"]) == target), None)
    if exact:
        return exact
    target_tokens = set(target.split())
    scored = []
    for p in products:
        name_n = _normalize(p["name"])
        overlap = len(target_tokens & set(name_n.split())) / max(len(target_tokens), 1)
        ratio = SequenceMatcher(None, target, name_n).ratio()
        scored.append((overlap * 0.65 + ratio * 0.35, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] >= 0.48 else None


def check_inventory(product_name: str, size: str | None = None) -> dict[str, Any]:
    p = resolve_product(product_name)
    if not p:
        return {"found": False, "error": f"No catalog product closely matches '{product_name}'."}
    size_available = True
    if size and p["sizes"]:
        size_available = _normalize(size) in {_normalize(s) for s in p["sizes"]}
    return {
        "found": True, "matched_product": p["name"], "sku": p["sku"],
        "stock": p["stock"], "in_stock": p["stock"] > 0 and size_available,
        "requested_size": size, "size_available": size_available,
        "available_sizes": p["sizes"], "price_usd": p["price_usd"],
    }


def get_promotions(category: str | None = None, subcategory: str | None = None, product_name: str | None = None) -> list[dict[str, Any]]:
    if product_name:
        product = resolve_product(product_name)
        if product:
            category = product["category"]; subcategory = product["subcategory"]
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT code, category, subcategory, discount_pct, description FROM promotions WHERE active=1")
    promos = [dict(r) for r in cur.fetchall()]; conn.close()
    results = []
    for promo in promos:
        if category and promo["category"] and _normalize(promo["category"]) != _normalize(category):
            continue
        if promo["subcategory"] and subcategory and _normalize(promo["subcategory"]) != _normalize(subcategory):
            continue
        results.append(promo)
    return results


def _best_promotion(category: str, subcategory: str | None = None) -> dict[str, Any] | None:
    promos = get_promotions(category=category, subcategory=subcategory)
    return max(promos, key=lambda p: p["discount_pct"], default=None)


def update_cart(session_id: str, product_name: str, quantity: int, action: str = "add") -> dict[str, Any]:
    p = resolve_product(product_name)
    if not p:
        return {"success": False, "error": f"No catalog product closely matches '{product_name}'."}
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT quantity FROM cart_items WHERE session_id=? AND product_name=?", (session_id, p["name"]))
    row = cur.fetchone(); current = row["quantity"] if row else 0
    new_qty = current + quantity if action == "add" else max(current - quantity, 0) if action == "remove" else quantity
    if new_qty > p["stock"]:
        conn.close(); return {"success": False, "error": f"Only {p['stock']} units of {p['name']} are available."}
    if new_qty <= 0:
        cur.execute("DELETE FROM cart_items WHERE session_id=? AND product_name=?", (session_id, p["name"]))
    elif row:
        cur.execute("UPDATE cart_items SET quantity=? WHERE session_id=? AND product_name=?", (new_qty, session_id, p["name"]))
    else:
        cur.execute("INSERT INTO cart_items(session_id,product_name,quantity) VALUES(?,?,?)", (session_id, p["name"], new_qty))
    conn.commit(); conn.close()
    return {"success": True, "matched_product": p["name"], "cart": get_cart(session_id)}


def get_cart(session_id: str) -> list[dict[str, Any]]:
    conn = get_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT c.product_name, c.quantity, p.price_usd, p.category, p.subcategory
        FROM cart_items c JOIN products p ON p.name=c.product_name
        WHERE c.session_id=? ORDER BY c.product_name
    """, (session_id,))
    rows = [dict(r) for r in cur.fetchall()]; conn.close()
    for row in rows:
        row["line_total_usd"] = round(row["price_usd"] * row["quantity"], 2)
    return rows


def checkout(session_id: str) -> dict[str, Any]:
    cart = get_cart(session_id)
    if not cart:
        return {"success": False, "error": "Cart is empty"}
    subtotal = round(sum(i["line_total_usd"] for i in cart), 2)
    best = None
    for item in cart:
        promo = _best_promotion(item["category"], item["subcategory"])
        if promo and (best is None or promo["discount_pct"] > best["discount_pct"]):
            best = promo
    discount = round(subtotal * ((best or {}).get("discount_pct", 0) / 100), 2)
    total = round(subtotal - discount, 2)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO orders(session_id,items_json,subtotal_usd,discount_usd,total_usd,promo_code) VALUES(?,?,?,?,?,?)",
                (session_id, json.dumps(cart), subtotal, discount, total, best["code"] if best else None))
    cur.execute("DELETE FROM cart_items WHERE session_id=?", (session_id,)); conn.commit(); order_id = cur.lastrowid; conn.close()
    return {"success": True, "order_id": order_id, "items": cart, "subtotal_usd": subtotal,
            "discount_usd": discount, "total_usd": total, "promo_code": best["code"] if best else None}
