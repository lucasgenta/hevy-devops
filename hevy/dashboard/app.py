"""Hevy Training Dashboard — multi-page Streamlit app."""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from hevy.env import load_dotenv  # noqa: E402
load_dotenv()

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from hevy.dashboard.utils import (  # noqa: E402
    load_sets_df, load_summary_df, load_templates_df,
    load_measurements_df, load_routines_df,
)
from hevy.dashboard.pages import (  # noqa: E402
    overview,
    volume_trends,
    muscle_analysis,
    personal_records,
    body_measurements,
    goals_predictions,
    ai_coach,
    raw_explorer,
    routine_analyzer,
)
from nutrition.dashboard import meal_log, nutrition_overview, ai_nutritionist_page  # noqa: E402

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Hevy Training Dashboard",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Load all data
# ---------------------------------------------------------------------------

with st.spinner("Loading your training data..."):
    sets_df_raw = load_sets_df()
    summary_df_raw = load_summary_df()
    templates_df = load_templates_df()
    measurements_df = load_measurements_df()
    routines_df_raw = load_routines_df()

# ---------------------------------------------------------------------------
# Determine global date range
# ---------------------------------------------------------------------------

if not summary_df_raw.empty:
    global_min_date = pd.to_datetime(summary_df_raw["start_time"]).min()
    global_max_date = pd.to_datetime(summary_df_raw["start_time"]).max()
else:
    global_min_date = pd.Timestamp.now() - pd.DateOffset(years=1)
    global_max_date = pd.Timestamp.now()

# ---------------------------------------------------------------------------
# Sidebar — date range filter
# ---------------------------------------------------------------------------

st.sidebar.title("💪 Hevy Dashboard")
st.sidebar.markdown("Your personal training analytics.")
st.sidebar.markdown("### 📅 Date Range")

today = pd.Timestamp.now(tz="UTC")

def _preset_dates(preset: str):
    if preset == "Last 7 days":
        return (today - pd.DateOffset(days=7)).date(), today.date()
    if preset == "Last 30 days":
        return (today - pd.DateOffset(days=30)).date(), today.date()
    if preset == "Last 3 months":
        return (today - pd.DateOffset(months=3)).date(), today.date()
    if preset == "Last 6 months":
        return (today - pd.DateOffset(months=6)).date(), today.date()
    if preset == "Year to date":
        return pd.Timestamp(year=today.year, month=1, day=1, tz="UTC").date(), today.date()
    if preset == "All time":
        return global_min_date.date(), global_max_date.date()
    return global_min_date.date(), global_max_date.date()

if "date_preset" not in st.session_state:
    st.session_state.date_preset = "All time"

preset_options = ["Custom", "Last 7 days", "Last 30 days", "Last 3 months",
                  "Last 6 months", "Year to date", "All time"]
st.sidebar.selectbox(
    "Quick select", preset_options,
    index=preset_options.index(st.session_state.date_preset),
    key="date_preset",
)

if st.session_state.date_preset != "Custom":
    p_start, p_end = _preset_dates(st.session_state.date_preset)
    if st.sidebar.button(f"📅 Apply: {st.session_state.date_preset}", use_container_width=True):
        st.session_state["global_date_range"] = (p_start, p_end)
        st.rerun()
    date_range = st.session_state.get("global_date_range", (p_start, p_end))
else:
    _saved_range = st.session_state.get("global_date_range", (global_min_date.date(), global_max_date.date()))
    if isinstance(_saved_range, (tuple, list)) and len(_saved_range) == 2:
        default_start, default_end = _saved_range
    else:
        default_start, default_end = global_min_date.date(), global_max_date.date()
    date_range = st.sidebar.date_input(
        "Custom range",
        value=default_start if default_start == default_end else (default_start, default_end),
        min_value=global_min_date.date(), max_value=global_max_date.date(),
        key="global_date_range",
    )
    if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
        date_range = (global_min_date.date(), global_max_date.date())

# Normalise
filter_start = pd.Timestamp(date_range[0], tz="UTC")
filter_end = pd.Timestamp(date_range[1], tz="UTC") + pd.DateOffset(days=1)

if not summary_df_raw.empty:
    summary_df = summary_df_raw[
        (pd.to_datetime(summary_df_raw["start_time"]) >= filter_start)
        & (pd.to_datetime(summary_df_raw["start_time"]) < filter_end)
    ].copy()
else:
    summary_df = summary_df_raw.copy()

if not sets_df_raw.empty:
    sets_df = sets_df_raw[
        (pd.to_datetime(sets_df_raw["start_time"]) >= filter_start)
        & (pd.to_datetime(sets_df_raw["start_time"]) < filter_end)
    ].copy()
else:
    sets_df = sets_df_raw.copy()

st.sidebar.caption(f"Showing {len(summary_df)} workouts, {len(sets_df)} sets")

# --- Exercise filter ---
if not sets_df.empty:
    all_exercises = sorted(sets_df["exercise_title"].unique())
    selected_exercises = st.sidebar.multiselect(
        "🏋️ Filter exercises", options=all_exercises, default=[], placeholder="All exercises",
    )
    if selected_exercises:
        sets_df = sets_df[sets_df["exercise_title"].isin(selected_exercises)].copy()

# --- Muscle group filter ---
if not sets_df.empty and not templates_df.empty:
    merged = sets_df.merge(
        templates_df[["id", "primary_muscle_group"]],
        left_on="exercise_template_id", right_on="id",
        how="left", suffixes=("", "_template"),
    )
    all_groups = sorted(merged["primary_muscle_group"].dropna().unique())
    selected_groups = st.sidebar.multiselect(
        "🦵 Filter muscle groups", options=all_groups, default=[], placeholder="All groups",
    )
    if selected_groups:
        filtered_ids = templates_df[templates_df["primary_muscle_group"].isin(selected_groups)]["id"].unique()
        sets_df = sets_df[sets_df["exercise_template_id"].isin(filtered_ids)].copy()

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigation",
    [
        "📊 Overview",
        "📈 Volume Trends",
        "🦵 Muscle Analysis",
        "🏆 Personal Records",
        "📏 Body Measurements",
        "🎯 Goals & Predictions",
        "🤖 AI Coach",
        "📋 Raw Data Explorer",
        "📋 Routine Analyzer",
        "🍽️ Meal Log",
        "📊 Nutrition Overview",
        "🤖 AI Nutritionist",
    ],
)

st.sidebar.markdown("---")
st.sidebar.caption(f"Data range: {global_min_date.date()} → {global_max_date.date()}")

# ---------------------------------------------------------------------------
# Shared page data
# ---------------------------------------------------------------------------

_page_kwargs = dict(
    sets_df=sets_df,
    summary_df=summary_df,
    templates_df=templates_df,
    measurements_df=measurements_df,
    routines_df_raw=routines_df_raw,
)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

PAGES = {
    "📊 Overview": overview.render,
    "📈 Volume Trends": volume_trends.render,
    "🦵 Muscle Analysis": muscle_analysis.render,
    "🏆 Personal Records": personal_records.render,
    "📏 Body Measurements": body_measurements.render,
    "🎯 Goals & Predictions": goals_predictions.render,
    "🤖 AI Coach": ai_coach.render,
    "📋 Raw Data Explorer": raw_explorer.render,
    "📋 Routine Analyzer": routine_analyzer.render,
    "🍽️ Meal Log": meal_log,
    "📊 Nutrition Overview": nutrition_overview,
    "🤖 AI Nutritionist": ai_nutritionist_page,
}

if page in PAGES:
    PAGES[page](**_page_kwargs)
