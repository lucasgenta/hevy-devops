"""Transform raw scraped JSON into structured pandas DataFrames."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .anatomy import AnatomyMapper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALLOWED_EXT = {".json"}


def _discover_files(root: str | Path, endpoint: str) -> list[Path]:
    """Return sorted JSON files for a given endpoint directory."""
    directory = Path(root) / endpoint
    if not directory.exists():
        return []
    return sorted(
        p for p in directory.iterdir()
        if p.suffix in _ALLOWED_EXT and not p.name.startswith(".")
    )


def _load_json(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def _resolve_path(base: str) -> str:
    """Resolve 'data/raw' relative to project root or make absolute."""
    p = Path(base)
    if p.exists():
        return str(p.resolve())
    return base


# ---------------------------------------------------------------------------
# DataFrames
# ---------------------------------------------------------------------------


def build_workout_sets_df(
    raw_dir: str = "data/raw",
    mapper: AnatomyMapper | None = None,
) -> pd.DataFrame:
    """Build a flat DataFrame with one row per set across all workouts.

    Columns:
        workout_id, workout_title, start_time, end_time, duration_min,
        exercise_index, exercise_title, exercise_template_id,
        set_index, set_type, weight_kg, reps, volume_kg, distance_meters,
        duration_seconds, rpe, custom_metric, primary_muscle_group,
        muscle_heads (list of specific heads)
    """
    rows: list[dict[str, Any]] = []
    raw_dir = _resolve_path(raw_dir)

    for path in _discover_files(raw_dir, "workouts"):
        payload = _load_json(path)
        data = payload.get("data", {})
        workouts = data.get("workouts", [])

        for w in workouts:
            wid = w.get("id", "")
            title = w.get("title", "")
            start = w.get("start_time", "")
            end = w.get("end_time", "")

            duration = _calc_duration_min(start, end)

            for ex in w.get("exercises", []):
                ex_idx = ex.get("index", 0)
                ex_title = ex.get("title", "")
                ex_tid = ex.get("exercise_template_id", "")
                ex_notes = ex.get("notes", "")

                for s in ex.get("sets", []):
                    wkg = s.get("weight_kg")
                    reps = s.get("reps")
                    volume = (wkg or 0) * (reps or 0)

                    rows.append({
                        "workout_id": wid,
                        "workout_title": title,
                        "start_time": start,
                        "end_time": end,
                        "duration_min": duration,
                        "exercise_index": ex_idx,
                        "exercise_title": ex_title,
                        "exercise_template_id": ex_tid,
                        "exercise_notes": ex_notes,
                        "set_index": s.get("index", 0),
                        "set_type": s.get("type", ""),
                        "weight_kg": wkg,
                        "reps": reps,
                        "volume_kg": volume,
                        "distance_meters": s.get("distance_meters"),
                        "duration_seconds": s.get("duration_seconds"),
                        "rpe": s.get("rpe"),
                        "custom_metric": s.get("custom_metric"),
                    })

    df = pd.DataFrame(rows)

    if mapper is not None and not df.empty:
        df = _enrich_with_muscle_heads(df, mapper)

    return df


def build_exercise_templates_df(raw_dir: str = "data/raw") -> pd.DataFrame:
    """DataFrame of all exercise templates."""
    rows: list[dict[str, Any]] = []
    raw_dir = _resolve_path(raw_dir)

    for path in _discover_files(raw_dir, "exercise_templates"):
        payload = _load_json(path)
        for t in payload.get("data", {}).get("exercise_templates", []):
            rows.append({
                "id": t.get("id", ""),
                "title": t.get("title", ""),
                "type": t.get("type", ""),
                "primary_muscle_group": t.get("primary_muscle_group", ""),
                "secondary_muscle_groups": ",".join(t.get("secondary_muscle_groups", [])),
                "is_custom": t.get("is_custom", False),
            })

    return pd.DataFrame(rows)


def build_body_measurements_df(raw_dir: str = "data/raw") -> pd.DataFrame:
    """DataFrame of body measurements over time."""
    rows: list[dict[str, Any]] = []
    raw_dir = _resolve_path(raw_dir)

    for path in _discover_files(raw_dir, "body_measurements"):
        payload = _load_json(path)
        for m in payload.get("data", {}).get("body_measurements", []):
            rows.append({
                "date": m.get("date", ""),
                "weight_kg": m.get("weight_kg"),
                "lean_mass_kg": m.get("lean_mass_kg"),
                "fat_percent": m.get("fat_percent"),
                "neck_cm": m.get("neck_cm"),
                "shoulder_cm": m.get("shoulder_cm"),
                "chest_cm": m.get("chest_cm"),
                "left_bicep_cm": m.get("left_bicep_cm"),
                "right_bicep_cm": m.get("right_bicep_cm"),
                "left_forearm_cm": m.get("left_forearm_cm"),
                "right_forearm_cm": m.get("right_forearm_cm"),
                "abdomen_cm": m.get("abdomen"),
                "waist_cm": m.get("waist"),
                "hips_cm": m.get("hips"),
                "left_thigh_cm": m.get("left_thigh"),
                "right_thigh_cm": m.get("right_thigh"),
                "left_calf_cm": m.get("left_calf"),
                "right_calf_cm": m.get("right_calf"),
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
    return df


def build_routines_df(raw_dir: str = "data/raw") -> pd.DataFrame:
    """DataFrame of routines with exercises and sets."""
    rows: list[dict[str, Any]] = []
    raw_dir = _resolve_path(raw_dir)

    for path in _discover_files(raw_dir, "routines"):
        payload = _load_json(path)
        for r in payload.get("data", {}).get("routines", []):
            for ex in r.get("exercises", []):
                for s in ex.get("sets", []):
                    rows.append({
                        "routine_id": r.get("id", ""),
                        "routine_title": r.get("title", ""),
                        "folder_id": r.get("folder_id"),
                        "exercise_index": ex.get("index", 0),
                        "exercise_title": ex.get("title", ""),
                        "exercise_template_id": ex.get("exercise_template_id", ""),
                        "rest_seconds": ex.get("rest_seconds"),
                        "set_index": s.get("index", 0),
                        "set_type": s.get("type", ""),
                        "weight_kg": s.get("weight_kg"),
                        "reps": s.get("reps"),
                        "rep_range_start": s.get("rep_range", {}).get("start") if s.get("rep_range") else None,
                        "rep_range_end": s.get("rep_range", {}).get("end") if s.get("rep_range") else None,
                    })

    return pd.DataFrame(rows)


def build_workout_summary_df(raw_dir: str = "data/raw") -> pd.DataFrame:
    """One row per workout with summary stats (duration, total volume, exercise count)."""
    raw_dir = _resolve_path(raw_dir)
    rows: list[dict[str, Any]] = []

    for path in _discover_files(raw_dir, "workouts"):
        payload = _load_json(path)
        for w in payload.get("data", {}).get("workouts", []):
            exercises = w.get("exercises", [])
            total_volume = 0
            total_sets = 0
            for ex in exercises:
                for s in ex.get("sets", []):
                    wkg = s.get("weight_kg") or 0
                    reps = s.get("reps") or 0
                    total_volume += wkg * reps
                    total_sets += 1

            rows.append({
                "workout_id": w.get("id", ""),
                "title": w.get("title", ""),
                "start_time": w.get("start_time", ""),
                "end_time": w.get("end_time", ""),
                "duration_min": _calc_duration_min(w.get("start_time"), w.get("end_time")),
                "description": w.get("description", ""),
                "routine_id": w.get("routine_id"),
                "exercise_count": len(exercises),
                "total_sets": total_sets,
                "total_volume_kg": total_volume,
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["start_time"] = pd.to_datetime(df["start_time"])
        df = df.sort_values("start_time").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _calc_duration_min(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return (e - s).total_seconds() / 60
    except (ValueError, TypeError):
        return None


def _enrich_with_muscle_heads(
    df: pd.DataFrame,
    mapper: AnatomyMapper,
) -> pd.DataFrame:
    """Add columns for specific muscle heads using the anatomy mapper."""

    # Pre-compute template → muscle group mapping from exercise_templates
    # We need templates loaded to know the Hevy muscle group per exercise
    # For now, we add heads based on title matching

    def get_heads(title: str) -> list[dict]:
        return mapper.get_heads(title)

    df["muscle_heads"] = df["exercise_title"].apply(get_heads)
    df["muscle_head_names"] = df["muscle_heads"].apply(
        lambda hs: [h["name"] for h in hs] if hs else []
    )
    df["primary_muscle_head"] = df["muscle_heads"].apply(
        lambda hs: next(
            (h["name"] for h in hs if h.get("role") == "primary"),
            hs[0]["name"] if hs else None,
        )
        if hs else None
    )
    return df
