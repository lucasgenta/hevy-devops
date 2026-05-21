"""HTTP client for the Open Food Facts API (NL-focused).

Provides barcode lookup and text search for food products with
complete nutritional data per 100g.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from nutrition.models import FoodItem

WORLD_API = "https://world.openfoodfacts.net"
WORLD_LEGACY = "https://world.openfoodfacts.org"

MAX_RETRIES = 3


class OpenFoodFactsError(Exception):
    """Base exception for Open Food Facts API errors."""


class OpenFoodFactsClient:
    """Thin HTTP wrapper around the Open Food Facts API.

    Free, no API key required. Rate limits are generous.
    All data is per 100g by default.
    """

    def __init__(self, country: str = "nl") -> None:
        self._country = country
        self._client = httpx.Client(timeout=15.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup_barcode(self, barcode: str) -> FoodItem | None:
        """Look up a product by barcode.

        Returns a FoodItem or None if not found.
        Supports both NL and global barcodes (NL barcodes start with 87).
        """
        data = self._get(f"{WORLD_API}/api/v2/product/{barcode}")
        if data is None:
            return None
        if data.get("status") != 1:
            return None
        return FoodItem.from_openfoodfacts(data)

    def search(self, query: str, page_size: int = 10) -> list[FoodItem]:
        """Search for products by name, filtered to the configured country.

        Returns up to ``page_size`` FoodItem results.
        """
        params: dict[str, Any] = {
            "search_terms": query,
            "json": 1,
            "page_size": page_size,
            "countries_tags": self._country,
        }
        data = self._get(f"{WORLD_LEGACY}/cgi/search.pl", params=params)
        if data is None:
            return []
        products = data.get("products", [])
        return [FoodItem.from_openfoodfacts({"product": p}) for p in products]

    def search_all_countries(self, query: str, page_size: int = 10) -> list[FoodItem]:
        """Search across all countries (fallback when NL search yields nothing)."""
        params = {"search_terms": query, "json": 1, "page_size": page_size}
        data = self._get(f"{WORLD_LEGACY}/cgi/search.pl", params=params)
        if data is None:
            return []
        products = data.get("products", [])
        return [FoodItem.from_openfoodfacts({"product": p}) for p in products]

    def search_fast(self, query: str, page_size: int = 10) -> list[FoodItem]:
        """Faster search using the v2 API (NL categories filter)."""
        params: dict[str, Any] = {
            "categories_tags": self._country,
            "search_terms": query,
            "fields": "code,product_name,brands,nutriments",
            "page_size": page_size,
        }
        data = self._get(f"{WORLD_API}/api/v2/search", params=params)
        if data is None:
            return []
        products = data.get("products", [])
        return [FoodItem.from_openfoodfacts({"product": p}) for p in products]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenFoodFactsClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Low-level request with retry
    # ------------------------------------------------------------------

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Execute a GET request with simple retry on failure."""
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.get(url, params=params)

                if response.status_code == 429:
                    time.sleep(2 * (attempt + 1))
                    continue

                if response.status_code == 404:
                    return None

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code in (502, 503, 504):
                    time.sleep(1 * (attempt + 1))
                    last_error = e
                    continue
                return None
            except (httpx.RequestError, httpx.TimeoutException) as e:
                time.sleep(1 * (attempt + 1))
                last_error = e
                continue

        if last_error:
            raise OpenFoodFactsError(f"Request failed after {MAX_RETRIES} retries") from last_error
        return None

    def __repr__(self) -> str:
        return f"OpenFoodFactsClient(country={self._country!r})"
