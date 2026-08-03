# Architecture

## Purpose

JeolAI is a reference implementation for operating an AI agent under explicit cost, action, and observability controls. The shopping workflow provides a familiar domain in which the agent reads catalog data and proposes state-changing actions.

## System context

```text
User -> Browser -> FastAPI -> Gemini on Vertex AI
                         |-> Shopping tools -> SQLite
                         |-> Budget policy
                         |-> Trace store
                         |-> Human approval
```

The model does not receive database credentials and cannot execute arbitrary code. It selects from a constrained set of declared functions. The API process validates and executes those functions.

## Components

### Browser interface

The single-page frontend submits chat requests and renders the agent response, current budget tier, trace events, and approval controls. It contains no model credentials.

### FastAPI service

The API owns session orchestration, model selection, tool execution, budget updates, and approval state. `backend/main.py` is the boundary between HTTP requests and agent execution.

### Gemini client

`backend/gemini_client.py` uses the Google Gen AI SDK with Vertex AI. Automatic function execution is disabled so the application can intercept every proposed tool call, record telemetry, and enforce policy before execution.

### Tool layer

The tool layer exposes five operations:

- `search_products`
- `check_inventory`
- `get_promotions`
- `update_cart`
- `checkout`

Tool implementations are deterministic and isolated from model logic. Checkout is simulated and writes an order to SQLite.

### Budget engine

The budget engine records estimated token cost per session. It chooses the model, limits search results, and determines when checkout requires human approval.

### Trace store

Model calls, tool calls, and policy events are written to `trace_steps`. Each model trace records model name, input tokens, output tokens, estimated cost, and latency.

## Request sequence

1. The browser sends a user message and session ID.
2. The API reads current spend and selects a Gemini model.
3. Gemini returns text or one or more function calls.
4. The application appends the complete model response to history.
5. Proposed functions are checked against policy.
6. Allowed functions are executed and traced.
7. Function responses are returned to Gemini.
8. The loop continues until Gemini produces a final response or approval is required.
9. Usage is added to the session budget.
10. The browser receives the response, model, budget tier, and approval state.

## Trust boundaries

- Browser input is untrusted.
- Model output is untrusted until validated by the application.
- Tool declarations are an allowlist, not authorization by themselves.
- State-changing functions require server-side policy checks.
- Vertex AI authentication remains on the backend through Application Default Credentials.

## Architectural tradeoffs

SQLite and in-memory conversations keep the project easy to run but do not support horizontal scaling or durable approvals. Manual function execution creates more code than automatic tool calling, but it provides the interception point required for governance, tracing, and human approval.
