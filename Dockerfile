# Author: Oleh Riabtsev
# File: Dockerfile
# Created: 2026-11-23
# Version: 1.2.0

FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install curl for container health checks and clean up apt cache
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create a dedicated non-root user for running the application
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Install Python dependencies first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code, Alembic migrations, tests, and configuration templates
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY tests/ ./tests/
COPY alembic.ini .
COPY pytest.ini .
COPY workflows.yaml .
COPY locales.yaml .

# Prepare runtime uploads directory and assign ownership to the non-root user
RUN mkdir -p /app/uploads \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Apply pending Alembic database migrations before starting Uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
