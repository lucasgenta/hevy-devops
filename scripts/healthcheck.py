#!/usr/bin/env python3
"""Health check utility for Hevy services.

Usage:
    python scripts/healthcheck.py --service dashboard
    python scripts/healthcheck.py --service scraper

Returns exit code 0 if healthy, 1 if unhealthy.
Docker HEALTHCHECK uses the exit code to determine container status.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys


def _check_port(host: str, port: int, timeout: float = 5.0) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    finally:
        sock.close()


def _check_dashboard() -> bool:
    """Dashboard health: Streamlit must be listening on port 8501."""
    return _check_port("localhost", 8501)


def _check_scraper() -> bool:
    """Scraper health: container process is alive (pid 1 exists).

    In a Docker container, pid 1 is the entrypoint. If the entrypoint
    script is running, the container is considered healthy.
    """
    try:
        os.kill(1, 0)  # send null signal — checks if process exists
        return True
    except (OSError, PermissionError):
        return False


def _check_gateway() -> bool:
    """Gateway health: Nginx must be listening on port 80."""
    return _check_port("localhost", 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Health check for Hevy services")
    parser.add_argument(
        "--service",
        required=True,
        choices=["dashboard", "scraper", "gateway"],
        help="Service to check",
    )
    args = parser.parse_args()

    checks = {
        "dashboard": _check_dashboard,
        "scraper": _check_scraper,
        "gateway": _check_gateway,
    }

    healthy = checks[args.service]()
    sys.exit(0 if healthy else 1)


if __name__ == "__main__":
    main()
