#!/bin/sh
# =============================================================================
# Hevy Scraper — Entrypoint
# =============================================================================
# Runs the initial scrape on container start, then loops on a configurable
# schedule. This allows the scraper to keep running as a long-lived service
# while periodically refreshing data.
#
# Override the interval via the SCRAPE_INTERVAL environment variable.
# Default: 21600 seconds (6 hours).
#
# Set SCRAPE_ONCE=1 to exit after a single scrape (useful for manual runs).
# =============================================================================
set -e

INTERVAL="${SCRAPE_INTERVAL:-21600}"

echo "[scraper] Starting Hevy Scraper (interval: ${INTERVAL}s)"
echo "[scraper] HEVY_API_KEY is $( [ -n \"$HEVY_API_KEY\" ] && echo 'set' || echo 'NOT SET' )"

while true; do
    echo "[scraper] $(date -u +'%Y-%m-%dT%H:%M:%SZ') — Running scrape..."
    if python scripts/scrape.py; then
        echo "[scraper] ✓ Scrape completed successfully"
    else
        echo "[scraper] ✗ Scrape failed (check your API key and network)"
    fi

    if [ "${SCRAPE_ONCE:-0}" = "1" ]; then
        echo "[scraper] SCRAPE_ONCE=1 — exiting"
        exit 0
    fi

    echo "[scraper] Next scrape in ${INTERVAL}s ($((INTERVAL / 3600))h)..."
    sleep "$INTERVAL"
done
