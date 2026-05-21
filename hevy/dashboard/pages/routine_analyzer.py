"""📋 Routine Analyzer — check hypertrophy set volumes across your routines."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from hevy.routine_analyzer import analyze_routine_volume


def render(
    routines_df_raw: pd.DataFrame,
    templates_df: pd.DataFrame,
    **_,
) -> None:
    st.title("📋 Routine Analyzer")
    st.markdown(
        "Checks your routines against hypertrophy volume guidelines to help you "
        "spot imbalances and optimise your training split."
    )

    if routines_df_raw.empty:
        st.warning("No routine data available. Run the scraper first.")
        return

    # Routine selector (exclude archived ones)
    all_titles = sorted(routines_df_raw["routine_title"].unique())
    defaults = [t for t in all_titles if not t.startswith("ZZZ")]
    selected = st.multiselect(
        "Select routines to analyze",
        options=all_titles,
        default=defaults if defaults else all_titles,
        help="Uncheck archived/old routines to focus on your current split.",
    )

    if not selected:
        st.info("Select at least one routine above.")
        return

    filtered = routines_df_raw[routines_df_raw["routine_title"].isin(selected)].copy()

    with st.spinner("Analyzing your routines..."):
        analysis = analyze_routine_volume(filtered, templates_df)

    if not analysis["per_routine"]:
        st.info("No working sets found in your routines.")
        return

    # Overview metrics
    total_exercises = sum(r["exercise_count"] for r in analysis["per_routine"])
    total_weekly_sets = sum(r["total_working_sets"] for r in analysis["per_routine"])
    col1, col2, col3 = st.columns(3)
    col1.metric("Routines", len(analysis["per_routine"]))
    col2.metric("Exercises", total_exercises)
    col3.metric("Weekly Working Sets", total_weekly_sets)
    st.markdown("---")

    # Weekly Hypertrophy Scorecard
    st.subheader("📊 Weekly Hypertrophy Scorecard")
    st.markdown(
        "Estimated total working sets per muscle group across all selected routines. "
        "Secondary muscle activation (e.g. triceps in pressing) is counted at ½ weight."
    )

    weekly = analysis["weekly_summary"]
    zone_colors = {
        "under": "#e74c3c", "low_optimal": "#f39c12", "optimal": "#2ecc71",
        "high": "#f1c40f", "over": "#e74c3c", "unknown": "#95a5a6",
    }

    if not weekly.empty:
        fig = px.bar(
            weekly, x="muscle_group", y="total_effective_sets",
            color="zone", color_discrete_map=zone_colors, text="total_effective_sets",
            labels={"muscle_group": "", "total_effective_sets": "Sets / Week"},
            category_orders={"muscle_group": sorted(weekly["muscle_group"].unique())},
        )
        fig.update_traces(textposition="outside", textfont_size=11)
        fig.update_layout(height=400, showlegend=True, legend_title="Status",
                          xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

        display_cols = {
            "muscle_group": "Muscle", "direct_sets": "Direct",
            "secondary_sets": "Secondary", "total_effective_sets": "Total Weekly",
            "status": "Verdict", "range": "Target Weekly Sets",
        }
        display_df = weekly[list(display_cols)].rename(columns=display_cols)

        def _style(row):
            zone = weekly.loc[row.name, "zone"]
            bg = zone_colors.get(zone, "#95a5a6")
            return [f"background-color: {bg}22"] * len(row)

        st.dataframe(display_df.style.apply(_style, axis=1), use_container_width=True, hide_index=True)
    else:
        st.info("Could not compute volume summary.")

    st.markdown("---")

    # Insights
    st.subheader("💡 Insights")
    for rec in analysis["recommendations"]:
        st.markdown(f"- {rec}")

    st.markdown("---")

    # Per-routine detail
    st.subheader("📋 Per-Routine Breakdown")
    for routine in analysis["per_routine"]:
        with st.expander(
            f"**{routine['routine_title']}** — {routine['exercise_count']} exercises, "
            f"{routine['total_working_sets']} working sets"
        ):
            cols = st.columns(len(routine["muscle_totals"]))
            for col, (muscle, sets) in zip(cols, routine["muscle_totals"].items()):
                col.metric(muscle.title(), f"{sets} sets")

            ex_df = pd.DataFrame(routine["exercises"])
            st.dataframe(
                ex_df.rename(columns={
                    "name": "Exercise", "working_sets": "Working Sets",
                    "primary_muscle": "Primary", "rep_range": "Rep Range",
                })[["Exercise", "Working Sets", "Primary", "Rep Range"]],
                use_container_width=True, hide_index=True,
            )
