# JeolAI

**Jeol** is derived from the Korean word *jeollyak* (절약), meaning thrift or economizing. JeolAI demonstrates that enterprise AI agents should optimize for cost, not just capability.

JeolAI is a cost-aware AI shopping agent with a production-oriented control plane. It combines a React + Vite experience, a FastAPI orchestration backend, Gemini on Vertex AI, deterministic commerce tools, budget-aware model routing, human approval, guardrails, and an observable execution timeline.

The commerce domain is intentionally bounded. The engineering value is in the controls, not the size of the storefront.

## What JeolAI demonstrates

- Gemini function calling through Vertex AI
- React + Vite two-panel application
- FastAPI orchestration APIs
- Deterministic catalog, inventory, promotion, cart, and checkout tools
- Multi-step tool orchestration for budget-constrained shopping requests
- Per-call token, cost, and latency tracing
- Session-level budget accounting and model routing
- Retrieval reduction after the warning threshold
- Human approval before gated checkout
- Pre-model domain guardrails
- Session summaries with conversation and operating metrics
- Pytest and Playwright validation
- GitHub Actions and dependency auditing
- Docker-based backend and frontend builds

## Architecture

```text
User
  |
React + Vite UI
  |
FastAPI API
  |
Domain Guard
  |
Budget Policy Engine
  |
Gemini Agent on Vertex AI
  |-----------------------------------|
  |            |           |          |
Catalog     Inventory   Promotions   Cart/Checkout
  |
Trace and Cost Store
  |
SQLite
```

Gemini does not access the database directly. It may request only declared tools. The FastAPI backend validates tool requests, records telemetry, applies policy, and can pause checkout for human approval.

## Budget policy

| Session spend | Model policy | Retrieval policy | Checkout policy |
|---|---|---|---|
| Below 70% | Default or escalated model | Full results | Customer confirmation |
| 70% to 95% | Lower-cost model | Results capped | Customer confirmation |
| 95% or above | Lower-cost model | Results capped | Human approval required |

Thresholds, model names, and estimated token rates are configurable in `.env`.

## Repository structure

```text
.
├── backend/
│   ├── budget.py
│   ├── db.py
│   ├── gemini_client.py
│   ├── guardrails.py
│   ├── main.py
│   ├── tools.py
│   └── tracer.py
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api.js
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── package.json
│   └── vite.config.js
├── docs/
├── tests/
├── e2e/
├── .github/workflows/
├── Dockerfile
├── docker-compose.yml
├── package.json
├── playwright.config.js
└── requirements.txt
```

## Prerequisites

- Python 3.11 or later
- Node.js 20 or later
- Google Cloud CLI
- A Google Cloud project with billing and Vertex AI enabled
- Permission to invoke the configured Gemini models

## Local setup

### 1. Configure Google Cloud

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com
```

### 2. Configure and run the backend

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set GOOGLE_CLOUD_PROJECT in .env
uvicorn backend.main:app --reload --port 8000
```

Verify:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

### 3. Configure and run the React frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5500
```

The React application reads the backend address from:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## API endpoints

| Endpoint | Purpose |
|---|---|
| `POST /chat` | Run one user turn through guardrails, policy, Gemini, and tools |
| `POST /approve` | Approve or deny a gated checkout |
| `GET /budget-status/{session_id}` | Read current spend and policy tier |
| `GET /trace/{session_id}` | Retrieve model, tool, cost, policy, and latency events |
| `POST /debug/set-spend` | Demonstrate budget tiers locally |
| `POST /end-chat` | Generate a resumable session summary |
| `DELETE /session/{session_id}` | Reset a local workshop session |
| `GET /health` | Verify provider and model configuration |

## Testing

Backend tests do not require live Vertex AI calls:

```bash
source venv/bin/activate
pytest
```

React build validation:

```bash
cd frontend
npm ci
npm run build
```

Playwright tests mock API responses and do not consume Gemini quota:

```bash
npm install
npm --prefix frontend install
npx playwright install chromium
npm run test:e2e
```

## CI and security

GitHub Actions validates:

- Python compilation
- Ruff linting
- Pytest and backend coverage
- React production build
- Playwright UI workflows
- Python dependency vulnerabilities through `pip-audit`
- Weekly Python and GitHub Actions updates through Dependabot

Normal pull requests do not authenticate to Google Cloud or invoke Gemini.

## Docker

Build and run the backend and frontend:

```bash
docker compose up --build
```

The local Docker configuration is for development and demonstration. A production deployment should use managed identity, durable storage, restricted CORS, and a managed database.

## Engineering documentation

- [Architecture](docs/architecture.md)
- [System design](docs/system-design.md)
- [Deployment](docs/deployment.md)
- [Testing strategy](docs/testing-strategy.md)
- [Governance](docs/governance.md)

## Production gaps

This repository is a reference implementation. A production deployment additionally requires identity, RBAC, tenant isolation, durable encrypted state, idempotency, payment isolation, centralized telemetry, continuous agent evaluation, prompt and policy versioning, organization-level budgets, security review, and incident runbooks.

## License

MIT
