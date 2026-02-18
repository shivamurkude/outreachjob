# Local setup and running

## Prerequisites

- Python 3.11+
- MongoDB (local or Docker)
- Redis (local or Docker)

## 1. Environment

```bash
cp .env.example .env
```

Edit `.env` and set at least:

| Variable | Description |
|----------|-------------|
| `MONGODB_URI` | e.g. `mongodb://localhost:27017` |
| `MONGODB_DB_NAME` | e.g. `findmyjob` |
| `REDIS_URL` | e.g. `redis://localhost:6379/0` |
| `SECRET_KEY` | Min 32 characters (used for session signing) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | From Google Cloud Console (OAuth 2.0) |
| `GMAIL_OAUTH_REDIRECT_URI` | e.g. `http://localhost:8000/v1/gmail/oauth/callback` |

Optional for dev: leave `TOKEN_ENCRYPTION_KEY` empty; it will be derived from `SECRET_KEY`.

**Staging / production:** Use the env templates per environment:

| File | Use for |
|------|--------|
| `.env.example` | Local / development reference |
| `.env.staging` | Staging deployment (copy to `.env` or source before run) |
| `.env.production` | Production deployment (copy to `.env` or inject via secrets manager) |

For staging/production, copy the right file to `.env` on the server or set all variables in the environment (e.g. from CI/CD or a secrets manager). Never commit real `.env` with secrets.

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. Run locally

### Option A: VS Code / Cursor launch configs

1. Open the project in VS Code or Cursor.
2. Open **Run and Debug** (Ctrl+Shift+D / Cmd+Shift+D).
3. Choose a configuration and press F5 or the green play button:

| Configuration | Use case |
|---------------|----------|
| **Run API (uvicorn)** | Start FastAPI with hot reload (default port 8000) |
| **Debug API (no reload)** | Start API with debugger (breakpoints work) |
| **Run ARQ Worker** | Start background worker (list processing + send_due_emails cron) |
| **Debug ARQ Worker** | Worker with debugger |
| **API + Worker (run both)** | Start API and Worker in parallel |
| **Pytest (current file)** | Run tests in current file with debugger |
| **Pytest (all)** | Run full test suite |

Ensure `PYTHONPATH` is the project root (launch.json sets it via `"env": {"PYTHONPATH": "${workspaceFolder}"}`).

### Option B: Terminal

**API:**

```bash
# From project root
export PYTHONPATH=.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Worker (separate terminal):**

```bash
export PYTHONPATH=.
python -m app.worker.run_worker
```

**Health check:**

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

**Interactive API docs:**

- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 4. Docker (optional)

Run MongoDB and Redis locally without installing them:

```bash
docker run -d -p 27017:27017 --name mongo mongo:7
docker run -d -p 6379:6379 --name redis redis:7-alpine
```

Then use `MONGODB_URI=mongodb://localhost:27017` and `REDIS_URL=redis://localhost:6379/0` in `.env`.

## 5. Logging

- **Development:** With `DEBUG=true`, logs are human-readable (structlog console).
- **Production:** With `DEBUG=false`, logs are JSON (one line per event).
- Every request is logged with: `method`, `path`, `status_code`, `duration_ms`, and `request_id` (also in response header `X-Request-ID`).
- Unhandled exceptions are logged with full traceback.
