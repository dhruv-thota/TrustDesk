FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime curl for health checks
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install python dependencies using pyproject.toml
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

# Copy application source, migrations, and datasets
COPY trustdesk/ trustdesk/
COPY alembic/ alembic/
COPY alembic.ini .
COPY data/ data/
COPY entrypoint.sh .

# Ensure entrypoint script is executable
RUN chmod +x /app/entrypoint.sh

# Create non-root system user and configure permissions
RUN addgroup --system --gid 10001 appgroup && \
    adduser --system --uid 10001 --gid 10001 --no-create-home appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

