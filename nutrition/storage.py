"""JSON file storage for meal logs, mirroring hevy/storage.py."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nutrition.models import MealEntry


class NutritionStorage:
    """Persists meal entries to structured JSON files.

    Files organized as::

        data/nutrition/{YYYY}/{MM}/{YYYY-MM-DD}.json
    """

    def __init__(self, root: str | Path = "data/nutrition") -> None:
        self._root = Path(root)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_entry(self, entry: MealEntry) -> Path:
        """Append a single meal entry to the day's file.

        Returns the path of the written file.
        """
        day = entry.timestamp[:10]  # YYYY-MM-DD
        path = self._day_path(day)
        entries = self._load_day(day)
        entries.append(entry.to_dict())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, indent=2, ensure_ascii=False))
        return path

    def save_entries(self, day: str, entries: list[MealEntry]) -> Path:
        """Overwrite all entries for a given day."""
        path = self._day_path(day)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([e.to_dict() for e in entries], indent=2, ensure_ascii=False),
        )
        return path

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_day(self, day: str) -> list[MealEntry]:
        """Load all meal entries for a specific date (YYYY-MM-DD)."""
        return [MealEntry.from_dict(e) for e in self._load_day(day)]

    def load_range(self, start: str, end: str) -> dict[str, list[MealEntry]]:
        """Load meal entries for a date range. Returns {date: [entries]}."""
        result: dict[str, list[MealEntry]] = {}
        current = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
        from datetime import timedelta

        while current <= end_date:
            day_str = current.isoformat()
            entries = self.load_day(day_str)
            if entries:
                result[day_str] = entries
            current += timedelta(days=1)
        return result

    def load_all_days(self) -> dict[str, list[MealEntry]]:
        """Load ALL logged days across all files."""
        result: dict[str, list[MealEntry]] = {}
        for path in sorted(self._root.rglob("*.json")):
            # Extract date from filename: YYYY-MM-DD.json
            day = path.stem
            try:
                datetime.strptime(day, "%Y-%m-%d")
            except ValueError:
                continue
            entries = self.load_day(day)
            if entries:
                result[day] = entries
        return result

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_entry(self, entry_id: str, day: str) -> bool:
        """Remove a single entry by ID from a day's file. Returns True if found."""
        entries = self._load_day(day)
        filtered = [e for e in entries if e.get("id") != entry_id]
        if len(filtered) == len(entries):
            return False
        self.save_entries(day, [MealEntry.from_dict(e) for e in filtered])
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _day_path(self, day: str) -> Path:
        """Return the file path for a given date."""
        try:
            dt = datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            dt = datetime.now()
        return self._root / str(dt.year) / f"{dt.month:02d}" / f"{day}.json"

    def _load_day(self, day: str) -> list[dict[str, Any]]:
        """Load raw dict entries for a date (no MealEntry wrapping)."""
        path = self._day_path(day)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, OSError):
            return []


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
