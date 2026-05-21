"""📈 Volume Trends — training volume over time."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from hevy.dashboard.helpers import _COLOR_SEQ, _COLOR_MAP
from hevy.analysis import volume_by_muscle_group, volume_by_exercise, volume_by_muscle_head


def render(
    sets_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    **_,
) -> None:
    st.title("📈 Volume Trends")
    st.markdown("Training volume over time. Use the sidebar filters to narrow down.")

    if sets_df.empty:
        st.warning("No workout data in the selected range.")
        return

    period = st.selectbox("Aggregation period", ["Week", "Month", "Year"], index=1)
    period_map = {"Week": "W", "Month": "M", "Year": "Y"}

    st.subheader(f"Volume by Muscle Group ({period})")
    if not templates_df.empty:
        vol_mg = volume_by_muscle_group(sets_df, templates_df, period=period_map[period])
        if not vol_mg.empty:
            vol_mg["period_str"] = vol_mg["period"].astype(str)
            fig = px.bar(
                vol_mg, x="period_str", y="volume_kg", color="primary_muscle_group",
                color_discrete_sequence=_COLOR_SEQ, barmode="stack",
                labels={"period_str": period, "volume_kg": "Volume (kg)", "primary_muscle_group": "Muscle"},
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

    st.subheader(f"Volume by Exercise ({period})")
    top_n = st.slider("Show top N exercises", 5, 30, 15, key="vol_top_n")
    vol_ex = volume_by_exercise(sets_df, period=period_map[period])
    if not vol_ex.empty:
        top_ex = vol_ex.groupby("exercise_title")["volume_kg"].sum().nlargest(top_n).index
        vol_top = vol_ex[vol_ex["exercise_title"].isin(top_ex)]
        vol_top["period_str"] = vol_top["period"].astype(str)
        fig = px.bar(
            vol_top, x="period_str", y="volume_kg", color="exercise_title",
            color_discrete_sequence=_COLOR_MAP, barmode="stack",
            labels={"period_str": period, "volume_kg": "Volume (kg)", "exercise_title": "Exercise"},
        )
        fig.update_layout(height=500, legend_title_text="Exercise")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Not enough data for exercise breakdown.")

    if "muscle_head_names" in sets_df.columns:
        st.subheader(f"Volume by Specific Muscle Head ({period})")
        vol_mh = volume_by_muscle_head(sets_df, period=period_map[period])
        if not vol_mh.empty:
            top_heads = vol_mh.groupby("muscle_head")["volume_kg"].sum().nlargest(12).index
            vol_mh_top = vol_mh[vol_mh["muscle_head"].isin(top_heads)]
            vol_mh_top["period_str"] = vol_mh_top["period"].astype(str)
            fig = px.bar(
                vol_mh_top, x="period_str", y="volume_kg", color="muscle_head",
                color_discrete_sequence=_COLOR_MAP, barmode="stack",
                labels={"period_str": period, "volume_kg": "Volume (kg)", "muscle_head": "Head"},
            )
            fig.update_layout(height=500, legend_title_text="Muscle Head")
            st.plotly_chart(fig, use_container_width=True)
