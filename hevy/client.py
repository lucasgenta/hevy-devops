"""HTTP client for the Hevy API v1 with auth, retries, and rate limiting."""

from __future__ import annotations

import time
from typing import Any

import httpx

BASE_URL = "https://api.hevyapp.com/v1"

# Max page sizes per endpoint as defined by the API
MAX_PAGE_SIZES: dict[str, int] = {
    "workouts": 10,
    "exercise_templates": 100,
    "routines": 10,
    "routine_folders": 10,
    "body_measurements": 10,
}


class HevyError(Exception):
    """Base exception for Hevy API errors."""


class HevyAuthError(HevyError):
    """Raised on 401/403 authentication failures."""


class HevyRateLimitError(HevyError):
    """Raised on 429 rate limit responses."""


class HevyClient:
    """Thin HTTP wrapper around the Hevy API.

    Handles authentication, pagination helpers, and retry with
    exponential backoff on rate limits.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        max_retries: int = 5,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._max_retries = max_retries
        self._client = httpx.Client(
            headers={"api-key": api_key},
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @staticmethod
    def max_page_size(endpoint: str) -> int:
        """Return the maximum allowed page size for an endpoint."""
        return MAX_PAGE_SIZES.get(endpoint, 10)

    # ------------------------------------------------------------------
    # Low-level request
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Execute an authenticated request with retry-on-429 logic."""
        url = f"{self._base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            response = self._client.request(method, url, **kwargs)

            if response.is_success:
                return response.json()

            if response.status_code == 429:
                retry_after = _parse_retry_after(response)
                wait = retry_after + (attempt * 2)  # additive backoff
                time.sleep(wait)
                last_error = HevyRateLimitError(
                    f"Rate limited. Retrying in {wait}s (attempt {attempt + 1})"
                )
                continue

            if response.status_code in (401, 403):
                raise HevyAuthError(
                    f"Authentication failed ({response.status_code}): "
                    f"{response.text}"
                )

            response.raise_for_status()

        raise HevyError(f"Request failed after {self._max_retries} retries") from last_error

    # ------------------------------------------------------------------
    # Endpoint methods (return raw JSON dicts)
    # ------------------------------------------------------------------

    def get_workouts(self, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        """Fetch a page of workouts."""
        return self._request("GET", "/workouts", params={"page": page, "pageSize": page_size})

    def get_workout_count(self) -> dict[str, Any]:
        """Fetch total workout count."""
        return self._request("GET", "/workouts/count")

    def get_workout(self, workout_id: str) -> dict[str, Any]:
        """Fetch a single workout by ID."""
        return self._request("GET", f"/workouts/{workout_id}")

    def get_exercise_templates(self, page: int = 1, page_size: int = 100) -> dict[str, Any]:
        """Fetch a page of exercise templates."""
        return self._request(
            "GET", "/exercise_templates", params={"page": page, "pageSize": page_size}
        )

    def get_routines(self, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        """Fetch a page of routines."""
        return self._request("GET", "/routines", params={"page": page, "pageSize": page_size})

    def create_routine(self, routine_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new routine in Hevy.

        Args:
            routine_data: Dict matching PostRoutinesRequestBody schema:
                {"routine": {"title": "...", "folder_id": null, "notes": "...", "exercises": [...]}}

        Returns:
            The created routine object.
        """
        return self._request("POST", "/routines", json=routine_data)

    def update_routine(self, routine_id: str, routine_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing routine in Hevy.

        Args:
            routine_id: The ID of the routine to update.
            routine_data: Dict matching PutRoutinesRequestBody schema.

        Returns:
            The updated routine object.
        """
        return self._request("PUT", f"/routines/{routine_id}", json=routine_data)

    def get_routine_folders(self, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        """Fetch a page of routine folders."""
        return self._request(
            "GET", "/routine_folders", params={"page": page, "pageSize": page_size}
        )

    def get_body_measurements(self, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        """Fetch a page of body measurements."""
        return self._request(
            "GET", "/body_measurements", params={"page": page, "pageSize": page_size}
        )

    def get_user_info(self) -> dict[str, Any]:
        """Fetch authenticated user info."""
        return self._request("GET", "/user/info")

    def get_exercise_history(self, template_id: str, **filters: str) -> dict[str, Any]:
        """Fetch exercise history for a given template.

        Optional filters: start_date, end_date (ISO 8601 format).
        """
        params = dict(filters)
        return self._request(
            "GET",
            f"/exercise_history/{template_id}",
            params=params or None,
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> HevyClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def _parse_retry_after(response: httpx.Response) -> float:
    """Extract Retry-After header value, defaulting to 1 second."""
    value = response.headers.get("Retry-After", "1")
    try:
        return float(value)
    except ValueError:
        return 1.0
