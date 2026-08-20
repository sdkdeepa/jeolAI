import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "GOOGLE_CLOUD_PROJECT",
    "test-project",
)

from backend import db  # noqa: E402
from backend import main  # noqa: E402


@pytest.fixture
def client(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        db,
        "DB_PATH",
        tmp_path / "shop_agent.db",
    )

    db.init_db()

    main._conversations.clear()
    main._pending_approvals.clear()
    main._chat_history.clear()
    main._session_started_at.clear()

    pending_product = {}

    def fake_run_turn(
        session_id,
        model,
        conversation,
    ):
        latest = (
            main._chat_history[
                session_id
            ][-1]["message"]
        )

        lower = (
            latest
            .lower()
            .strip()
            .rstrip(".")
        )

        if (
            "find waterproof hiking boots"
            in lower
        ):
            reply = (
                "I found Summit GTX Hiking Boots "
                "for $159."
            )

        elif "add summit gtx" in lower:
            result = db.update_cart(
                session_id,
                "Summit GTX",
                1,
                "add",
            )

            assert (
                result["status"]
                == "needs_input"
            )

            pending_product[
                session_id
            ] = result["matched_product"]

            reply = (
                "What size would you like? "
                "Available sizes are "
                + ", ".join(
                    result["available_sizes"]
                )
                + "."
            )

        elif lower == "size 10":
            result = db.update_cart(
                session_id,
                pending_product[
                    session_id
                ],
                1,
                "add",
                size="10",
            )

            assert result["success"] is True

            pending_product.pop(
                session_id,
                None,
            )

            reply = (
                "Summit GTX Hiking Boots "
                "size 10 was added to your cart."
            )

        elif "show me my cart" in lower:
            cart = db.get_cart(
                session_id
            )

            item = cart["items"][0]

            reply = (
                f"{item['product_name']} "
                f"size {item['selected_size']}"
            )

        elif (
            "add alpine trek"
            in lower
        ):
            result = db.update_cart(
                session_id,
                "Alpine Trek Women’s Boot",
                1,
                "add",
            )

            assert (
                result["status"]
                == "needs_input"
            )

            pending_product[
                session_id
            ] = result["matched_product"]

            reply = (
                "What size would you like for "
                "the Alpine Trek Women's Boot?"
            )

        elif lower == "10.5 wide":
            # The important regression here is that this turn
            # reaches the agent instead of being stopped by the
            # deterministic domain guardrail.
            #
            # 10.5 is not currently a valid catalog size for this
            # demo product, so the backend should reject the
            # variant normally rather than the guardrail treating
            # the message as off-domain.
            result = db.update_cart(
                session_id,
                pending_product[
                    session_id
                ],
                1,
                "add",
                size="10.5",
            )

            assert result["success"] is False
            assert (
                result["status"]
                == "invalid_variant"
            )

            reply = (
                "Size 10.5 is not available for "
                "the Alpine Trek Women's Boot. "
                "Please choose one of the "
                "available sizes."
            )

        else:
            raise AssertionError(
                f"Unexpected test message: {latest}"
            )

        return {
            "status": "complete",
            "text": reply,
            "messages": conversation,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    monkeypatch.setattr(
        main,
        "run_turn",
        fake_run_turn,
    )

    return TestClient(
        main.app
    )


def test_sized_product_conversation_requires_variant_before_cart_mutation(
    client,
):
    session_id = (
        "variant-conversation"
    )

    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": (
                "Find waterproof hiking boots "
                "under $170."
            ),
        },
    )

    assert response.status_code == 200
    assert (
        "Summit GTX"
        in response.json()["reply"]
    )

    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": (
                "Add Summit GTX to my cart."
            ),
        },
    )

    assert response.status_code == 200
    assert (
        "What size"
        in response.json()["reply"]
    )

    cart = db.get_cart(
        session_id
    )

    assert cart["items"] == []
    assert cart["subtotal_usd"] == 0

    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "Size 10",
        },
    )

    assert response.status_code == 200

    assert (
        "size 10"
        in response.json()["reply"]
    )

    cart = db.get_cart(
        session_id
    )

    assert len(
        cart["items"]
    ) == 1

    assert (
        cart["items"][0]["product_name"]
        == "Summit GTX Hiking Boots"
    )

    assert (
        cart["items"][0]["selected_size"]
        == "10"
    )

    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "Show me my cart.",
        },
    )

    assert response.status_code == 200

    assert (
        "Summit GTX Hiking Boots"
        in response.json()["reply"]
    )

    assert (
        "10"
        in response.json()["reply"]
    )


def test_decimal_wide_size_followup_is_not_blocked_by_domain_guard(
    client,
):
    """
    Regression for the browser bug:

        User:
        Add Alpine Trek Women's Boot

        Assistant:
        What size would you like?

        User:
        10.5 wide

    "10.5 wide" is ambiguous when viewed by itself, but it is
    clearly a commerce continuation when JeolAI just asked for
    the product size.

    The domain guardrail must allow the turn to reach the agent.

    The catalog currently does not offer size 10.5 for this
    product, so the deterministic product-option validation may
    reject the requested variant. That is correct and is a
    separate concern from domain classification.
    """
    session_id = (
        "wide-size-followup"
    )

    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": (
                "Add Alpine Trek Women's Boot"
            ),
        },
    )

    assert response.status_code == 200

    first_body = response.json()

    assert (
        first_body["domain_allowed"]
        is True
    )

    assert (
        "size"
        in first_body[
            "reply"
        ].lower()
    )

    # Missing size must not mutate the cart.
    cart = db.get_cart(
        session_id
    )

    assert cart["items"] == []

    response = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "10.5 wide",
        },
    )

    assert response.status_code == 200

    second_body = (
        response.json()
    )

    # This is the actual regression assertion.
    # Before the fix this value was False.
    assert (
        second_body[
            "domain_allowed"
        ]
        is True
    )

    blocked_reply = (
        "i don’t know. i can only help "
        "with shopping"
    )

    assert (
        blocked_reply
        not in second_body[
            "reply"
        ].lower()
    )

    assert (
        "10.5"
        in second_body["reply"]
    )

    # 10.5 is not a catalog size, so deterministic validation
    # should still prevent an invalid cart mutation.
    cart = db.get_cart(
        session_id
    )

    assert cart["items"] == []