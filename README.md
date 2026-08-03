# JeolAI

**Jeol** is derived from the Korean word *jeollyak* (절약), meaning thrift or economizing. JeolAI demonstrates that enterprise AI agents should optimize for cost, not just capability.

JeolAI is an AI shopping agent with a production-oriented control plane around it. The application traces model and tool calls, estimates session cost, routes requests between Gemini models, reduces work as spend rises, and requires human approval before a gated checkout.

The commerce domain is intentionally small. The engineering value is in the controls, not the size of the storefront.

## What JeolAI demonstrates

- Gemini function calling through Vertex AI
- Deterministic catalog, inventory, promotion, cart, and checkout tools
- Per-call token, cost, and latency tracing
- Session-level budget accounting
- Budget-aware model routing
- Search-result reduction after a warning threshold
- Human approval before a gated checkout
- FastAPI APIs and a lightweight browser interface
- GitHub Actions validation
- Engineering documentation covering architecture, deployment, testing, and governance

## Architecture

```text
User
  |
Browser UI
  |
FastAPI API
  |
Gemini Agent on Vertex AI
  |-------------------------------|
  |          |          |         |
Catalog   Inventory  Promotions  Cart/Checkout
  |
Budget Policy Engine
  |
Trace and Cost Store
  |
SQLite
```

The agent does not access the database directly. It can only act through the declared tools. The application intercepts tool requests, records execution telemetry, and enforces approval policy before checkout.

## Demo app
Backend:
![Screenshot](/docs/Screenshot%202026-08-03%20at%201.05.57 AM.png)


Frontend:
![Screenshot](/docs/Screenshot%202026-08-03%20at%2012.58.59 AM.png)



## Budget policy

| Session spend | Model policy | Retrieval policy | Checkout policy |
|---|---|---|---|
| Below 70% | Default or escalated model | Full results | Customer confirmation |
| 70% to 95% | Lower-cost default model | Results capped | Customer confirmation |
| 95% or above | Lower-cost default model | Results capped | Human approval required |

Thresholds, model names, and estimated token rates are configurable through environment variables.

## Repository structure

```text
.
├── backend/
│   ├── budget.py
│   ├── db.py
│   ├── gemini_client.py
│   ├── main.py
│   ├── tools.py
│   └── tracer.py
├── docs/
│   ├── architecture.md
│   ├── deployment.md
│   ├── governance.md
│   ├── system-design.md
│   └── testing-strategy.md
├── frontend/
│   └── index.html
├── tests/
├── .github/workflows/ci.yml
├── .env.example
└── requirements.txt
```

## Engineering documentation

- [Architecture](docs/architecture.md): components, execution flow, trust boundaries, and tradeoffs
- [System design](docs/system-design.md): requirements, APIs, data model, reliability, and scaling path
- [Deployment](docs/deployment.md): local setup, Vertex AI authentication, CI, and production deployment
- [Testing strategy](docs/testing-strategy.md): unit, integration, end-to-end, agent, and policy testing
- [Governance](docs/governance.md): cost, approval, auditability, security, and operational ownership

## Prerequisites

- Python 3.11 or later
- A Google Cloud project with Vertex AI enabled
- Permission to invoke the configured Gemini models
- Google Cloud CLI for local Application Default Credentials

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Set GOOGLE_CLOUD_PROJECT and review model and pricing configuration.

gcloud auth application-default login
```

Start the API:

```bash
uvicorn backend.main:app --reload --port 8000
```

Open `frontend/index.html` in a browser. The page calls `http://localhost:8000`.

## API endpoints

| Endpoint | Purpose |
|---|---|
| `POST /chat` | Run one user turn through the agent |
| `POST /approve` | Approve or deny a gated checkout |
| `GET /budget-status/{session_id}` | Read current spend and policy tier |
| `GET /trace/{session_id}` | Retrieve model, tool, cost, and latency events |
| `POST /debug/set-spend` | Demonstrate budget thresholds locally |
| `GET /health` | Verify service and model configuration |

## Authentication and cost notes

The project uses the Google Gen AI SDK with Vertex AI and Application Default Credentials. No API key is stored in the repository.

Displayed dollar amounts are estimates. Model prices can change and can differ by model, capability, and region. Update the rate variables in `.env` before using cost data for operational or financial decisions.

## CI

GitHub Actions runs on pushes and pull requests to `main` or `master`. It installs dependencies, checks formatting and lint rules, runs tests, and validates Python compilation.

## Current scope and production gaps

This repository is a reference implementation, not a production commerce system. A production deployment would additionally require:

- Identity, authentication, RBAC, and tenant isolation
- Durable encrypted session and approval state
- A managed transactional database
- Idempotency for state-changing tools
- Payment-provider isolation and reconciliation
- Prompt, model, tool, and policy versioning
- Golden datasets and continuous agent evaluation
- Centralized logs, metrics, traces, and alerting
- Organization-level budgets and chargeback
- Security review, abuse controls, and incident runbooks

## License

MIT
