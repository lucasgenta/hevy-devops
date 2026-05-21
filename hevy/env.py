"""Simple .env file loader — no external dependencies required.

Looks for a `.env` file in the project root directory and loads
key=value pairs into the environment.

Usage::

    from hevy.env import load_dotenv
    load_dotenv()  # loads .env from project root → os.environ
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(dotenv_path: str | Path | None = None) -> bool:
    """Load variables from a .env file into os.environ.

    Args:
        dotenv_path: Path to .env file. Defaults to ``<project-root>/.env``.

    Returns:
        True if a .env file was found and loaded, False otherwise.
    """
    if dotenv_path is None:
        dotenv_path = _discover_dotenv()

    path = Path(dotenv_path)
    if not path.is_file():
        return False

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'").strip()

        # Only set if not already present (env vars take precedence)
        if key and key not in os.environ:
            os.environ[key] = value

    return True


def _discover_dotenv() -> Path:
    """Walk up from this file's location to find the project root .env."""
    here = Path(__file__).resolve().parent  # hevy/
    # Walk up until we find .env or hit root
    for parent in [here, *here.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    # Fallback: look in the current working directory
    return Path.cwd() / ".env"
