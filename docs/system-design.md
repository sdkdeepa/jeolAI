# System Design

## Problem statement

An agent that can complete a shopping workflow must be more than capable. It must operate within cost limits, expose its execution path, and prevent consequential actions from bypassing policy.

## Functional requirements

- Search and compare products.
- Check inventory and active promotions.
- Add, remove, and update cart items.
- Complete a simulated checkout after confirmation.
- Pause checkout for human approval when policy requires it.
- Display model, token, cost, latency, and tool activity by session.

## Nonfunctional requirements

- Tool access must be allowlisted.
- Budget decisions must be deterministic and server-side.
- Model credentials must not reach the browser.
- State-changing operations must be auditable.
- Model and pricing configuration must be externalized.
- The application must remain understandable enough for architectural review.

## Data model

- `products`: catalog, category, price, description, inventory
- `promotions`: code, category, discount, status
- `cart_items`: session-scoped cart state
- `orders`: simulated checkout records
- `sessions`: accumulated tokens and estimated spend
- `trace_steps`: model, tool, and policy events

## API design

`POST /chat` is the orchestration endpoint. The caller supplies a session identifier, message, and optional escalation request. The response includes the text result, model used, budget status, and whether approval is required.

`POST /approve` completes or denies a pending checkout. Approval is separate from chat so a future production system can enforce a different reviewer identity and authorization policy.

## Model routing

The default model handles normal traffic. An escalated model can be requested while the session remains in the normal budget tier. Once spend crosses the warning threshold, policy forces the lower-cost model.

## Failure handling

- Invalid product requests return structured tool errors.
- Missing Vertex AI configuration fails fast during application startup.
- A model response without candidate content raises an explicit error.
- Denied checkout preserves the cart.
- Unknown model pricing configuration fails rather than silently reporting an incorrect estimate.

## Scaling path

For multi-instance deployment:

1. Move conversations and pending approvals to Redis or a durable workflow store.
2. Replace SQLite with PostgreSQL.
3. Add idempotency keys to cart and checkout operations.
4. Export traces through OpenTelemetry.
5. Add tenant and user identity to every record.
6. Introduce organization-level budget aggregation and quotas.
7. Run the API on Cloud Run with minimum instances only where latency requires it.

## Key tradeoff

JeolAI favors transparent control points over framework abstraction. This makes the policy path visible to reviewers and provides a clear reference for teams deciding where governance belongs in an agent stack.
