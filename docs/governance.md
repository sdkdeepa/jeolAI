# Governance

## Governance goals

JeolAI treats cost, action authorization, traceability, and model configuration as application responsibilities rather than optional dashboard features.

## Cost governance

Each model call records input tokens, output tokens, model name, estimated cost, and latency. Session spend drives a three-tier policy:

- Normal: escalation allowed and full search results
- Downgraded: lower-cost model and reduced result set
- Gated: lower-cost model, reduced result set, and approval before checkout

Pricing is configuration because provider prices and model IDs change. Cloud billing data remains the financial source of truth.

## Action governance

Tool declarations constrain what Gemini may request, but the server remains the enforcement point. Checkout is intercepted before execution. In a production system, approval must include reviewer identity, authorization, reason, timestamp, expiration, and the exact proposed action payload.

## Auditability

The trace records model calls, tool calls, and policy events in execution order. Production records should additionally include:

- User and tenant identity
- Request and correlation IDs
- Prompt, model, tool, and policy versions
- Approval actor and decision
- Redacted tool inputs and outputs
- Retry and error events
- Immutable retention controls

## Security

- Authenticate every request.
- Authorize every tool independently of model intent.
- Use least-privilege service identities.
- Validate function names and arguments server-side.
- Apply rate limits and request-size limits.
- Redact sensitive data before logging.
- Encrypt data in transit and at rest.
- Separate payment execution from model orchestration.

## Operational ownership

A production service needs named owners for model configuration, pricing updates, budget policy, tool contracts, evaluation datasets, security review, and incident response. A new control without an owner becomes another failure surface.

## Change management

Changes to prompts, model versions, tools, thresholds, or pricing can alter quality, cost, and behavior. Version these artifacts, evaluate them against golden tasks, review high-risk changes, and retain a rollback path.

## Known limitations

The current project uses in-memory conversation and approval state, permissive CORS, a caller-provided session ID, and SQLite. These choices support a local reference implementation but are not acceptable controls for a shared production environment.
