"""📋 Raw Data Explorer — browse your scraped data in table form."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from hevy.dashboard.helpers import insight


def render(
    sets_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    measurements_df: pd.DataFrame,
    routines_df_raw: pd.DataFrame,
    **_,
) -> None:
    st.title("📋 Raw Data Explorer")
    st.markdown("Browse your training data in raw table form for debugging or deep dives.")

    dataset = st.selectbox(
        "Choose a dataset",
        ["Workout Summary", "Workout Sets", "Exercise Templates", "Body Measurements", "Routines"],
    )

    limit = st.slider("Rows to show", 10, 500, 50, step=10)

    if dataset == "Workout Summary":
        st.subheader(f"Workout Summary ({len(summary_df)} workouts)")
        st.dataframe(summary_df.sort_values("start_time", ascending=False).head(limit), use_container_width=True)
        insight("Tip", "Click any column header to sort. Use the sidebar date filter to narrow down.", "💡")

    elif dataset == "Workout Sets":
        st.subheader(f"Workout Sets ({len(sets_df)} sets)")
        st.dataframe(sets_df.sort_values("start_time", ascending=False).head(limit), use_container_width=True)
        insight("Tip", "The 'muscle_heads' column shows which specific muscle heads each exercise targets.", "💡")

    elif dataset == "Exercise Templates":
        st.subheader(f"Exercise Templates ({len(templates_df)} exercises)")
        st.dataframe(templates_df.head(limit), use_container_width=True)
        unique_groups = templates_df["primary_muscle_group"].dropna().unique()
        st.caption(f"Muscle groups: {', '.join(sorted(unique_groups))}")

    elif dataset == "Body Measurements":
        st.subheader(f"Body Measurements ({len(measurements_df)} records)")
        st.dataframe(measurements_df.sort_values("date", ascending=False).head(limit), use_container_width=True)

    elif dataset == "Routines":
        st.subheader(f"Routines ({len(routines_df_raw)} rows)")
        st.dataframe(routines_df_raw.head(limit), use_container_width=True)
        unique_routines = routines_df_raw["routine_title"].unique()
        st.caption(f"Routines: {', '.join(unique_routines)}")
