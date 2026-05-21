"""Exercise swap suggestions — recommends replacements to fix muscle imbalances."""

from __future__ import annotations

from typing import Any

import pandas as pd

from hevy.analysis import muscle_group_balance, muscle_head_balance
from hevy.anatomy import AnatomyMapper


def suggest_swaps(
    sets_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    routines_df: pd.DataFrame | None = None,
    n_suggestions: int = 5,
) -> list[dict[str, Any]]:
    """Suggest exercise swaps to address under-trained muscle groups.

    Finds the muscle groups with the lowest volume, then recommends
    exercises from your template library that target those groups but
    aren't already in your routine.

    Args:
        sets_df: Workout sets DataFrame.
        templates_df: Exercise templates DataFrame.
        routines_df: Optional routines DataFrame (to check current exercises).
        n_suggestions: Number of swap suggestions to return.

    Returns:
        List of dicts with 'under_targeted', 'volume_percentage',
        'suggested_exercises', and 'reason'.
    """
    if sets_df.empty or templates_df.empty:
        return []

    balance = muscle_group_balance(sets_df, templates_df)
    if balance.empty:
        return []

    # Get current exercises from routines or recent workouts
    current_exercises = _get_current_exercises(sets_df, routines_df)

    # Find under-trained groups (bottom third by volume)
    balance = balance.sort_values("volume_kg", ascending=True)
    under_threshold = balance["volume_kg"].quantile(0.33)
    under_targeted = balance[balance["volume_kg"] <= under_threshold]

    mapper = AnatomyMapper()
    suggestions: list[dict[str, Any]] = []

    for _, row in under_targeted.iterrows():
        group = row["primary_muscle_group"]
        volume_pct = row["percentage"]

        # Find exercises in templates that target this group
        candidates = templates_df[
            templates_df["primary_muscle_group"].str.lower() == group.lower()
        ]

        # Exclude exercises already being done
        new_exercises = candidates[
            ~candidates["title"].isin(current_exercises)
        ]

        if new_exercises.empty:
            continue

        # Pick top 3 suggestions, sorted by most relevant
        top_exercises = new_exercises.head(3)["title"].tolist()

        # Get specific muscle heads for variety
        head_info = []
        for ex in top_exercises[:2]:
            heads = mapper.get_heads(ex, group)
            head_names = [h["name"].replace("_", " ") for h in heads[:2]]
            head_info.append(f"{ex} (targets: {', '.join(head_names)})")

        suggestions.append({
            "under_targeted": group,
            "volume_percentage": round(volume_pct, 1),
            "suggested_exercises": top_exercises,
            "head_info": head_info,
            "reason": (
                f"Only {volume_pct:.1f}% of total volume. "
                f"Add variety with {', '.join(top_exercises[:2])}."
            ),
        })

        if len(suggestions) >= n_suggestions:
            break

    return suggestions


def suggest_head_swaps(
    sets_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    n_suggestions: int = 5,
) -> list[dict[str, Any]]:
    """Suggest swaps targeting specific under-trained muscle heads."""
    if "muscle_head_names" not in sets_df.columns:
        return []

    balance = muscle_head_balance(sets_df)
    if balance.empty:
        return []

    mapper = AnatomyMapper()

    # Find lowest-trained muscle heads that aren't generic
    specific = balance[~balance["muscle_head"].str.contains("generic")]
    specific = specific.sort_values("percentage", ascending=True)
    under = specific.head(n_suggestions * 2)

    suggestions: list[dict[str, Any]] = []
    seen_muscle = set()

    for _, row in under.iterrows():
        head = row["muscle_head"]
        pct = row["percentage"]

        # Group muscle heads (e.g., "triceps_long_head" → "triceps")
        parent_muscle = head.split("_")[0] if "_" in head else head
        if parent_muscle in seen_muscle:
            continue
        seen_muscle.add(parent_muscle)

        # Find exercises in templates that target this head
        all_templates = {}
        for _, t in templates_df.iterrows():
            result = mapper.match(t["title"])
            if result:
                for h in result["heads"]:
                    if h["name"] == head:
                        all_templates.setdefault(t["title"], []).append(h["activation"])

        if not all_templates:
            continue

        # Pick highest activation exercises
        sorted_ex = sorted(
            all_templates.items(),
            key=lambda x: {"very_high": 4, "high": 3, "moderate": 2, "low": 1}.get(x[1][0], 0),
            reverse=True,
        )

        top_exercises = [ex for ex, _ in sorted_ex[:3]]

        suggestions.append({
            "under_targeted": head.replace("_", " ").title(),
            "volume_percentage": round(pct, 1),
            "suggested_exercises": top_exercises,
            "reason": (
                f"Only {pct:.1f}% of volume. Try {', '.join(top_exercises[:2])} "
                f"to specifically target this area."
            ),
        })

        if len(suggestions) >= n_suggestions:
            break

    return suggestions


def _get_current_exercises(
    sets_df: pd.DataFrame,
    routines_df: pd.DataFrame | None,
) -> set[str]:
    """Get set of exercise titles currently being done."""
    exercises = set()

    if routines_df is not None and not routines_df.empty:
        exercises.update(routines_df["exercise_title"].str.lower().unique())

    # Also include recently done exercises
    if not sets_df.empty:
        recent = sets_df.sort_values("start_time", ascending=False)
        exercises.update(recent["exercise_title"].str.lower().unique()[:30])

    return exercises
