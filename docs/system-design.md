# System Design

## Problem statement

A shopping agent that can search, compare, add to cart, and checkout must do more than generate useful answers. It must remain within its supported domain, operate under cost limits, expose its execution path, and prevent consequential actions from bypassing policy.

## Design goals

- Make agent behavior visible to users and reviewers.
- Keep model access separate from deterministic business operations.
- Enforce budget and action policy on the server.
- Support multi-step commerce workflows.
- Reject unrelated requests before model invocation.
- Preserve a lightweight local setup suitable for workshops and portfolio review.

## Functional requirements

- Search products by natural-language intent.
- Filter by budget, category, brand, gender, size, and product attributes.
- Resolve abbreviated or near-match product names.
- Check inventory and active promotions.
- Add, remove, and inspect cart items.
- Build multi-item recommendations under a user-specified budget.
- Complete a simulated checkout.
- Pause checkout for human approval when the hard budget threshold is reached.
- Reject off-domain requests.
- Display the full execution path and operating metrics.
- Generate a session summary with chat history and aggregate usage.

## Nonfunctional requirements

- Tool access must be allowlisted.
- Budget decisions must be deterministic and server-side.
- Model credentials must never reach the browser.
- State-changing operations must be auditable.
- Model, pricing, and policy configuration must be externalized.
- Off-domain requests should not consume model tokens.
- The system must remain understandable enough for architectural review.

## Data model

### Products

Stores:

- Product name and aliases
- Category and subcategory
- Brand
- Price
- Gender or audience
- Sizes
- Use cases and attributes
- Inventory

### Promotions

Stores:

- Promotion code
- Description
- Applicable category, product, or scope
- Discount value
- Active state

### Cart items

Stores session-scoped selections and quantities.

### Orders

Stores simulated checkout records, totals, discounts, and order status.

### Sessions

Stores:

- Session ID
- Input and output tokens
- Estimated spend
- Model and tool-call counts
- Current policy tier
- Session start time

### Trace steps

Stores execution events, including:

- Step type
- Display label
- Model or tool name
- Arguments and results
- Tokens
- Estimated cost
- Latency
- Policy metadata
- Timestamp

## API design

### `POST /chat`

Runs one user turn through:

1. Domain validation
2. Budget policy
3. Model selection
4. Gemini tool orchestration
5. Tool execution
6. Response generation

The response includes the assistant reply, model used, token usage, budget status, and approval state.

### `POST /approve`

Approves or denies a pending gated checkout. Approval remains separate from chat so a production implementation can enforce reviewer identity and authorization.

### `GET /budget-status/{session_id}`

Returns current estimated spend, percentage used, remaining budget, and budget tier.

### `GET /trace/{session_id}`

Returns ordered model, tool, domain, cost, policy, and latency events for the right-side execution panel.

### `POST /debug/set-spend`

Changes simulated spend for workshop demonstrations of downgraded and approval-gated behavior.

### Session summary endpoint

Returns:

- Message count
- Session duration
- Input, output, and total tokens
- Estimated cost
- Model-call count
- Tool-call count
- Total latency
- Current budget tier
- Conversation history

Generating a summary does not destroy the session. The user may return to the active conversation.

## Model routing

The lower-cost Gemini model handles normal traffic by default. A higher-capability model may be requested while policy allows it. Once spend crosses the warning threshold, policy forces the lower-cost model.

Model selection is visible in the execution panel.

## Retrieval policy

Below the warning threshold, product searches may return the full configured result set. Above the threshold, result counts are capped to reduce subsequent context and model cost.

## Multi-step planning

For broad shopping goals, Gemini may issue several sequential tool calls. The application loops through function calls until a final answer is produced. Each call is validated, executed, and traced independently.

## Domain-boundary behavior

Clearly unrelated requests are blocked before Gemini. The guard should be deterministic for obvious cases and conservative for ambiguous shopping language.

Blocked requests must record:

- Request received
- Domain guard rejected request
- Model not called
- Tokens: zero
- Cost: zero
- Tool calls: zero

## Failure handling

- Invalid tool names are rejected.
- Invalid tool arguments return structured errors.
- Missing Vertex AI configuration fails fast.
- Empty or malformed model responses raise explicit errors.
- Product-resolution failures return suggestions rather than fabricating inventory.
- Denied checkout preserves cart state.
- Unknown pricing configuration fails rather than silently producing inaccurate cost.
- Summary-dialog closure does not terminate the active session.

## Scaling path

For multi-instance deployment:

1. Move sessions, conversations, and pending approvals to Redis or a durable workflow store.
2. Replace SQLite with PostgreSQL.
3. Add idempotency keys to cart and checkout operations.
4. Export traces through OpenTelemetry.
5. Add tenant and user identity to every record.
6. Introduce organization-level budget aggregation and quotas.
7. Run the API on Cloud Run.
8. Move product search to a dedicated search or catalog service.
9. Introduce durable workflow execution for long-running approvals.

## Key tradeoff

JeolAI favors explicit control points over framework abstraction. This makes the model, policy, and tool path easy to review and explain, which is valuable for workshops and architectural evaluation. The tradeoff is more orchestration code than a framework-managed agent loop.
