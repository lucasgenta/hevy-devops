"""Analyze routines for hypertrophy-optimal set volumes across a training week."""

from __future__ import annotations

from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Hypertrophy guidelines (working sets per muscle group per week)
# Synthesised from current exercise science literature (Schoenfeld, Israetel,
# Paulsen, Krieger, etc.) — ranges are for well-trained individuals.
# ---------------------------------------------------------------------------

HYPERTROPHY_GUIDELINES: dict[str, dict[str, int]] = {
    "chest":        {"min": 8,  "optimal_low": 12, "optimal_high": 20, "max": 26},
    "shoulders":    {"min": 8,  "optimal_low": 10, "optimal_high": 18, "max": 24},
    "triceps":      {"min": 6,  "optimal_low": 10, "optimal_high": 18, "max": 22},
    "biceps":       {"min": 6,  "optimal_low": 10, "optimal_high": 18, "max": 22},
    "lats":         {"min": 8,  "optimal_low": 12, "optimal_high": 20, "max": 26},
    "upper_back":   {"min": 8,  "optimal_low": 10, "optimal_high": 18, "max": 22},
    "lower_back":   {"min": 6,  "optimal_low": 8,  "optimal_high": 14, "max": 18},
    "traps":        {"min": 6,  "optimal_low": 8,  "optimal_high": 14, "max": 18},
    "quadriceps":   {"min": 8,  "optimal_low": 10, "optimal_high": 18, "max": 24},
    "hamstrings":   {"min": 6,  "optimal_low": 10, "optimal_high": 16, "max": 20},
    "glutes":       {"min": 6,  "optimal_low": 10, "optimal_high": 16, "max": 20},
    "calves":       {"min": 6,  "optimal_low": 8,  "optimal_high": 16, "max": 20},
    "abdominals":   {"min": 6,  "optimal_low": 8,  "optimal_high": 16, "max": 20},
    "forearms":     {"min": 4,  "optimal_low": 6,  "optimal_high": 12, "max": 16},
    "abductors":    {"min": 4,  "optimal_low": 6,  "optimal_high": 12, "max": 16},
    "adductors":    {"min": 4,  "optimal_low": 6,  "optimal_high": 12, "max": 16},
}

WORKING_TYPES = frozenset({"normal", "failure", "dropset"})
"""Set types that count as working sets toward hypertrophy volume."""

SECONDARY_MULTIPLIER = 0.5
"""Weight given to a set that hits a muscle group secondarily."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_routine_volume(
    routines_df: pd.DataFrame,
    templates_df: pd.DataFrame,
) -> dict[str, Any]:
    """Analyze all routines and return a structured hypertrophy audit.

    Parameters
    ----------
    routines_df:
        DataFrame with columns ``routine_id``, ``routine_title``,
        ``exercise_title``, ``exercise_template_id``, ``set_type``,
        ``set_index``, ``rep_range_start``, ``rep_range_end``.
    templates_df:
        DataFrame with columns ``id``, ``title``, ``primary_muscle_group``,
        ``secondary_muscle_groups``.

    Returns
    -------
    dict with keys:
        - ``per_routine`` — list of per-routine breakdown dicts
        - ``weekly_summary`` — DataFrame with total weekly sets per muscle
        - ``recommendations`` — list of human-readable suggestion strings
    """
    if routines_df.empty:
        return {"per_routine": [], "weekly_summary": pd.DataFrame(), "recommendations": []}

    # Build exercise → muscle mapping from templates
    template_map = _build_template_map(templates_df)

    # Analyse each routine independently
    routine_exercises = _routine_exercise_summary(routines_df, template_map)
    per_routine = _per_routine_breakdown(routines_df, routine_exercises)

    # Aggregate across all routines for weekly totals
    weekly_summary = _weekly_volume_summary(routine_exercises)

    # Generate human-readable suggestions
    recommendations = _build_recommendations(weekly_summary, per_routine)

    return {
        "per_routine": per_routine,
        "weekly_summary": weekly_summary,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_template_map(templates_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Return {exercise_template_id → {primary_muscle, secondary_muscles}}."""
    mapping: dict[str, dict[str, Any]] = {}
    for _, row in templates_df.iterrows():
        secondary = [
            s.strip().lower()
            for s in str(row.get("secondary_muscle_groups", "")).split(",")
            if s.strip()
        ]
        mapping[row["id"]] = {
            "primary": str(row.get("primary_muscle_group", "")).lower(),
            "secondary": secondary,
        }
    return mapping


def _routine_exercise_summary(
    routines_df: pd.DataFrame,
    template_map: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """Return one row per (routine_id, exercise) with working-set count & muscle info.

    Filters out warmup sets. Joins with templates to get muscle groups.
    """
    # Keep only working sets
    working = routines_df[routines_df["set_type"].isin(WORKING_TYPES)].copy()
    if working.empty:
        return pd.DataFrame()

    # Count working sets per exercise per routine
    summary = (
        working.groupby(
            ["routine_id", "routine_title", "exercise_title", "exercise_template_id"],
            as_index=False,
        )
        .agg(
            working_sets=("set_index", "count"),
            rep_range_low=("rep_range_start", "min"),
            rep_range_high=("rep_range_end", "max"),
        )
    )

    # Attach muscle-group info from templates
    def _muscle_info(tid: str) -> dict[str, Any]:
        info = template_map.get(tid, {})
        return pd.Series({
            "primary_muscle": info.get("primary", "unknown"),
            "secondary_muscles": ",".join(info.get("secondary", [])),
        })

    muscle_info = summary["exercise_template_id"].apply(_muscle_info)
    summary = pd.concat([summary, muscle_info], axis=1)

    return summary


def _per_routine_breakdown(
    routines_df: pd.DataFrame,
    exercise_summary: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Build a per-routine breakdown with muscle-group totals and directory."""
    if exercise_summary.empty:
        return []

    routine_names = (
        routines_df[["routine_id", "routine_title"]]
        .drop_duplicates()
        .set_index("routine_id")["routine_title"]
        .to_dict()
    )

    results: list[dict[str, Any]] = []
    for rid in routines_df["routine_id"].unique():
        title = routine_names.get(rid, "Unknown")
        ex_rows = exercise_summary[exercise_summary["routine_id"] == rid]

        exercises = []
        for _, row in ex_rows.iterrows():
            exercises.append({
                "name": row["exercise_title"],
                "working_sets": int(row["working_sets"]),
                "primary_muscle": row["primary_muscle"],
                "secondary_muscles": (
                    [s.strip() for s in row["secondary_muscles"].split(",") if s.strip()]
                    if row["secondary_muscles"]
                    else []
                ),
                "rep_range": (
                    f'{int(row["rep_range_low"])}-{int(row["rep_range_high"])}'
                    if pd.notna(row["rep_range_low"]) and pd.notna(row["rep_range_high"])
                    else "—"
                ),
            })

        # Subtotal sets per muscle group within this routine
        muscle_totals: dict[str, int] = {}
        for ex in exercises:
            m = ex["primary_muscle"]
            muscle_totals[m] = muscle_totals.get(m, 0) + ex["working_sets"]
            for sec in ex["secondary_muscles"]:
                # Count secondary at reduced weight
                muscle_totals[sec] = muscle_totals.get(sec, 0) + round(
                    ex["working_sets"] * SECONDARY_MULTIPLIER
                )

        total_sets = sum(ex["working_sets"] for ex in exercises)
        results.append({
            "routine_id": rid,
            "routine_title": title,
            "exercises": exercises,
            "muscle_totals": dict(sorted(muscle_totals.items())),
            "total_working_sets": total_sets,
            "exercise_count": len(exercises),
        })

    return results


def _weekly_volume_summary(
    exercise_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate working sets across all routines into a weekly muscle-group summary."""
    if exercise_summary.empty:
        return pd.DataFrame()

    # Primary muscle contribution (full set count)
    primary = (
        exercise_summary
        .groupby("primary_muscle", as_index=False)["working_sets"]
        .sum()
        .rename(columns={"primary_muscle": "muscle_group", "working_sets": "direct_sets"})
    )

    # Secondary muscle contribution (half set count per secondary muscle)
    secondary_rows: list[dict[str, Any]] = []
    for _, row in exercise_summary.iterrows():
        secs = (
            [s.strip() for s in row["secondary_muscles"].split(",") if s.strip()]
            if row["secondary_muscles"]
            else []
        )
        for sec in secs:
            secondary_rows.append({
                "muscle_group": sec,
                "half_sets": row["working_sets"] * SECONDARY_MULTIPLIER,
            })

    secondary = pd.DataFrame(secondary_rows)
    if not secondary.empty:
        secondary = (
            secondary.groupby("muscle_group", as_index=False)["half_sets"]
            .sum()
        )

    # Merge primary + secondary
    combined = primary.merge(secondary, on="muscle_group", how="left")
    combined["secondary_sets"] = combined["half_sets"].fillna(0).round(0).astype(int)
    combined["total_effective_sets"] = combined["direct_sets"] + combined["secondary_sets"]

    # Attach guideline zones
    def _zone(muscle: str, total: int) -> dict[str, Any]:
        g = HYPERTROPHY_GUIDELINES.get(muscle, {})
        if not g:
            return {"zone": "unknown", "status": "—", "range": "—"}
        if total < g["min"]:
            return {"zone": "under", "status": "⬆️ Under-trained", "range": f'{g["min"]}-{g["max"]}'}
        if total < g["optimal_low"]:
            return {"zone": "low_optimal", "status": "🔵 Nearly optimal", "range": f'{g["min"]}-{g["max"]}'}
        if total <= g["optimal_high"]:
            return {"zone": "optimal", "status": "✅ Optimal", "range": f'{g["min"]}-{g["max"]}'}
        if total <= g["max"]:
            return {"zone": "high", "status": "🟡 High volume", "range": f'{g["min"]}-{g["max"]}'}
        return {"zone": "over", "status": "🔴 Overtrained", "range": f'{g["min"]}-{g["max"]}'}

    zones = combined["muscle_group"].apply(
        lambda m: pd.Series(_zone(m, combined.loc[combined["muscle_group"] == m, "total_effective_sets"].iloc[0]))
    )
    combined = pd.concat([combined, zones], axis=1)

    return combined.sort_values("total_effective_sets", ascending=False).reset_index(drop=True)


def _build_recommendations(
    weekly_summary: pd.DataFrame,
    per_routine: list[dict[str, Any]],
) -> list[str]:
    """Generate actionable hypertrophy suggestions."""
    recs: list[str] = []

    if weekly_summary.empty:
        return recs

    # Under-trained muscles
    under = weekly_summary[weekly_summary["zone"] == "under"]
    for _, row in under.iterrows():
        needed = row["range"].split("-")[0]
        recs.append(
            f'⬆️ **{row["muscle_group"].title()}** is under-trained '
            f'({row["total_effective_sets"]} sets — aim for at least {needed} sets/week). '
            f"Consider adding an exercise targeting this muscle group."
        )

    # Over-trained muscles
    over = weekly_summary[weekly_summary["zone"] == "over"]
    for _, row in over.iterrows():
        recs.append(
            f'🔴 **{row["muscle_group"].title()}** may be over-trained '
            f'({row["total_effective_sets"]} sets). '
            f"Consider reducing volume or increasing recovery between sessions."
    )

    # High but not over
    high = weekly_summary[weekly_summary["zone"] == "high"]
    for _, row in high.iterrows():
        recs.append(
            f'🟡 **{row["muscle_group"].title()}** is on the higher side '
            f'({row["total_effective_sets"]} sets). Monitor for signs of fatigue.'
        )

    # Frequency check — how many routines hit each muscle
    muscle_freq: dict[str, list[str]] = {}
    for routine in per_routine:
        for muscle in routine["muscle_totals"]:
            if muscle not in muscle_freq:
                muscle_freq[muscle] = []
            muscle_freq[muscle].append(routine["routine_title"])

    for muscle, routines_hitting in muscle_freq.items():
        if len(routines_hitting) > 3 and muscle not in {"forearms", "traps", "calves"}:
            recs.append(
                f'⚠️ **{muscle.title()}** is worked in {len(routines_hitting)} different routines '
                f'({", ".join(routines_hitting)}). '
                "This high frequency may impede recovery — consider consolidating volume."
            )
        elif len(routines_hitting) == 1:
            g = HYPERTROPHY_GUIDELINES.get(muscle)
            if g and g["optimal_low"] > 8:
                recs.append(
                    f'💡 **{muscle.title()}** is only hit in 1 routine. '
                    "Studies suggest 2×/week frequency is superior for hypertrophy — "
                    "consider spreading volume across two sessions."
                )

    if not recs:
        recs.append("✅ Your routine looks well-balanced. No major issues detected.")

    return recs
