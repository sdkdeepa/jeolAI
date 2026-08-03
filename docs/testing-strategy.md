# Testing Strategy

## Objectives

Testing must validate deterministic business behavior, agent-tool integration, policy enforcement, and the operational signals used to govern the system.

## Unit tests

- Token-cost estimation for every configured model
- Budget tier transitions at exact boundaries
- Model routing before and after the warning threshold
- Search-result caps after policy downgrade
- Checkout approval requirements
- Product search, inventory, promotion, cart, and checkout behavior
- Trace persistence and aggregation

## API integration tests

Use FastAPI's test client with the Gemini client mocked. Validate:

- Chat request and response contracts
- Conversation-state updates
- Approval creation and resolution
- Budget and trace endpoints
- Health response
- Error behavior when no approval is pending

## Agent tests

Create a golden set of user tasks such as:

- Find the least expensive fitness item in stock.
- Compare two hiking products and check inventory.
- Add a product to the cart without checking out.
- Refuse to checkout until the customer confirms.
- Request approval once the hard budget threshold is reached.

Measure tool-selection accuracy, argument accuracy, task completion, policy compliance, latency, and estimated cost.

## End-to-end tests

Playwright can validate the browser experience:

- Submit a shopping request.
- Render the response and trace.
- Display model and budget tier.
- Trigger the warning and hard thresholds.
- Approve and deny checkout.
- Preserve cart state after denial.

## Security and governance tests

- Prompt injection requesting undeclared tools
- Attempts to bypass approval through natural language
- Invalid function arguments
- Repeated checkout calls
- Cross-session cart access
- Oversized input and request-rate limits
- Missing or malformed identity once authentication is added

## CI gates

A pull request should fail when linting, compilation, or tests fail. Live model evaluations should run in a controlled scheduled workflow or staging pipeline with explicit credentials and a capped evaluation budget, not on every pull request.
