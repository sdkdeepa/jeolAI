from backend.guardrails import evaluate_request


def test_programming_request_is_blocked():
    result = evaluate_request("How do I reverse a string in Python?")
    assert result.allowed is False


def test_product_search_is_allowed():
    result = evaluate_request("Find me a rain jacket under $100")
    assert result.allowed is True


def test_cart_request_is_allowed():
    result = evaluate_request("Add the rain jacket to my cart")
    assert result.allowed is True
