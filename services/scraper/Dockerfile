# syntax=docker/dockerfile:1
# =============================================================================
# Hevy Scraper — Multi-stage Docker build
# =============================================================================
# Stage 1: Builder — install Python dependencies
FROM python:3.12-slim AS builder

WORKDIR /app
COPY services/scraper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy application source
COPY hevy/       hevy/
COPY scripts/    scripts/

# Ensure data directory exists
RUN mkdir -p /app/data

# Health check — verifies the process is alive
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD kill -0 1 2>/dev/null || exit 1

# Entrypoint runs the scrape on start and then loops on a schedule
COPY services/scraper/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
