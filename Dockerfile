# FINDMYJOB v2 API / Worker (build with --platform linux/amd64 for ECS Fargate)
# Use 3.12 bookworm (full) for reliable MongoDB Atlas TLS; slim can cause TLSV1_ALERT_INTERNAL_ERROR
FROM python:3.12-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Default: run API. Override CMD for worker: python -m app.worker.run_worker
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
