"""Compute training metrics, volume trends, PRs, and muscle balance analysis."""

from __future__ import annotations

from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Volume analysis
# ---------------------------------------------------------------------------


def _to_period(series: pd.Series, period: str) -> pd.Series:
    """Convert datetime series to period, handling timezone-aware values."""
    dt = pd.to_datetime(series)
    if dt.dt.tz is not None:
        dt = dt.dt.tz_localize(None)
    return dt.dt.to_period(period)


def volume_by_exercise(
    sets_df: pd.DataFrame,
    period: str = "M",
) -> pd.DataFrame:
    """Total volume (kg) per exercise, grouped by time period.

    *period* — pandas offset alias: 'W' (week), 'M' (month), 'Y' (year).
    """
    df = sets_df.copy()
    df["period"] = _to_period(df["start_time"], period)
    return (
        df.groupby(["period", "exercise_title"])["volume_kg"]
        .sum()
        .reset_index()
        .sort_values(["period", "volume_kg"], ascending=[True, False])
    )


def volume_by_muscle_group(
    sets_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    period: str = "M",
) -> pd.DataFrame:
    """Total volume per Hevy muscle group over time."""
    merged = _merge_muscle_groups(sets_df, templates_df)
    merged["period"] = _to_period(merged["start_time"], period)
    return (
        merged.groupby(["period", "primary_muscle_group"])["volume_kg"]
        .sum()
        .reset_index()
        .sort_values(["period", "volume_kg"], ascending=[True, False])
    )


def volume_by_muscle_head(
    sets_df: pd.DataFrame,
    period: str = "M",
) -> pd.DataFrame:
    """Total volume per specific muscle head over time.

    Requires sets_df to have 'muscle_head_names' column (from transform).
    """
    if "muscle_head_names" not in sets_df.columns:
        raise ValueError(
            "sets_df must have 'muscle_head_names' column. "
            "Pass an AnatomyMapper to build_workout_sets_df()."
        )

    # Explode the muscle_heads list — one row per muscle head per set
    rows: list[dict[str, Any]] = []
    for _, row in sets_df.iterrows():
        heads = row.get("muscle_head_names", [])
        vol = row.get("volume_kg", 0)
        ts = pd.Timestamp(row["start_time"])
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        period_val = ts.to_period(period)
        for head in heads:
            rows.append({"period": period_val, "muscle_head": head, "volume_kg": vol})

    exploded = pd.DataFrame(rows)
    if exploded.empty:
        return pd.DataFrame()

    return (
        exploded.groupby(["period", "muscle_head"])["volume_kg"]
        .sum()
        .reset_index()
        .sort_values(["period", "volume_kg"], ascending=[True, False])
    )


# ---------------------------------------------------------------------------
# Personal Records
# ---------------------------------------------------------------------------


def best_set_by_exercise(sets_df: pd.DataFrame) -> pd.DataFrame:
    """Best set (highest volume) ever for each exercise.

    Returns one row per exercise with the max volume, weight, and reps.
    """
    if sets_df.empty:
        return pd.DataFrame()

    # Find the index of the max volume per exercise
    idx = sets_df.groupby("exercise_title")["volume_kg"].idxmax()
    top_sets = sets_df.loc[idx, [
        "exercise_title",
        "volume_kg",
        "weight_kg",
        "reps",
        "start_time",
        "workout_title",
    ]].reset_index(drop=True)

    return top_sets.sort_values("volume_kg", ascending=False).reset_index(drop=True)


def best_weight_by_exercise(sets_df: pd.DataFrame) -> pd.DataFrame:
    """Highest weight ever lifted for each exercise."""
    if sets_df.empty:
        return pd.DataFrame()

    # Drop groups where all weight_kg values are NaN
    valid = sets_df.dropna(subset=["weight_kg"])
    if valid.empty:
        return pd.DataFrame()

    idx = valid.groupby("exercise_title")["weight_kg"].idxmax()
    return valid.loc[idx, [
        "exercise_title", "weight_kg", "reps", "start_time", "workout_title",
    ]].sort_values("weight_kg", ascending=False).reset_index(drop=True)


def e1rm_progression(
    sets_df: pd.DataFrame,
    exercise_title: str,
) -> pd.DataFrame:
    """Estimated 1RM progression for a specific exercise over time.

    Uses the Brzycki formula: weight × (36 / (37 - reps))

    Filters to sets with reps between 1 and 36.
    """
    df = sets_df[
        (sets_df["exercise_title"].str.lower() == exercise_title.lower())
        & (sets_df["reps"].between(1, 36, inclusive="both"))
        & (sets_df["weight_kg"] > 0)
    ].copy()

    if df.empty:
        return pd.DataFrame()

    df["e1rm"] = df.apply(
        lambda r: r["weight_kg"] * (36 / (37 - r["reps"])), axis=1
    )
    df["date"] = pd.to_datetime(df["start_time"]).dt.date
    return (
        df.groupby("date")["e1rm"]
        .max()
        .reset_index()
        .sort_values("date")
    )


# ---------------------------------------------------------------------------
# Muscle balance
# ---------------------------------------------------------------------------


def muscle_group_balance(sets_df: pd.DataFrame, templates_df: pd.DataFrame) -> pd.DataFrame:
    """Volume distribution across muscle groups as percentage of total."""
    merged = _merge_muscle_groups(sets_df, templates_df)
    total_volume = merged["volume_kg"].sum()
    if total_volume == 0:
        return pd.DataFrame()

    by_group = merged.groupby("primary_muscle_group")["volume_kg"].sum().reset_index()
    by_group["percentage"] = (by_group["volume_kg"] / total_volume * 100).round(1)
    return by_group.sort_values("volume_kg", ascending=False).reset_index(drop=True)


def muscle_head_balance(sets_df: pd.DataFrame) -> pd.DataFrame:
    """Volume distribution across specific muscle heads as percentage of total."""
    if "muscle_head_names" not in sets_df.columns:
        raise ValueError(
            "sets_df must have 'muscle_head_names' column. "
            "Pass an AnatomyMapper to build_workout_sets_df()."
        )

    rows: list[dict[str, Any]] = []
    for _, row in sets_df.iterrows():
        heads = row.get("muscle_head_names", [])
        vol = row.get("volume_kg", 0) / max(len(heads), 1)
        for head in heads:
            rows.append({"muscle_head": head, "volume_kg": vol})

    exploded = pd.DataFrame(rows)
    if exploded.empty:
        return pd.DataFrame()

    total_volume = exploded["volume_kg"].sum()
    by_head = exploded.groupby("muscle_head")["volume_kg"].sum().reset_index()
    by_head["percentage"] = (by_head["volume_kg"] / total_volume * 100).round(1)
    return by_head.sort_values("volume_kg", ascending=False).reset_index(drop=True)


def symmetrical_imbalance(
    sets_df: pd.DataFrame,
    templates_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compare left vs right unilateral exercise volume.

    Looks for exercises containing 'left' or 'right' in the title.
    """
    df = sets_df[
        sets_df["exercise_title"].str.contains(
            r"\b(left|right)\b", case=False, na=False
        )
    ].copy()

    if df.empty:
        return pd.DataFrame()

    df["side"] = df["exercise_title"].str.extract(
        r"\b(left|right)\b", expand=False, flags=re.IGNORECASE
    )
    df["side"] = df["side"].str.lower()
    df["base_exercise"] = df["exercise_title"].str.replace(
        r"\s*(Left|Right)\s*", "", regex=True
    ).str.strip()

    return (
        df.groupby(["base_exercise", "side"])["volume_kg"]
        .sum()
        .reset_index()
        .pivot(index="base_exercise", columns="side", values="volume_kg")
        .fillna(0)
        .reset_index()
    )


# ---------------------------------------------------------------------------
# Workout frequency & trends
# ---------------------------------------------------------------------------


def workouts_over_time(summary_df: pd.DataFrame, period: str = "W") -> pd.DataFrame:
    """Number of workouts per time period."""
    df = summary_df.copy()
    df["period"] = _to_period(df["start_time"], period)
    return (
        df.groupby("period").size()
        .reset_index(name="workout_count")
        .sort_values("period")
    )


def weekly_volume_trend(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Total weekly training volume over time."""
    df = summary_df.copy()
    df["week"] = _to_period(df["start_time"], "W")
    return (
        df.groupby("week")["total_volume_kg"]
        .sum()
        .reset_index()
        .sort_values("week")
    )


def muscle_group_diversity_by_workout(
    sets_df: pd.DataFrame,
    templates_df: pd.DataFrame,
) -> pd.DataFrame:
    """How many distinct muscle groups trained per workout session."""
    merged = _merge_muscle_groups(sets_df, templates_df)
    return (
        merged.groupby("workout_id")["primary_muscle_group"]
        .nunique()
        .reset_index(name="muscle_groups_count")
        .sort_values("muscle_groups_count", ascending=False)
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

import re  # noqa: E402 (needed for symmetrical_imbalance)


def _merge_muscle_groups(
    sets_df: pd.DataFrame,
    templates_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join sets with exercise templates to get primary muscle group."""
    if "primary_muscle_group" in sets_df.columns:
        return sets_df

    merged = sets_df.merge(
        templates_df[["id", "primary_muscle_group"]],
        left_on="exercise_template_id",
        right_on="id",
        how="left",
        suffixes=("", "_template"),
    )
    # For exercises missing a template match, use the title to guess
    merged["primary_muscle_group"] = merged["primary_muscle_group"].fillna("unknown")
    return merged
