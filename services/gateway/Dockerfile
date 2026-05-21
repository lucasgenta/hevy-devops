# syntax=docker/dockerfile:1
# =============================================================================
# Hevy Gateway — Nginx reverse proxy with load balancing
# =============================================================================
FROM nginx:1.27-alpine

# Remove default nginx config
RUN rm -f /etc/nginx/conf.d/default.conf

# Copy custom config
COPY services/gateway/nginx.conf /etc/nginx/nginx.conf

# Health check via the /healthz endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:80/healthz || exit 1

EXPOSE 80
