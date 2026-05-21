"""JSON file storage for scraped API data."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonStorage:
    """Writes scraped API responses to structured JSON files.

    Files are organized as::

        data/raw/{endpoint}/{timestamp}_{page}.json
    """

    def __init__(self, root: str | Path = "data/raw") -> None:
        self._root = Path(root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_page(
        self,
        endpoint: str,
        page: int,
        data: dict[str, Any],
    ) -> Path:
        """Save a single page response to disk.

        Returns the path of the written file.
        """
        directory = self._root / endpoint
        directory.mkdir(parents=True, exist_ok=True)

        timestamp = _now_tag()
        filename = f"{timestamp}_page_{page:04d}.json"
        path = directory / filename

        # Enrich with scrape metadata
        payload = {
            "_meta": {
                "endpoint": endpoint,
                "page": page,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
            "data": data,
        }

        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return path

    def save_workout_events(
        self,
        page: int,
        data: dict[str, Any],
    ) -> Path:
        """Save workout events separately."""
        return self.save_page("workout_events", page, data)

    def save_single(self, endpoint: str, data: dict[str, Any]) -> Path:
        """Save a non-paginated response."""
        return self.save_page(endpoint, 0, data)

    def save_exercise_history(
        self,
        template_id: str,
        data: dict[str, Any],
    ) -> Path:
        """Save exercise history for a specific template."""
        directory = self._root / "exercise_history"
        directory.mkdir(parents=True, exist_ok=True)

        timestamp = _now_tag()
        filename = f"{timestamp}_{template_id}.json"
        path = directory / filename

        payload = {
            "_meta": {
                "endpoint": "exercise_history",
                "exercise_template_id": template_id,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            },
            "data": data,
        }

        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return path

    def list_scraped_runs(self, endpoint: str) -> list[Path]:
        """Return all scraped files for an endpoint, sorted by name."""
        directory = self._root / endpoint
        if not directory.exists():
            return []
        return sorted(directory.iterdir())


def _now_tag() -> str:
    """Return a compact timestamp string for filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
