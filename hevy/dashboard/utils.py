"""Shared data-loading helpers for the dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from hevy.transform import (
    build_body_measurements_df,
    build_exercise_templates_df,
    build_workout_sets_df,
    build_workout_summary_df,
)
from hevy.anatomy import AnatomyMapper

# Default data path relative to project root
_DEFAULT_RAW = str(Path(__file__).resolve().parents[2] / "data" / "raw")


@st.cache_data(ttl=300)
def load_sets_df(raw_dir: str | None = None, use_muscle_heads: bool = True) -> pd.DataFrame:
    """Load and cache the workout sets DataFrame.

    Cached for 5 minutes — re-scraping will refresh.
    """
    mapper = AnatomyMapper() if use_muscle_heads else None
    return build_workout_sets_df(raw_dir=raw_dir or _DEFAULT_RAW, mapper=mapper)


@st.cache_data(ttl=300)
def load_summary_df(raw_dir: str | None = None) -> pd.DataFrame:
    """Load and cache the workout summary DataFrame."""
    return build_workout_summary_df(raw_dir=raw_dir or _DEFAULT_RAW)


@st.cache_data(ttl=300)
def load_templates_df(raw_dir: str | None = None) -> pd.DataFrame:
    """Load and cache exercise templates."""
    return build_exercise_templates_df(raw_dir=raw_dir or _DEFAULT_RAW)


@st.cache_data(ttl=300)
def load_measurements_df(raw_dir: str | None = None) -> pd.DataFrame:
    """Load and cache body measurements."""
    return build_body_measurements_df(raw_dir=raw_dir or _DEFAULT_RAW)


@st.cache_data(ttl=300)
def load_routines_df(raw_dir: str | None = None) -> pd.DataFrame:
    """Load and cache routines data."""
    from hevy.transform import build_routines_df
    return build_routines_df(raw_dir=raw_dir or _DEFAULT_RAW)


def overview_stats(summary_df: pd.DataFrame, sets_df: pd.DataFrame) -> dict[str, Any]:
    """Compute high-level overview statistics."""
    total_volume = sets_df["volume_kg"].sum() if not sets_df.empty else 0
    stats = {
        "Workouts": len(summary_df),
        "Total Sets": len(sets_df),
        "Total Volume": f"{total_volume:,.0f} kg",
        "Avg Duration": f"{summary_df['duration_min'].mean():.0f} min" if not summary_df.empty else "—",
        "Total Exercises": sets_df["exercise_title"].nunique() if not sets_df.empty else 0,
    }
    return stats
