# ── Stage 1: base ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Don't write .pyc files, don't buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: app ──────────────────────────────────────────────────────────────
FROM base AS app

# Copy full project
COPY . .

# Create a non-root user for security
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
USER appuser

# DB lives inside the container at /app/securevote.db
# Mount a volume here in production to persist data
VOLUME ["/app/securevote.db"]

EXPOSE 5000

# Initialise DB then start gunicorn
# For development swap CMD to: ["python", "app.py"]
CMD ["sh", "-c", "python -c 'import sys; sys.path.insert(0,\"..\"); from src.backend.db import init_db,migrate_db,seed_db; init_db(); migrate_db(); seed_db()' && gunicorn --bind 0.0.0.0:5000 --workers 2 app:app"]
