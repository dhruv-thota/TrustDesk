#!/bin/sh
set -e

# If arguments are provided (e.g. worker daemon), execute them directly
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# Default execution: Backend service initialization and startup
echo "=========================================="
echo "TrustDesk Backend Service Initialization"
echo "=========================================="

# 1. Apply database migrations safely
echo "Applying database migrations (alembic upgrade head)..."
alembic upgrade head

# 2. Ingest demo dataset idempotently
echo "Ingesting demo dataset idempotently (python -m trustdesk.cli ingest)..."
python -m trustdesk.cli ingest --data-dir ./data

# 3. Launch FastAPI backend via Uvicorn
echo "Starting FastAPI backend on 0.0.0.0:8000..."
exec uvicorn trustdesk.main:app --host 0.0.0.0 --port 8000

