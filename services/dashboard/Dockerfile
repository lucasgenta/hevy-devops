# syntax=docker/dockerfile:1
# =============================================================================
# Hevy Dashboard — Multi-stage Docker build
# =============================================================================
# Stage 1: Builder — install Python dependencies
FROM python:3.14-slim AS builder

WORKDIR /app
COPY services/dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime — minimal image with only what's needed
FROM python:3.14-slim

WORKDIR /app

# Copy installed packages + executables (streamlit, etc.) from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application source (shared across services)
COPY hevy/       hevy/
COPY nutrition/  nutrition/
COPY pwa/        pwa/
COPY scripts/    scripts/

# Ensure data directory exists
RUN mkdir -p /app/data

# Streamlit port
EXPOSE 8501

# Health check — verifies the Streamlit server is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python scripts/healthcheck.py --service dashboard

# Default: launch the Streamlit dashboard
CMD ["streamlit", "run", "hevy/dashboard/app.py", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.address=0.0.0.0", \
     "--server.enableCORS=false"]
