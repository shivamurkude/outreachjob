#!/usr/bin/env bash
# Start Redis locally for backend dev. Use with .env.staging.local (REDIS_URL=redis://localhost:6379/0)
set -e
CONTAINER="findmyjob-redis"
if docker ps -q -f name="^${CONTAINER}$" | grep -q .; then
  echo "Redis already running (container: $CONTAINER)"
  exit 0
fi
if docker ps -aq -f name="^${CONTAINER}$" | grep -q .; then
  echo "Starting existing container: $CONTAINER"
  docker start "$CONTAINER"
  exit 0
fi
echo "Starting Redis on port 6379 (container: $CONTAINER)"
docker run -d -p 6379:6379 --name "$CONTAINER" redis:7-alpine
echo "Redis is ready. Run the API via launch.json (API (staging local)) or: uvicorn app.main:app --reload --port 8000"
