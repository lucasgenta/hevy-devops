"""📏 Body Measurements — track body composition over time."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from hevy.dashboard.helpers import _COLOR_SEQ

METRIC_COLS = [
    "weight_kg", "lean_mass_kg", "fat_percent",
    "chest_cm", "waist_cm", "hips_cm",
    "left_bicep_cm", "right_bicep_cm",
    "left_thigh_cm", "right_thigh_cm",
    "shoulder_cm", "neck_cm",
]


def render(measurements_df: pd.DataFrame, **_) -> None:
    st.title("📏 Body Measurements")
    st.markdown("Track your body composition over time.")

    if measurements_df.empty:
        st.warning("No body measurement data. Scrape the body_measurements endpoint first.")
        return

    selected_metrics = st.multiselect(
        "Select measurements to display", METRIC_COLS,
        default=["weight_kg", "fat_percent", "chest_cm", "waist_cm"],
    )

    if selected_metrics:
        fig = go.Figure()
        for i, metric in enumerate(selected_metrics):
            valid = measurements_df.dropna(subset=[metric])
            if not valid.empty:
                fig.add_trace(go.Scatter(
                    x=valid["date"], y=valid[metric],
                    mode="lines+markers", name=metric.replace("_", " ").title(),
                    line=dict(color=_COLOR_SEQ[i % len(_COLOR_SEQ)], width=2),
                ))
        fig.update_layout(height=450, xaxis_title="Date", yaxis_title="Value", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Changes Over Full Recorded Period")
    latest = measurements_df.sort_values("date", ascending=False).iloc[0]
    first = measurements_df.sort_values("date").iloc[0]
    deltas = {}
    for metric in selected_metrics:
        if metric in latest and metric in first:
            lv, fv = latest[metric], first[metric]
            if pd.notna(lv) and pd.notna(fv):
                deltas[metric.replace("_", " ").title()] = lv - fv
    if deltas:
        cols = st.columns(len(deltas))
        for col, (label, delta) in zip(cols, deltas.items()):
            col.metric(label=label, value=f"{delta:+.1f}")
    else:
        st.info("Select metrics above to see changes.")

    with st.expander("View raw data"):
        display_cols = ["date"] + [c for c in METRIC_COLS if c in measurements_df.columns]
        st.dataframe(
            measurements_df[display_cols].sort_values("date", ascending=False).reset_index(drop=True),
            use_container_width=True, hide_index=True,
        )
