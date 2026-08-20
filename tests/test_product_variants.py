import json

import pytest

from backend import db


@pytest.fixture(autouse=True)
def clean_database():
    conn = db.get_connection()
    conn.execute("DELETE FROM cart_items")
    conn.execute("DELETE FROM orders")
    conn.commit()
    conn.close()

    db.init_db()

    yield

    conn = db.get_connection()
    conn.execute("DELETE FROM cart_items")
    conn.execute("DELETE FROM orders")
    conn.commit()
    conn.close()


def test_sized_product_requires_size_and_does_not_mutate_cart():
    result = db.update_cart(
        "s1",
        "Summit GTX",
        1,
        "add",
    )

    assert result["success"] is False
    assert result["status"] == "needs_input"
    assert result["missing_fields"] == ["size"]
    assert "10" in result["available_sizes"]

    cart = db.get_cart("s1")

    assert cart["items"] == []
    assert cart["item_count"] == 0
    assert cart["subtotal_usd"] == 0


def test_sized_product_with_in_stock_size_is_persisted():
    result = db.update_cart(
        "s2",
        "Summit GTX",
        1,
        "add",
        size="10",
    )

    assert result["success"] is True

    cart = db.get_cart("s2")

    assert len(cart["items"]) == 1

    item = cart["items"][0]

    assert item["product_name"] == "Summit GTX Hiking Boots"
    assert item["selected_size"] == "10"
    assert item["price_usd"] == 159.0
    assert item["line_total_usd"] == 159.0

    assert cart["item_count"] == 1
    assert cart["subtotal_usd"] == 159.0


def test_cart_subtotal_is_calculated_deterministically():
    session_id = "test-cart-subtotal"

    result = db.update_cart(
        session_id=session_id,
        product_name="Merino Base Layer Top",
        quantity=1,
        action="add",
        size="L",
    )

    assert result["success"] is True

    cart = db.get_cart(session_id)

    assert len(cart["items"]) == 1

    item = cart["items"][0]

    assert item["product_name"] == "Merino Base Layer Top"
    assert item["selected_size"] == "L"
    assert item["price_usd"] == 58.0
    assert item["line_total_usd"] == 58.0

    assert cart["subtotal_usd"] == 58.0


def test_invalid_or_unavailable_size_is_rejected_without_cart_mutation():
    invalid = db.update_cart(
        "s3",
        "Summit GTX",
        1,
        "add",
        size="99",
    )

    assert invalid["success"] is False
    assert invalid["status"] == "invalid_variant"

    cart = db.get_cart("s3")

    assert cart["items"] == []
    assert cart["subtotal_usd"] == 0

    product = db.resolve_product("Summit GTX")

    # Save original inventory so this test does not affect later tests.
    original_inventory = product["size_inventory"].copy()

    try:
        inventory = product["size_inventory"].copy()
        inventory["10"] = 0

        conn = db.get_connection()

        conn.execute(
            """
            UPDATE products
            SET size_inventory_json=?
            WHERE name=?
            """,
            (
                json.dumps(inventory),
                product["name"],
            ),
        )

        conn.commit()
        conn.close()

        unavailable = db.update_cart(
            "s3",
            "Summit GTX",
            1,
            "add",
            size="10",
        )

        assert unavailable["success"] is False
        assert unavailable["status"] == "out_of_stock"

        cart = db.get_cart("s3")

        assert cart["items"] == []
        assert cart["subtotal_usd"] == 0

    finally:
        # Restore catalog inventory for subsequent tests.
        conn = db.get_connection()

        conn.execute(
            """
            UPDATE products
            SET size_inventory_json=?
            WHERE name=?
            """,
            (
                json.dumps(original_inventory),
                product["name"],
            ),
        )

        conn.commit()
        conn.close()


def test_cart_subtotal_sums_multiple_line_items():
    session_id = "test-multi-item-subtotal"

    first = db.update_cart(
        session_id=session_id,
        product_name="Merino Base Layer Top",
        quantity=1,
        action="add",
        size="L",
    )

    assert first["success"] is True

    second = db.update_cart(
        session_id=session_id,
        product_name="Trail Daypack 20L",
        quantity=1,
        action="add",
    )

    assert second["success"] is True

    cart = db.get_cart(session_id)

    assert len(cart["items"]) == 2
    assert cart["subtotal_usd"] == 127.0


def test_one_size_product_can_be_added_without_size():
    product = db.resolve_product(
        "Trail Daypack 20L"
    )

    assert product["requires_size"] is False
    assert product["one_size"] is True

    result = db.update_cart(
        "s4",
        "Trail Daypack 20L",
        1,
        "add",
    )

    assert result["success"] is True

    cart = db.get_cart("s4")

    assert len(cart["items"]) == 1
    assert cart["items"][0]["selected_size"] is None
    assert cart["items"][0]["product_name"] == "Trail Daypack 20L"
    assert cart["subtotal_usd"] == 69.0


def test_checkout_rejects_sized_item_missing_selected_variant_before_order_creation():
    conn = db.get_connection()

    conn.execute(
        """
        INSERT INTO cart_items(
            session_id,
            product_name,
            quantity,
            selected_size
        )
        VALUES(?,?,?,NULL)
        """,
        (
            "s5",
            "Summit GTX Hiking Boots",
            1,
        ),
    )

    conn.commit()
    conn.close()

    result = db.checkout("s5")

    assert result["success"] is False
    assert result["status"] == "invalid_cart"
    assert result["missing_fields"] == ["size"]

    cart = db.get_cart("s5")

    assert len(cart["items"]) == 1
    assert cart["items"][0]["selected_size"] is None

    # Checkout failure must preserve the cart.
    assert cart["subtotal_usd"] == 159.0


def test_checkout_rejects_variant_that_becomes_unavailable():
    added = db.update_cart(
        "s6",
        "Summit GTX",
        1,
        "add",
        size="10",
    )

    assert added["success"] is True

    product = db.resolve_product("Summit GTX")

    original_inventory = product["size_inventory"].copy()

    try:
        inventory = product["size_inventory"].copy()
        inventory["10"] = 0

        conn = db.get_connection()

        conn.execute(
            """
            UPDATE products
            SET size_inventory_json=?
            WHERE name=?
            """,
            (
                json.dumps(inventory),
                product["name"],
            ),
        )

        conn.commit()
        conn.close()

        result = db.checkout("s6")

        assert result["success"] is False
        assert result["status"] == "invalid_cart"

        cart = db.get_cart("s6")

        assert len(cart["items"]) == 1

        item = cart["items"][0]

        assert item["product_name"] == "Summit GTX Hiking Boots"
        assert item["selected_size"] == "10"
        assert cart["item_count"] == 1
        assert cart["subtotal_usd"] == 159.0

    finally:
        # Restore catalog inventory for subsequent tests.
        conn = db.get_connection()

        conn.execute(
            """
            UPDATE products
            SET size_inventory_json=?
            WHERE name=?
            """,
            (
                json.dumps(original_inventory),
                product["name"],
            ),
        )

        conn.commit()
        conn.close()
        