"""Convert AI Coach suggestions into executable Hevy API routine changes."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import pandas as pd

from hevy.client import HevyClient
from hevy.llm.providers import LLMProvider


def extract_routine_from_suggestion(
    suggestion_text: str,
    templates_df: pd.DataFrame,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Parse an AI Coach suggestion into structured Hevy routine data.

    Uses the LLM to extract exercises, sets, and rep schemes from free text,
    then returns a list of routine dicts ready for the Hevy API.

    The LLM outputs generic exercise names — we match them to your actual
    exercise templates using fuzzy matching server-side.

    Args:
        suggestion_text: The AI Coach's suggestion text.
        templates_df: Exercise templates DataFrame with 'title' and 'id' columns.
        api_key: Deepseek API key (defaults to DEEPSEEK_API_KEY env var).

    Returns:
        List of routine dicts matching the Hevy API create format.
    """
    template_map = dict(zip(templates_df["title"], templates_df["id"]))

    last_error = None
    for attempt in range(3):
        try:
            return _do_extract(suggestion_text, template_map, api_key)
        except ValueError as e:
            last_error = e

    raise ValueError(
        f"Could not parse suggestion after 3 attempts.\n"
        f"Last error: {last_error}\n\n"
        f"Try rephrasing with specific exercise names."
    )


def push_routine_to_hevy(
    routine_data: dict[str, Any],
    hevy_api_key: str | None = None,
) -> dict[str, Any]:
    """Create a routine in Hevy via the API.

    Args:
        routine_data: Single routine dict matching PostRoutinesRequestBody.
        hevy_api_key: Hevy API key (defaults to HEVY_API_KEY env var).

    Returns:
        The API response.
    """
    api_key = hevy_api_key or os.environ.get("HEVY_API_KEY")
    if not api_key:
        raise ValueError("HEVY_API_KEY required. Set it in .env or pass hevy_api_key=.")

    client = HevyClient(api_key)
    try:
        result = client.create_routine(routine_data)
        return result
    finally:
        client.close()


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a JSON-only API. Convert workout suggestions into valid JSON arrays.

Rules:
- Output ONLY a JSON array — no explanations, no markdown, no code fences, no greetings
- Use GENERIC exercise names like "Bench Press", "Squat", "Face Pull" — NOT template IDs
- Each element has: "title" (routine name), "exercises" (array)
- Each exercise has: "name" (string), "sets" (array)
- Each set has: "weight_kg" (number or null), "reps" (number), "type" ("normal")
- If weight is not mentioned, use null
- If a rep range like "8-12" is given, use the higher number
- If multiple training days are mentioned, create separate objects for each
- Be concise — ONLY output the JSON array"""


def _do_extract(
    suggestion: str,
    template_map: dict[str, str],
    api_key: str | None,
) -> list[dict[str, Any]]:
    """Attempt extraction — LLM outputs generic names, we fuzzy-match to templates."""
    prompt = (
        f"Extract workout routines from this suggestion. Return ONLY a JSON array.\n\n"
        f"Suggestion:\n{suggestion}\n\n"
        f'Example: [{{"title":"Upper A","exercises":[{{"name":"Bench Press","sets":[{{"weight_kg":80,"reps":8,"type":"normal"}}]}}]}}]'
    )

    provider = LLMProvider(
        "deepseek",
        api_key=api_key,
        temperature=0.05,
        max_tokens=4096,
    )

    response = provider.chat(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=_SYSTEM_PROMPT,
    )
    provider.close()

    parsed = _extract_json(response.content)

    # Normalize to list of routines
    if isinstance(parsed, dict):
        routines_data = parsed.get("routines", [parsed])
    elif isinstance(parsed, list):
        routines_data = parsed
    else:
        raise ValueError(f"Unexpected JSON structure: {type(parsed).__name__}")

    # Fuzzy-match exercise names to templates
    result = []
    for entry in routines_data:
        title = entry.get("title", "AI Suggested Routine")
        exercises_raw = entry.get("exercises", entry.get("exercise", []))

        resolved = []
        for ex in exercises_raw:
            ex_name = ex.get("name", ex.get("exercise_title", ex.get("title", "")))
            if not ex_name:
                continue

            # Find best matching template
            match = _fuzzy_match_exercise(ex_name, template_map)
            if match is None:
                continue

            sets_raw = ex.get("sets", [])
            sets = []
            for s in sets_raw:
                sets.append({
                    "type": s.get("type", "normal"),
                    "weight_kg": s.get("weight_kg"),
                    "reps": s.get("reps"),
                })

            resolved.append({
                "exercise_template_id": match["id"],
                "superset_id": None,
                "rest_seconds": ex.get("rest_seconds", 90),
                "notes": ex.get("notes", ""),
                "sets": sets,
            })

        if resolved:
            result.append({
                "routine": {
                    "title": title,
                    "folder_id": None,
                    "notes": entry.get("notes", "Created by Hevy AI Coach"),
                    "exercises": resolved,
                }
            })

    if not result:
        raise ValueError(
            "No exercises could be matched to your templates. "
            "Make sure the suggestion uses recognizable exercise names."
        )

    return result


def _extract_json(text: str) -> Any:
    """Extract JSON from LLM response, handling various wrapper formats."""
    raw = text.strip()

    # Remove markdown code fences
    raw = re.sub(r'^```(?:json)?\s*\n?', '', raw)
    raw = re.sub(r'\n?```\s*$', '', raw)
    raw = raw.strip()

    # Try parsing directly
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try finding JSON array/object in the text
    for start_char, end_char in [('[', ']'), ('{', '}')]:
        start = raw.find(start_char)
        if start >= 0:
            end = raw.rfind(end_char)
            if end > start:
                candidate = raw[start:end + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue

    raise ValueError(f"No valid JSON found in response. Raw text:\n{raw[:500]}")


def _fuzzy_match_exercise(
    exercise_name: str,
    template_map: dict[str, str],
) -> dict[str, Any] | None:
    """Find the best matching template for a generic exercise name.

    Matching strategy (in order):
    1. Exact match (case-insensitive)
    2. LLM name is a substring of a template title
    3. Template title contains the LLM name
    4. Word-level overlap scoring for best match
    """
    name_lower = exercise_name.lower().strip()
    name_words = set(re.findall(r'\b[a-z0-9]+\b', name_lower))
    # Remove equipment suffixes for matching (e.g., "Bench Press" matches "Bench Press (Barbell)")
    name_core = name_lower.split("(")[0].strip()

    best_match = None
    best_score = 0

    for title, tid in template_map.items():
        title_lower = title.lower()
        title_core = title_lower.split("(")[0].strip()
        title_words = set(re.findall(r'\b[a-z0-9]+\b', title_lower))

        # Exact match (or core match)
        if title_lower == name_lower or title_core == name_core:
            return {"title": title, "id": tid, "match": "exact"}

        # LLM name is contained in template title
        if name_lower in title_lower:
            score = 100 - len(title_lower) * 0.3
            if score > best_score:
                best_score = score
                best_match = {"title": title, "id": tid, "match": "contains"}

        # Template title core matches LLM name core
        if title_core and name_core and title_core == name_core:
            score = 95
            if score > best_score:
                best_score = score
                best_match = {"title": title, "id": tid, "match": "core"}

        # Word overlap scoring
        overlap = name_words & title_words
        if overlap:
            word_score = len(overlap) / max(len(name_words), len(title_words), 1) * 80
            # Bonus for long/distinctive word matches
            for w in overlap:
                if len(w) > 4:
                    word_score += 5
            if word_score > best_score:
                best_score = word_score
                best_match = {"title": title, "id": tid, "match": "fuzzy", "score": round(word_score, 1)}

    return best_match if best_score >= 15 else None
