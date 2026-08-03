from backend import budget


def test_estimate_cost_uses_configured_rates():
    model = budget.DEFAULT_MODEL
    rates = budget.MODEL_RATES[model]
    expected = rates["input"] + rates["output"]
    assert budget.estimate_cost(model, 1_000_000, 1_000_000) == expected


def test_unknown_model_fails_explicitly():
    try:
        budget.estimate_cost("unknown-model", 10, 10)
    except ValueError as exc:
        assert "No pricing configuration" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
