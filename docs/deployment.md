# Deployment

## Local prerequisites

- Python 3.11+
- Google Cloud CLI
- A Google Cloud project with Vertex AI enabled
- Access to the configured Gemini models

## Local authentication

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

Copy `.env.example` to `.env`, set `GOOGLE_CLOUD_PROJECT`, and confirm the location and model IDs available to the project.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

## GitHub Actions

The CI workflow does not call Vertex AI and therefore does not require cloud credentials. It installs dependencies, runs Ruff, executes tests, and compiles Python modules. Tests mock or avoid model calls.

## Cloud Run target architecture

- Build the API into a container.
- Deploy the service to Cloud Run.
- Attach a dedicated service account with the minimum Vertex AI invocation role.
- Store configuration in Cloud Run environment variables and secrets in Secret Manager.
- Replace SQLite with Cloud SQL for PostgreSQL.
- Host the frontend on Firebase Hosting or serve it from the API container.
- Restrict CORS to the deployed frontend origin.

## Required production controls

- No long-lived service-account key files
- Least-privilege service account
- Secret Manager for secrets
- Private database connectivity
- Structured application logs
- Trace and metric export
- Request timeouts and bounded retries
- Rate limits and abuse controls
- Health, readiness, and dependency checks

## Rollout strategy

Use separate development, staging, and production projects. Validate prompts, models, tool schemas, and policy configuration in staging before production rollout. Use gradual traffic migration and preserve a rollback path to the prior container revision.

## Cost configuration

Estimated rates in `.env.example` are configuration examples. Confirm current model pricing and update the environment before deployment. Treat the application estimate as telemetry, not billing authority. Reconcile operational estimates with Cloud Billing exports for financial reporting.
