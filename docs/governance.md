# Governance

## Governance goals

JeolAI treats domain boundaries, cost, action authorization, traceability, and model configuration as application responsibilities rather than optional dashboard features.

## Domain governance

JeolAI is scoped to shopping and commerce workflows. Obvious off-domain requests are rejected before model invocation.

This provides:

- Lower unnecessary inference cost
- Reduced abuse surface
- More predictable product behavior
- Clear ownership of supported capabilities

Production systems should maintain a versioned domain policy and test it against both false positives and false negatives.

## Cost governance

Each model call records:

- Model name
- Input tokens
- Output tokens
- Estimated cost
- Latency

Session spend drives a three-tier policy:

### Normal

- Default or requested higher-capability model
- Full configured search results
- Standard customer confirmation before checkout

### Downgraded

- Lower-cost model enforced
- Search results capped
- Standard customer confirmation retained

### Gated

- Lower-cost model enforced
- Search results capped
- Human approval required before checkout

Pricing is external configuration because provider rates and model identifiers change. Cloud Billing remains the financial source of truth.

## Action governance

Tool declarations constrain what Gemini may request, but the server remains the enforcement point.

For every state-changing action, the backend should validate:

- User and tenant authorization
- Tool name and arguments
- Current cart and inventory state
- Idempotency key
- Budget tier
- Approval requirement
- Exact proposed action payload

Checkout is intercepted before execution when the session is gated.

## Human approval

The reference implementation demonstrates an approval gate. A production approval record should include:

- Reviewer identity
- Reviewer authorization
- Decision and reason
- Timestamp
- Expiration
- Session and tenant IDs
- Exact proposed action
- Policy version
- Model and tool versions

Approval should authorize one specific action, not grant broad future permission.

## Auditability

The execution trace records:

- Request received
- Domain-guard result
- Budget-policy decision
- Model selection
- Model calls
- Tool selection
- Tool input and output
- Approval state
- Final response

Production audit records should additionally include:

- User and tenant identity
- Request and correlation IDs
- Prompt, model, tool, catalog, and policy versions
- Approval actor and decision
- Redacted tool payloads
- Retry and error events
- Immutable retention controls

## Session summaries

The session summary provides a user-visible operating record:

- Conversation history
- Message count
- Duration
- Total tokens
- Estimated cost
- Model calls
- Tool calls
- Total latency
- Final budget tier

Closing the summary returns to the active conversation. Starting a new chat creates a new session. In production, summary generation and session termination should be distinct operations.

## Security

- Authenticate every request.
- Authorize every tool independently of model intent.
- Use least-privilege service identities.
- Validate function names and arguments server-side.
- Apply rate and request-size limits.
- Redact sensitive data before logging.
- Encrypt data in transit and at rest.
- Separate payment execution from model orchestration.
- Do not expose provider credentials to the browser.
- Treat model output as untrusted.

## Operational ownership

A production service needs named owners for:

- Domain policy
- Model configuration
- Pricing updates
- Budget thresholds
- Tool contracts
- Catalog and inventory data
- Approval policy
- Evaluation datasets
- Security review
- Incident response

A control without an owner becomes another failure surface.

## Change management

Changes to prompts, model versions, tools, catalog data, thresholds, or pricing can alter quality, cost, and behavior. Version these artifacts, evaluate them against golden tasks, review high-risk changes, and retain a rollback path.

## Incident response

Operational runbooks should cover:

- Unexpected cost growth
- Model or provider outage
- Tool failure
- Incorrect inventory or price
- Approval bypass
- Cross-session data exposure
- Trace or logging failure
- Domain-guard regression

## Known limitations

The reference implementation uses local browser state, SQLite, permissive local CORS, caller-provided session IDs, and simplified approval behavior. These choices support a local workshop and portfolio project but are not sufficient for a shared production environment.
