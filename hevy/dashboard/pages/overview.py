"""📊 Overview — high-level stats and trends."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from hevy.dashboard.helpers import _COLOR_SEQ, insight
from hevy.dashboard.utils import overview_stats
from hevy.analysis import (
    workouts_over_time,
    weekly_volume_trend,
    muscle_group_balance,
)


def render(
    sets_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    **_,
) -> None:
    st.title("📊 Training Overview")
    st.markdown("High-level stats and trends from your Hevy data.")

    stats = overview_stats(summary_df, sets_df)
    cols = st.columns(len(stats))
    for col, (label, value) in zip(cols, stats.items()):
        col.metric(label=label, value=value)

    st.markdown("---")

    if summary_df.empty:
        st.info("No workouts in the selected date range. Adjust the date filter.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Workouts per Week")
        w_freq = workouts_over_time(summary_df, period="W")
        if not w_freq.empty:
            w_freq["period_str"] = w_freq["period"].astype(str)
            fig = px.bar(
                w_freq, x="period_str", y="workout_count",
                color_discrete_sequence=[_COLOR_SEQ[2]],
                labels={"period_str": "Week", "workout_count": "Workouts"},
            )
            fig.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)
            avg = w_freq["workout_count"].mean()
            insight("Frequency", f"You average **{avg:.1f} workouts/week** in this period.", "📅")
        else:
            st.info("Not enough data.")

    with col2:
        st.subheader("Weekly Volume Trend")
        wvt = weekly_volume_trend(summary_df)
        if not wvt.empty:
            wvt["week_str"] = wvt["week"].astype(str)
            fig = px.area(
                wvt, x="week_str", y="total_volume_kg",
                color_discrete_sequence=[_COLOR_SEQ[0]],
                labels={"week_str": "Week", "total_volume_kg": "Volume (kg)"},
            )
            fig.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)
            if len(wvt) > 1:
                trend = wvt["total_volume_kg"]
                change = ((trend.iloc[-1] - trend.iloc[0]) / trend.iloc[0]) * 100
                direction = "increasing 📈" if change > 0 else "decreasing 📉"
                insight("Volume Trend", f"Volume is **{direction}** ({change:+.0f}%) over this period.", "📊")

    st.markdown("---")
    st.subheader("Volume by Muscle Group")
    if not sets_df.empty and not templates_df.empty:
        balance = muscle_group_balance(sets_df, templates_df)
        if not balance.empty:
            col1, col2 = st.columns([1, 1])
            with col1:
                fig = px.pie(
                    balance, names="primary_muscle_group", values="volume_kg",
                    color_discrete_sequence=_COLOR_SEQ, hole=0.4,
                )
                fig.update_layout(height=450)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.subheader("Top Muscle Groups")
                for _, row in balance.head(8).iterrows():
                    st.markdown(f"**{row['primary_muscle_group']}**: {row['percentage']:.1f}% ({row['volume_kg']:,.0f} kg)")
                top = balance.iloc[0]
                low = balance.iloc[-1]
                insight("Balance Check",
                    f"Most trained: **{top['primary_muscle_group']}** ({top['percentage']:.1f}%) — "
                    f"Least: **{low['primary_muscle_group']}** ({low['percentage']:.1f}%).", "⚖️")
        else:
            st.info("Could not compute muscle balance.")
    else:
        st.info("Load workout data to see muscle distribution.")

    st.markdown("---")
    st.subheader("Recent Workouts")
    if not summary_df.empty:
        recent = summary_df.sort_values("start_time", ascending=False).head(10)
        cols_show = ["title", "start_time", "duration_min", "exercise_count", "total_sets", "total_volume_kg"]
        st.dataframe(
            recent[cols_show].rename(columns={
                "title": "Workout", "start_time": "Date",
                "duration_min": "Duration (min)", "exercise_count": "Exercises",
                "total_sets": "Sets", "total_volume_kg": "Volume (kg)",
            }),
            use_container_width=True, hide_index=True,
        )
