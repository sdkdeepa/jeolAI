# JeolAI Testing Guide

JeolAI uses layered testing to validate deterministic commerce rules, conversational behavior, guardrails, budget policies, and end-to-end user flows.

The core testing principle is simple:

> The LLM handles conversation, but deterministic backend logic owns commerce correctness.

## Run Tests

### Run all backend tests

```bash
source .venv/bin/activate
PYTHONPATH=. pytest -v
```

### Run a specific test suite

```bash
PYTHONPATH=. pytest -v tests/test_budget.py
PYTHONPATH=. pytest -v tests/test_guardrails.py
PYTHONPATH=. pytest -v tests/test_product_variants.py
PYTHONPATH=. pytest -v tests/test_variant_conversation.py
```

### Run Playwright E2E tests

```bash
npx playwright test
```

Run with the browser visible:

```bash
npx playwright test --headed
```

---

## 1. Budget Policy Tests

**File:** `tests/test_budget.py`

| Test Scenario | What It Validates |
|---|---|
| Configured model rates | Model cost is calculated using the configured token pricing. |
| Unknown model | Unsupported model names fail explicitly instead of silently producing incorrect cost estimates. |

---

## 2. Domain Guardrail Tests

**File:** `tests/test_guardrails.py`

| Test Scenario | Example | Expected Behavior |
|---|---|---|
| Programming request | `How do I reverse a string in Python?` | Blocked before model invocation. |
| Product search | `Find me a rain jacket under $100` | Allowed as commerce intent. |
| Cart request | `Add the rain jacket to my cart` | Allowed as commerce intent. |
| Decimal/width size follow-up | Assistant asks for size → `10.5 wide` | Allowed as a contextual shopping follow-up. |
| Numeric size follow-up | Assistant asks for size → `10` | Allowed as a contextual shopping follow-up. |
| Apparel size follow-up | Assistant asks for size → `Large` | Allowed as a contextual shopping follow-up. |
| Size without context | `10.5 wide` with no preceding size question | Blocked because there is no established commerce context. |
| Off-domain request during size flow | Assistant asks for size → `How do I reverse a string in Python?` | Still blocked. Shopping context does not disable the guardrail. |

### Why this matters

Short answers such as `10`, `Large`, or `10.5 wide` may not contain standalone shopping keywords. The guardrail uses conversation context to recognize them as valid responses when JeolAI has explicitly asked for a size.

Explicit off-domain requests remain blocked.

---

## 3. Product Variant and Cart Tests

**File:** `tests/test_product_variants.py`

| Test Scenario | What It Validates |
|---|---|
| Sized product without size | A product requiring a size cannot be added without one. Returns `needs_input`, identifies `size` as missing, provides available sizes, and leaves the cart unchanged. |
| Sized product with valid size | An in-stock size can be added and the selected size is persisted with the cart item. |
| Deterministic cart subtotal | Product price and line total come from backend/catalog data rather than LLM-generated arithmetic. |
| Multiple line-item subtotal | Backend correctly calculates the subtotal across multiple cart items. |
| Invalid size | A size that does not exist for the product is rejected and the cart remains unchanged. |
| Out-of-stock size | A valid size with zero inventory is rejected and the cart remains unchanged. |
| One-size product | Products that do not require size can be added normally without `selected_size`. |
| Checkout with missing variant | Checkout rejects a sized product that somehow reaches the cart without a selected size. |
| Variant becomes unavailable | If a selected size becomes unavailable after being added, checkout fails and the cart is preserved. |

### Defense in Depth

Variant validation happens at multiple boundaries:

| Boundary | Protection |
|---|---|
| Add to cart | Prevents creation of an invalid cart item. |
| Inventory validation | Prevents unavailable variants from being added. |
| Cart persistence | Stores the selected product variant. |
| Checkout | Revalidates the cart before order creation. |

This ensures that even if the conversational flow, model, or another API client behaves incorrectly, an invalid cart cannot produce an order.

---

## 4. Multi-Turn Conversation Tests

**File:** `tests/test_variant_conversation.py`

| Test Scenario | Conversation | Expected Behavior |
|---|---|---|
| Product requires size | `Add Summit GTX to my cart` | Assistant asks for size and cart remains unchanged. |
| User supplies requested size | `Size 10` | Previous product context is preserved and Summit GTX size 10 is added. |
| Show cart after variant selection | `Show me my cart` | Response identifies both Summit GTX and selected size 10. |
| Contextual decimal/width response | Assistant asks for size → `10.5 wide` | Domain guardrail allows the request to reach the shopping flow rather than incorrectly classifying it as off-domain. |
| Invalid contextual variant | `10.5 wide` when 10.5 is unavailable | Product validation can reject the unavailable size even though the domain guard correctly allows the conversational turn. |

### Important distinction

These tests validate two separate layers:

| Layer | Responsibility |
|---|---|
| Domain guardrail | Determines whether the message belongs to the shopping conversation. |
| Product validation | Determines whether the requested product option is actually valid and available. |

For example, `10.5 wide` may be a perfectly valid **shopping message** while still being an **invalid product variant** for a particular product.

---

## 5. Playwright End-to-End Tests

**File:** `e2e/jeolai.spec.js`

| Test Scenario | What It Validates |
|---|---|
| Sized product variant flow | Browser conversation requires the user to select a variant before the product is added. |
| Missing size | UI does not falsely indicate that a sized product was added before size selection. |
| Size selection | User can provide the requested size in the next conversational turn. |
| Cart display | Browser-visible cart response contains the product and selected size. |
| Checkout regression | Sized products cannot proceed through checkout without their required variant. |

Example E2E flow:

```text
User: Add Summit GTX to my cart.

Assistant: What size would you like?

User: Size 10

Assistant: Summit GTX size 10 was added.

User: Show me my cart.

Assistant: Summit GTX Hiking Boots, Size 10
```

---

## Test Coverage Summary

| Test Type | File | Primary Responsibility |
|---|---|---|
| Unit | `tests/test_budget.py` | Model cost and budget-policy correctness |
| Unit | `tests/test_guardrails.py` | Deterministic domain classification and contextual follow-ups |
| Unit / Backend | `tests/test_product_variants.py` | Product variants, inventory, cart pricing, and checkout validation |
| API / Integration | `tests/test_variant_conversation.py` | Multi-turn conversational state and backend interaction |
| Browser E2E | `e2e/jeolai.spec.js` | Complete user-visible shopping workflow |

---

## Regression Testing Strategy

Several tests in JeolAI originated from issues discovered during workshop and manual testing.

| Regression | Protection Added |
|---|---|
| Sized product could be added without selecting a size | Deterministic add-to-cart variant validation |
| Cart could contain a sized product without its variant | Checkout defense-in-depth validation |
| Product variant could become unavailable before checkout | Checkout inventory revalidation |
| Incorrect cart subtotal could be presented | Backend-owned deterministic subtotal calculation |
| `10.5 wide` was incorrectly treated as off-domain | Context-aware deterministic guardrail |
| Short responses such as `10` or `Large` could be ambiguous | Contextual size-follow-up recognition |

When a functional bug is discovered:

1. Reproduce the failure.
2. Add a regression test.
3. Fix the deterministic layer responsible for the failure.
4. Run the affected test suite.
5. Run the complete backend and E2E suites.
6. Keep the regression test permanently.

---

## Before Pushing Changes

Run:

```bash
PYTHONPATH=. pytest -v
```

Then:

```bash
npx playwright test
```

All tests should pass before merging or publishing workshop updates.