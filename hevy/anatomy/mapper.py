"""Matches exercise titles to specific muscle heads using keyword patterns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_YAML_PATH = Path(__file__).resolve().parent / "data" / "muscle_map.yaml"


class AnatomyMapper:
    """Maps exercise names to specific muscle heads/regions.

    Uses keyword-based pattern matching against a curated YAML mapping
    of exercise types → muscle heads with activation levels.

    Usage::

        mapper = AnatomyMapper()
        result = mapper.match("Incline Bench Press (Dumbbell)")
        # => {"muscle": "chest", "heads": [
        #      {"name": "upper_chest", "role": "primary", "activation": "high"},
        #      ...
        #    ]}
    """

    def __init__(self, yaml_path: str | Path | None = None) -> None:
        self._patterns = _load_patterns(yaml_path or _YAML_PATH)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def match(self, exercise_title: str) -> dict[str, Any] | None:
        """Return the best matching muscle-head mapping for a title.

        Returns None if no pattern matches.
        """
        title_lower = exercise_title.lower()

        best: dict[str, Any] | None = None
        best_keyword_len = 0

        for entry in self._patterns:
            keywords = entry.get("keywords", [])
            for kw in keywords:
                if kw.lower() in title_lower:
                    # Prefer the longest (most specific) keyword match
                    if len(kw) > best_keyword_len:
                        best = entry
                        best_keyword_len = len(kw)
                    break

        return best

    def match_or_fallback(self, exercise_title: str, hevy_muscle_group: str) -> dict[str, Any]:
        """Try to match, falling back to a generic mapping using the Hevy group."""
        result = self.match(exercise_title)
        if result is not None:
            return result
        return _fallback_for(hevy_muscle_group, exercise_title)

    def get_heads(
        self,
        exercise_title: str,
        hevy_muscle_group: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return only the specific muscle heads for an exercise."""
        result = self.match(exercise_title)
        if result is not None:
            return result["heads"]
        if hevy_muscle_group:
            fallback = _fallback_for(hevy_muscle_group, exercise_title)
            return fallback["heads"]
        return []

    def all_muscle_heads(self) -> list[str]:
        """Return every distinct muscle head name in the mapping."""
        seen: set[str] = set()
        for entry in self._patterns:
            for h in entry.get("heads", []):
                seen.add(h["name"])
        return sorted(seen)


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

def _load_patterns(path: Path) -> list[dict[str, Any]]:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return raw.get("patterns", [])


def _fallback_for(hevy_group: str, title: str) -> dict[str, Any]:
    """Generate a generic muscle-head mapping when no pattern matches."""
    group_lower = hevy_group.lower()

    # Map Hevy muscle groups to generic head names
    generic: dict[str, list[dict[str, str]]] = {
        "chest": [{"name": "chest_generic", "role": "primary", "activation": "moderate"}],
        "triceps": [{"name": "triceps_generic", "role": "primary", "activation": "moderate"}],
        "biceps": [{"name": "biceps_generic", "role": "primary", "activation": "moderate"}],
        "shoulders": [{"name": "shoulders_generic", "role": "primary", "activation": "moderate"}],
        "quadriceps": [{"name": "quads_generic", "role": "primary", "activation": "moderate"}],
        "hamstrings": [{"name": "hamstrings_generic", "role": "primary", "activation": "moderate"}],
        "glutes": [{"name": "glutes_generic", "role": "primary", "activation": "moderate"}],
        "lats": [{"name": "lats_generic", "role": "primary", "activation": "moderate"}],
        "upper_back": [{"name": "upper_back_generic", "role": "primary", "activation": "moderate"}],
        "lower_back": [{"name": "lower_back_generic", "role": "primary", "activation": "moderate"}],
        "traps": [{"name": "traps_generic", "role": "primary", "activation": "moderate"}],
        "abdominals": [{"name": "abs_generic", "role": "primary", "activation": "moderate"}],
        "calves": [{"name": "calves_generic", "role": "primary", "activation": "moderate"}],
        "forearms": [{"name": "forearms_generic", "role": "primary", "activation": "moderate"}],
        "cardio": [{"name": "cardio_generic", "role": "primary", "activation": "low"}],
        "full_body": [{"name": "full_body_generic", "role": "primary", "activation": "low"}],
        "abductors": [{"name": "abductors_generic", "role": "primary", "activation": "moderate"}],
        "adductors": [{"name": "adductors_generic", "role": "primary", "activation": "moderate"}],
        "neck": [{"name": "neck_generic", "role": "primary", "activation": "moderate"}],
        "other": [{"name": "other_generic", "role": "primary", "activation": "low"}],
    }

    heads = generic.get(group_lower, [{"name": f"{hevy_group}_generic", "role": "primary", "activation": "low"}])
    return {"muscle": hevy_group, "heads": heads}
