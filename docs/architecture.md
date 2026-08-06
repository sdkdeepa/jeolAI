# Architecture

## Purpose

JeolAI is a reference implementation for operating an AI shopping agent under explicit cost, action, observability, and domain controls. The shopping workflow is intentionally bounded so the architecture can focus on how a production agent is governed rather than on storefront breadth.

## System context

```text
            User
              |
            React + Vite UI
              |
            FastAPI orchestration API
              |
            Domain guard
              |
            Budget policy engine
              |
            Gemini on Vertex AI
              |
            Declared commerce tools
              |
            SQLite state and trace store
```

The model does not receive database credentials and cannot execute arbitrary code. It can only request functions declared by the application. The backend validates, executes, traces, and may block those requests.

![JeolAI System Deign](/docs/jeolai-system-design.png)

## Major components

### React + Vite two-panel interface

The React UI separates the experience into:

- **Shopping conversation**: user messages, assistant responses, message input, and session controls
- **Agent execution**: budget meter, model selected, token counts, estimated cost, latency, tool-call count, budget tier, and execution timeline

The UI also provides:

- Presenter controls for simulating downgraded and approval-gated budget tiers
- An end-chat summary containing conversation history and aggregate metrics
- A resumable summary flow that returns to the existing conversation
- No model credentials or direct database access

### Demo App
#### Backend 
![Backend](/docs/Backend.png)

#### Frontend - Downgraded, Gated and Goverance

![Downgraded](/docs/Downgraded.png)

![Gated](/docs/Gated.png)

![Guardrail](/docs/Governance.png)

#### Session summary
![Session Summary](/docs/SessionSummary.png)

### FastAPI orchestration service

`backend/main.py` is the HTTP and orchestration boundary. It:

- Accepts chat requests
- Runs the domain guard
- Reads budget state
- Selects the allowed model
- Invokes the Gemini tool-calling loop
- Enforces checkout approval
- Aggregates session summaries
- Exposes trace and budget APIs

### Domain guard

The domain guard rejects requests outside supported commerce workflows before model execution. Examples include coding questions, general knowledge, and unrelated writing requests.

A blocked request returns a bounded response such as:

> I don’t know. I can only help with shopping, products, promotions, inventory, carts, and checkout.

The trace records that the request was blocked before Gemini, preserving zero model tokens and zero model cost for that turn.

### Gemini client

`backend/gemini_client.py` uses the Google Gen AI SDK with Vertex AI. Automatic function execution is not trusted as an opaque operation. The application intercepts each proposed tool call so it can:

- Validate the tool name and arguments
- Record tool input and output
- Apply policy before execution
- Return deterministic function results to Gemini
- Continue multi-step orchestration until a final response is produced

### Tool layer

The tool layer includes deterministic commerce operations such as:

- Product search with price, category, brand, gender, size, and use-case filters
- Product-name resolution and near-match handling
- Inventory lookup
- Promotion lookup
- Cart read and update
- Checkout

The richer seeded catalog supports scenarios such as waterproof hiking boots, women’s hiking apparel, outdoor accessories, and budget-constrained outfits.

### Multi-step orchestration

The agent can execute several tool calls within one user turn. For example, an outfit request can:

1. Search footwear
2. Search outerwear
3. Search pants
4. Search a base layer
5. Search socks or accessories
6. Compare the combined price against the user’s budget
7. Produce a final recommendation

The right-side execution panel shows these steps in order.

### Budget policy engine

The budget engine evaluates accumulated session spend and determines:

- Which Gemini model may be selected
- Whether a higher-capability model is allowed
- How many product results tools may return
- Whether checkout requires human approval

The local presenter controls alter simulated spend so these behaviors can be demonstrated without consuming the full session budget.

### Trace and cost store

Execution events are persisted in order. Trace records include:

- Request received
- Domain-guard result
- Budget-policy decision
- Model selected
- Model call usage and latency
- Tool selected
- Tool input and output
- Final response
- Approval events

Session-level metrics aggregate input tokens, output tokens, estimated cost, model calls, tool calls, and total latency.

## Request sequence

1. The browser sends a user message and session ID.
2. The API records the request.
3. The domain guard accepts or rejects the message.
4. The budget engine reads session spend and determines the tier.
5. The API selects the permitted Gemini model.
6. Gemini returns text or one or more function calls.
7. The backend validates and executes allowed tools.
8. Tool inputs, outputs, latency, and policy decisions are traced.
9. Function responses are returned to Gemini.
10. The loop continues until Gemini produces a final response or checkout requires approval.
11. Model usage is added to session-level cost accounting.
12. The browser updates both the conversation and execution panel.
13. On request, the API generates a session summary without destroying the active conversation.

## Trust boundaries

- Browser input is untrusted.
- Model output is untrusted until validated by the backend.
- Tool declarations are an allowlist, not authorization by themselves.
- State-changing tools require server-side validation.
- Checkout may require a human approval decision.
- Vertex AI credentials remain on the backend through Application Default Credentials.
- Trace data may contain sensitive inputs and must be redacted in production.

## Architectural tradeoffs

SQLite and local session state keep the project easy to run for a workshop but do not support multi-instance durability. Manual tool interception creates more code than automatic execution, but it makes model decisions, tool activity, and governance visible. The seeded catalog improves demo reliability but is not intended to replace a real commerce search or inventory platform.
