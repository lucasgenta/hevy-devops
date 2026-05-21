"""High-level scraper that paginates all Hevy API endpoints and persists results."""

from __future__ import annotations

import time
from typing import Any

from .client import HevyClient
from .storage import JsonStorage


class HevyScraper:
    """Orchestrates scraping of all Hevy API endpoints.

    Iterates through paginated endpoints, calls the client, and saves
    each page through the storage backend.
    """

    def __init__(self, client: HevyClient, storage: JsonStorage) -> None:
        self._client = client
        self._storage = storage

    # ------------------------------------------------------------------
    # Public orchestration
    # ------------------------------------------------------------------

    def scrape_all(self, delay: float = 0.5) -> dict[str, Any]:
        """Scrape every available endpoint and return a summary report.

        *delay* — seconds to wait between pagination requests (be nice).
        """
        summary: dict[str, Any] = {
            "workouts": {"pages": 0, "files": []},
            "exercise_templates": {"pages": 0, "files": []},
            "routines": {"pages": 0, "files": []},
            "routine_folders": {"pages": 0, "files": []},
            "body_measurements": {"pages": 0, "files": []},
            "user_info": None,
        }

        # --- User info (single) ---
        user_data = self._client.get_user_info()
        path = self._storage.save_single("user_info", user_data)
        summary["user_info"] = str(path)

        # --- Paginated endpoints ---
        summary["workouts"]["files"] = self._scrape_paginated(
            "workouts",
            self._client.get_workouts,
            summary["workouts"],
            delay=delay,
        )

        summary["exercise_templates"]["files"] = self._scrape_paginated(
            "exercise_templates",
            self._client.get_exercise_templates,
            summary["exercise_templates"],
            page_size=100,
            delay=delay,
        )

        summary["routines"]["files"] = self._scrape_paginated(
            "routines",
            self._client.get_routines,
            summary["routines"],
            delay=delay,
        )

        summary["routine_folders"]["files"] = self._scrape_paginated(
            "routine_folders",
            self._client.get_routine_folders,
            summary["routine_folders"],
            delay=delay,
        )

        summary["body_measurements"]["files"] = self._scrape_paginated(
            "body_measurements",
            self._client.get_body_measurements,
            summary["body_measurements"],
            delay=delay,
        )

        return summary

    def scrape_workouts_only(self, delay: float = 0.5) -> dict[str, Any]:
        """Scrape only workouts."""
        result: dict[str, Any] = {"pages": 0, "files": []}
        result["files"] = self._scrape_paginated(
            "workouts", self._client.get_workouts, result, delay=delay
        )
        return result

    def scrape_exercise_history(
        self,
        template_ids: list[str],
        delay: float = 0.25,
    ) -> list[str]:
        """Scrape exercise history for a list of template IDs."""
        files: list[str] = []
        for tid in template_ids:
            data = self._client.get_exercise_history(tid)
            path = self._storage.save_exercise_history(tid, data)
            files.append(str(path))
            time.sleep(delay)
        return files

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scrape_paginated(
        self,
        endpoint: str,
        fetch_page_fn: Any,
        result_tracker: dict[str, Any],
        page_size: int | None = None,
        delay: float = 0.5,
    ) -> list[str]:
        """Scrape all pages of a paginated endpoint.

        *fetch_page_fn* is a callable that takes (page, page_size) kwargs.
        *page_size* defaults to the endpoint's API max.
        """
        if page_size is None:
            page_size = self._client.max_page_size(endpoint)

        files: list[str] = []
        page = 1
        page_count = 1  # assume at least 1 page

        while page <= page_count:
            data = fetch_page_fn(page=page, page_size=page_size)
            path = self._storage.save_page(endpoint, page, data)
            files.append(str(path))

            # Update page_count from response (normalised key)
            page_count = data.get("page_count", 1)
            page += 1
            result_tracker["pages"] += 1

            if page <= page_count:
                time.sleep(delay)

        return files
