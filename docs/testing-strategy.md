# Testing Strategy

## Objectives

Testing must validate deterministic business behavior, agent-tool integration, domain boundaries, budget policy, approval controls, and the telemetry used to operate the system.

## Unit tests

### Budget engine

- Cost estimation for each configured model
- Normal, downgraded, and gated tier transitions
- Exact behavior at 70% and 95% boundaries
- Model escalation allowed below the warning threshold
- Lower-cost model enforced after the warning threshold
- Result caps applied after downgrade

### Domain guard

- Programming questions rejected
- General-knowledge requests rejected
- Unrelated writing requests rejected
- Product, inventory, promotion, cart, and checkout requests accepted
- Ambiguous shopping language handled conservatively
- Rejected requests produce zero model calls, tokens, and cost

### Catalog and tools

- Product search by keyword and category
- Price filtering
- Gender, size, brand, and attribute filtering
- Near-match product resolution
- Inventory checks
- Promotion lookup
- Cart add, remove, and read behavior
- Checkout totals and discounts
- Empty-cart checkout handling
- Idempotent behavior where implemented

### Trace aggregation

- Events stored in execution order
- Model token and latency aggregation
- Tool-call count
- Session cost aggregation
- Domain and policy events displayed correctly
- Session summary metrics match trace totals

## API integration tests

Use FastAPI’s test client with Gemini mocked. Validate:

- `POST /chat` request and response contracts
- Off-domain rejection behavior
- Conversation-state updates
- Budget and trace endpoints
- Presenter spend controls
- Approval creation and resolution
- Session-summary generation
- Summary closure does not destroy the active session
- Health response
- Error behavior when no approval is pending

## Agent tests

Create a golden dataset containing tasks such as:

- Find waterproof hiking boots under a price limit.
- Check a product’s inventory in a requested size.
- Add a near-match product name to the cart.
- Find an applicable promotion.
- Build a complete hiking outfit under a budget.
- Build a women’s cold-weather outfit for a named destination.
- Show the current cart.
- Require approval for gated checkout.
- Reject a programming request before model execution.

Measure:

- Tool-selection accuracy
- Argument accuracy
- Multi-step completion
- Budget compliance
- Domain compliance
- Approval compliance
- Product hallucination rate
- Token use
- Estimated cost
- Latency

## End-to-end browser tests

Playwright should validate:

- Two-column layout renders.
- Conversation input remains anchored at the bottom.
- New messages scroll into view.
- Agent execution panel updates after each turn.
- Model, tokens, cost, latency, tool calls, and tier are shown.
- Tool input and output details can be expanded.
- Off-domain response is clearly styled.
- Presenter controls change the displayed budget tier.
- Gated checkout pauses for approval.
- End chat opens the summary dialog.
- X and Back to chat return to the same active conversation.
- Start a new chat creates a new session.
- Summary metrics and chat history render correctly.

## Policy demonstrations

### Downgraded tier

1. Request the higher-capability model.
2. Run a broad outfit request.
3. Set simulated spend to 75%.
4. Repeat the request.
5. Verify the lower-cost model is selected and result caps apply.

### Gated tier

1. Add an item to the cart.
2. Set simulated spend to 96%.
3. Request checkout.
4. Verify checkout pauses for human approval.
5. Approve and deny in separate tests.

## Security and governance tests

- Prompt injection requesting undeclared tools
- Attempts to bypass approval through natural language
- Invalid function arguments
- Repeated checkout calls
- Cross-session cart access
- Oversized input
- Request-rate limits
- Sensitive-data redaction
- Missing or malformed identity after authentication is added

## CI gates

A pull request should fail when:

- Linting fails
- Formatting checks fail
- Compilation fails
- Unit tests fail
- API integration tests fail
- Coverage falls below the configured threshold
- Docker build validation fails, when enabled

Live Vertex AI evaluations should run in a scheduled or staging workflow with explicit credentials and a capped budget, not on every pull request.

## React testing layers

- React production build validation catches module and bundling failures.
- Playwright mocks FastAPI responses for deterministic UI behavior and zero model cost.
- Recommended future additions include Vitest and React Testing Library for component-level state and accessibility tests.
