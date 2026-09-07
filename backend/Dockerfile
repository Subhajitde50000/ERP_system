# Multi-stage Dockerfile for FastAPI ERP Backend
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies for C-extensions (e.g. asyncpg, bcrypt, hiredis)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies in a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Final Runtime Stage
FROM python:3.12-slim AS runner

WORKDIR /app

# Install runtime dependencies (curl for healthcheck, libpq for postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create non-root user for security
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/sh -m appuser

# Copy application files
COPY --chown=appuser:appgroup alembic.ini .
COPY --chown=appuser:appgroup app/ ./app/
COPY --chown=appuser:appgroup scripts/ ./scripts/

# Create uploads and logs directories with correct permissions
RUN mkdir -p uploads logs && chown -R appuser:appgroup uploads logs /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
