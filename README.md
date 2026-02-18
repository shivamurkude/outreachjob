# FINDMYJOB v2 Backend

Monolith FastAPI backend: Google Auth, Gmail API scheduling, credits/ledger, resume/list/verify/enrich/templates/campaigns, Razorpay payments, admin ops.

## Stack

- **API**: FastAPI, uvicorn, pydantic-settings
- **Auth**: Google ID token verification, signed cookie session
- **DB**: MongoDB + Beanie (ODM)
- **Queue**: Redis + ARQ (jobs + cron)
- **Gmail**: OAuth tokens (encrypted), drafts + send at scheduled time
- **Payments**: Razorpay (order + webhook, HMAC)
- **Storage**: Local or GCS for uploads
- **Logging**: structlog (request + duration, service/worker logs, exception tracebacks)

## Docs

- **[docs/SETUP.md](docs/SETUP.md)** – Local setup, env vars, running via terminal or **VS Code/Cursor launch configs**
- **[docs/API.md](docs/API.md)** – API reference (all v1 endpoints)
- **[docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)** – What’s implemented vs plan (gaps: suppression list, LangGraph, Gmail rate limit, audit/DLQ wiring, RBAC)

## Setup

1. Copy `.env.example` to `.env` and set at least `MONGODB_URI`, `MONGODB_DB_NAME`, `REDIS_URL`, `SECRET_KEY`, Google OAuth and (optional) Razorpay vars. See [docs/SETUP.md](docs/SETUP.md).

2. Install:

```bash
pip install -r requirements.txt
```

3. Run locally:

**Option A – VS Code / Cursor**

- Open **Run and Debug** (Ctrl+Shift+D / Cmd+Shift+D).
- Select **Run API (uvicorn)** or **Run ARQ Worker** (or **API + Worker** to run both), then F5.

**Option B – Terminal**

```bash
export PYTHONPATH=.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# In another terminal for the worker:
python -m app.worker.run_worker
```

## Endpoints (v1)

- **Auth**: `POST /v1/auth/google`, `GET /v1/auth/me`
- **Gmail**: `GET /v1/gmail/connect`, `GET /v1/gmail/oauth/callback`, `POST /v1/gmail/verify`, `DELETE /v1/gmail/disconnect`
- **Credits**: `GET /v1/credits/balance`, `GET /v1/credits/ledger`
- **Resume**: `POST /v1/resume/upload`, `POST /v1/resume/analyze`, `GET /v1/resume/latest`
- **Recipients**: `POST /v1/recipients/lists/upload`, `GET /v1/recipients/lists/{id}`, `GET /v1/recipients/lists/{id}/items`
- **Verify**: `POST /v1/verify/email`, `POST /v1/verify/bulk`
- **Enrich**: `POST /v1/enrich/bulk`
- **Templates**: CRUD `/v1/templates`, `POST /v1/templates/generate`
- **Campaigns**: `GET/POST /v1/campaigns`, `GET /v1/campaigns/{id}/preview`, `POST /v1/campaigns/{id}/schedule`
- **Payments**: `POST /v1/payments/orders`, `POST /v1/payments/webhook`
- **Admin**: `POST /v1/admin/recipients/import`, `POST /v1/admin/recipients/refresh`

## Logging

- Each request is logged with `method`, `path`, `status_code`, `duration_ms` and `request_id` (also in response header `X-Request-ID`).
- With `DEBUG=true`, logs are console-friendly; with `DEBUG=false`, JSON (one line per event).
- Unhandled exceptions are logged with full traceback.

## Tests and CI

```bash
pytest tests -v
ruff check app tests
```

CI: `.github/workflows/ci.yml` (Ruff + Pytest with MongoDB service). You can also use **Pytest (current file)** or **Pytest (all)** from the launch menu to run tests under the debugger.
