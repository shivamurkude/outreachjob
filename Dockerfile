# FINDMYJOB v2 API / Worker
FROM python:3.13-slim

WORKDIR /app

# Install system deps if needed (e.g. for PDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Default: run API. Override CMD for worker: python -m app.worker.run_worker
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
