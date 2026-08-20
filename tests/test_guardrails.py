from backend.guardrails import evaluate_request


def test_programming_request_is_blocked():
    result = evaluate_request(
        "How do I reverse a string in Python?"
    )

    assert result.allowed is False


def test_product_search_is_allowed():
    result = evaluate_request(
        "Find me a rain jacket under $100"
    )

    assert result.allowed is True


def test_cart_request_is_allowed():
    result = evaluate_request(
        "Add the rain jacket to my cart"
    )

    assert result.allowed is True


def test_decimal_wide_size_followup_is_allowed_after_size_question():
    history = [
        {
            "role": "user",
            "message": "Add Alpine Trek Women's Boot",
        },
        {
            "role": "assistant",
            "message": (
                "What size would you like for "
                "the Alpine Trek Women's Boot?"
            ),
        },
    ]

    result = evaluate_request(
        "10.5 wide",
        history=history,
    )

    assert result.allowed is True
    assert result.matched_signal == "size_followup"


def test_numeric_size_followup_is_allowed_after_size_question():
    history = [
        {
            "role": "user",
            "message": "Add Summit GTX to my cart",
        },
        {
            "role": "assistant",
            "message": "What size would you like?",
        },
    ]

    result = evaluate_request(
        "10",
        history=history,
    )

    assert result.allowed is True
    assert result.matched_signal == "size_followup"


def test_apparel_size_followup_is_allowed_after_size_question():
    history = [
        {
            "role": "user",
            "message": "Add Merino Base Layer Top",
        },
        {
            "role": "assistant",
            "message": (
                "What size would you like for "
                "the Merino Base Layer Top?"
            ),
        },
    ]

    result = evaluate_request(
        "Large",
        history=history,
    )

    assert result.allowed is True
    assert result.matched_signal == "size_followup"


def test_size_like_message_without_context_is_not_automatically_allowed():
    result = evaluate_request(
        "10.5 wide"
    )

    assert result.allowed is False


def test_explicit_off_domain_request_remains_blocked_during_size_followup():
    history = [
        {
            "role": "user",
            "message": "Add Summit GTX to my cart",
        },
        {
            "role": "assistant",
            "message": "What size would you like?",
        },
    ]

    result = evaluate_request(
        "How do I reverse a string in Python?",
        history=history,
    )

    assert result.allowed is False
    assert result.matched_signal == "programming"