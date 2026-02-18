# Run backend locally (with staging DB, local Redis)

Use **staging MongoDB** and other staging secrets, but **Redis on your machine** (no VPN/tunnel).

## 1. Start Redis

**Option A – Docker Compose (recommended)**

```bash
docker compose up -d
```

**Option B – Script**

```bash
./scripts/start-redis.sh
```

**Option C – One-off Docker**

```bash
docker run -d -p 6379:6379 --name findmyjob-redis redis:7-alpine
```

## 2. Run the API

- **VS Code / Cursor:** Run and Debug → choose **"API (staging local)"** → F5.
- **Terminal:**

  ```bash
  cp .env.staging.local .env   # optional, only if you run without envFile
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
  ```

API: **http://localhost:8000** (e.g. http://localhost:8000/health)

## 3. Optional: run the worker

- **VS Code:** Run **"Worker (staging local)"**.
- **Terminal:** `python -m app.worker.run_worker`

## Env file

`.env.staging.local` already points to:

- Staging MongoDB Atlas
- **Local Redis:** `redis://localhost:6379/0`

No PEM, VPN, or staging Redis access needed.
