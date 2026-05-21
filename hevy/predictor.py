"""Progressive overload predictor — suggests next weight/reps for each exercise."""

from __future__ import annotations

from typing import Any

import pandas as pd

# Default increment by movement pattern
WEIGHT_INCREMENT: dict[str, float] = {
    "bench": 2.5,
    "press": 2.5,
    "curl": 1.25,
    "extension": 1.25,
    "fly": 1.25,
    "row": 2.5,
    "pulldown": 2.5,
    "pull": 2.5,
    "squat": 5.0,
    "deadlift": 5.0,
    "leg press": 5.0,
    "lunge": 2.5,
    "hip thrust": 5.0,
    "calf": 2.5,
    "raise": 1.25,
    "shrug": 2.5,
    "core": 1.25,
    "triceps": 1.25,
    "biceps": 1.25,
    "shoulder": 2.5,
    "lat": 2.5,
    "chest": 2.5,
}

DEFAULT_INCREMENT = 2.5


def suggest_next_session(
    sets_df: pd.DataFrame,
    exercise_title: str,
    routine_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Suggest weight and reps for the next session of an exercise.

    Args:
        sets_df: Full workout sets DataFrame.
        exercise_title: Exact exercise title to analyze.
        routine_df: Optional routine data to know target rep ranges.

    Returns:
        Dict with 'exercise', 'suggested_weight_kg', 'suggested_reps',
        'last_weight_kg', 'last_reps', 'confidence', and 'reasoning'.
    """
    # Get all sets for this exercise, sorted by date
    ex_df = sets_df[sets_df["exercise_title"] == exercise_title].copy()
    if ex_df.empty or ex_df["weight_kg"].isna().all():
        return {
            "exercise": exercise_title,
            "suggested_weight_kg": None,
            "suggested_reps": None,
            "last_weight_kg": None,
            "last_reps": None,
            "confidence": "low",
            "reasoning": "No weighted data found for this exercise.",
        }

    ex_df = ex_df.dropna(subset=["weight_kg"])
    if ex_df.empty:
        return {
            "exercise": exercise_title,
            "suggested_weight_kg": None,
            "suggested_reps": None,
            "last_weight_kg": None,
            "last_reps": None,
            "confidence": "low",
            "reasoning": "No weighted data found for this exercise.",
        }

    ex_df = ex_df.sort_values("start_time")
    last_set = ex_df.iloc[-1]
    last_weight = last_set["weight_kg"]
    last_reps = last_set["reps"] if pd.notna(last_set["reps"]) else None

    if last_weight is None or last_weight == 0:
        return {
            "exercise": exercise_title,
            "suggested_weight_kg": None,
            "suggested_reps": None,
            "last_weight_kg": None,
            "last_reps": None,
            "confidence": "low",
            "reasoning": "Last set had no weight logged.",
        }

    # Determine target rep range from routine if available
    target_reps_high = _get_target_rep_high(exercise_title, routine_df)

    # Get the last N sessions (group by workout_id)
    ex_df["session"] = ex_df["workout_id"]
    sessions = ex_df.groupby("session").agg({
        "weight_kg": "max",
        "reps": "max",
        "start_time": "first",
    }).sort_values("start_time")

    last_session = sessions.iloc[-1] if len(sessions) > 0 else None
    prev_session = sessions.iloc[-2] if len(sessions) > 1 else None

    # Determine if the user hit the top of their rep range
    reached_target = False
    if last_reps and target_reps_high:
        reached_target = last_reps >= target_reps_high

    # Check progression trend
    progressing = False
    if last_session is not None and prev_session is not None:
        if last_session["weight_kg"] > prev_session["weight_kg"]:
            progressing = True
        elif (last_session["weight_kg"] == prev_session["weight_kg"]
              and last_session["reps"] > prev_session["reps"]):
            progressing = True

    # Calculate increment
    increment = _get_increment(exercise_title)

    # Build suggestion
    if reached_target and last_weight:
        # Hit target reps → increase weight, drop reps back
        suggested_weight = last_weight + increment
        suggested_reps = max(target_reps_high - 2, 6) if target_reps_high else max(last_reps - 2, 6)
        reasoning = (
            f"Hit {last_reps} reps (target ≥{target_reps_high}). "
            f"Increase weight by {increment}kg to {suggested_weight}kg."
        )
        confidence = "high" if progressing else "medium"
    elif last_reps is not None and target_reps_high and last_reps < target_reps_high:
        # Didn't hit target reps → stay at same weight, aim for more reps
        suggested_weight = last_weight
        suggested_reps = last_reps + 1
        reasoning = (
            f"Got {last_reps}/{target_reps_high} reps. "
            f"Stay at {last_weight}kg and aim for {suggested_reps} reps."
        )
        confidence = "high"
    elif last_weight:
        # No routine context — use simple trend
        if progressing:
            suggested_weight = last_weight + (increment / 2)
            suggested_reps = last_reps or 8
            reasoning = f"Trending up. Try {suggested_weight}kg × {suggested_reps} reps."
            confidence = "medium"
        else:
            suggested_weight = last_weight
            suggested_reps = last_reps or 8
            reasoning = f"Hold at {last_weight}kg. Focus on form and add reps."
            confidence = "low"
    else:
        suggested_weight = None
        suggested_reps = None
        reasoning = "Insufficient data."
        confidence = "low"

    return {
        "exercise": exercise_title,
        "suggested_weight_kg": suggested_weight,
        "suggested_reps": int(suggested_reps) if suggested_reps else None,
        "last_weight_kg": last_weight,
        "last_reps": int(last_reps) if last_reps else None,
        "confidence": confidence,
        "reasoning": reasoning,
    }


def suggest_all_exercises(
    sets_df: pd.DataFrame,
    routines_df: pd.DataFrame | None = None,
    min_sets: int = 3,
) -> list[dict[str, Any]]:
    """Get overload suggestions for all exercises with enough data."""
    suggestions = []
    for ex in sets_df["exercise_title"].unique():
        ex_sets = sets_df[sets_df["exercise_title"] == ex]
        if len(ex_sets) < min_sets:
            continue
        suggestion = suggest_next_session(sets_df, ex, routines_df)
        if suggestion["suggested_weight_kg"] is not None:
            suggestions.append(suggestion)
    return sorted(suggestions, key=lambda s: s["confidence"] == "high", reverse=True)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _get_increment(exercise_title: str) -> float:
    """Determine appropriate weight increment for an exercise."""
    title_lower = exercise_title.lower()
    for keyword, inc in WEIGHT_INCREMENT.items():
        if keyword in title_lower:
            return inc
    return DEFAULT_INCREMENT


def _get_target_rep_high(
    exercise_title: str,
    routine_df: pd.DataFrame | None,
) -> int | None:
    """Get the top of the target rep range from routine data."""
    if routine_df is None or routine_df.empty:
        return None

    exercise_rows = routine_df[
        routine_df["exercise_title"].str.lower() == exercise_title.lower()
    ]
    if exercise_rows.empty:
        return None

    valid = exercise_rows.dropna(subset=["rep_range_end"])
    if valid.empty:
        return None

    return int(valid["rep_range_end"].iloc[0])
