# Deployment

## Local prerequisites

- Python 3.11 or later
- Google Cloud CLI
- A Google Cloud project with Vertex AI enabled
- Permission to invoke the configured Gemini models
- A modern web browser

## Google Cloud authentication

Use Application Default Credentials for local development:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

Verify Vertex AI is enabled:

```bash
gcloud services list --enabled | grep aiplatform
```

Enable it when needed:

```bash
gcloud services enable aiplatform.googleapis.com
```

## Environment configuration

Copy the example file:

```bash
cp .env.example .env
```

Set:

```text
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
```

Review the configured Gemini model IDs, session budget, warning threshold, hard threshold, and estimated token rates.

Use the Google Cloud **Project ID**, not the display name or project number.

## Local backend

From the project root:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Verify:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

## Local frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5500
```

Running the frontend through a local HTTP server is preferred over opening `index.html` directly because it avoids browser file-origin restrictions.

## Workshop operating model

For a live workshop:

- Start the backend and frontend before screen sharing.
- Keep `/health`, `/docs`, and the two-panel UI open in separate tabs.
- Use presenter controls to demonstrate budget tiers without consuming the full configured budget.
- Prepare a backup recording when venue connectivity is uncertain.
- Ask attendees to clone the repository and install dependencies before arrival when possible.
- Treat stable Wi-Fi as a requirement for a fully hands-on cloud-model workshop.

## GitHub Actions

The CI workflow should not call Vertex AI on every pull request. It should:

- Install Python dependencies
- Run formatting and lint checks
- Run deterministic unit and API tests
- Validate Python compilation
- Build the application or Docker image when configured
- Avoid requiring cloud credentials for normal pull-request validation

Live model evaluations should run only in a controlled environment with an explicit evaluation budget.

## Container deployment

A production-oriented container should:

- Run Uvicorn or Gunicorn with bounded workers
- Expose a health endpoint
- Load configuration from environment variables
- Avoid embedding credentials
- Run as a non-root user
- Use a read-only filesystem where practical

## Cloud Run target architecture

```text
GitHub
  |
GitHub Actions
  |
Container Registry
  |
Cloud Run API
  |
Vertex AI
  |
Managed database and trace backend
```

Recommended production changes:

- Deploy the FastAPI service to Cloud Run.
- Attach a dedicated service account with minimum Vertex AI permissions.
- Store secrets in Secret Manager.
- Replace SQLite with Cloud SQL for PostgreSQL.
- Store session and approval state in a durable shared system.
- Host the frontend on Firebase Hosting or serve it from the API container.
- Restrict CORS to the deployed frontend origin.
- Export logs, metrics, and traces centrally.

## Required production controls

- No long-lived service-account key files
- Least-privilege service identity
- Secret Manager for secrets
- Private database connectivity
- Structured logs
- Trace and metric export
- Request timeouts and bounded retries
- Rate limits and abuse controls
- Health, readiness, and dependency checks
- Data-retention and redaction policies
- Idempotency for cart and checkout operations

## Rollout strategy

Use separate development, staging, and production projects. Validate prompts, model versions, tool schemas, policy thresholds, and pricing configuration in staging. Use gradual traffic migration and retain a rollback path to the previous container revision.

## Cost configuration

Displayed costs are operational estimates derived from configured token rates. They are not a billing authority. Confirm current provider pricing and reconcile estimates with Cloud Billing exports for financial reporting.


## React production build

```bash
cd frontend
npm ci
npm run build
```

The generated `frontend/dist/` directory can be served by a static host, Firebase Hosting, or Nginx. Set `VITE_API_BASE_URL` at build time to the deployed FastAPI endpoint.
