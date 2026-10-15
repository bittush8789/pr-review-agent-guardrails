# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime

# Security hardening: Prevent bytecode generation and unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-privileged service user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

WORKDIR /workspace

# Install dependencies separately for optimal layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source and configuration
COPY app/ ./app/
COPY pyproject.toml .

# Set ownership to unprivileged user
RUN chown -R appuser:appgroup /workspace

USER appuser

# Entrypoint executes review agent orchestrator
ENTRYPOINT ["python", "-m", "app.main"]
