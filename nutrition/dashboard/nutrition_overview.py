"""Nutrition Overview page — trends, weekly averages, macro balance."""

from __future__ import annotations

from datetime import date, timedelta

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from nutrition.analysis import (
    macro_percentages,
    period_totals,
    weekly_averages,
)
from nutrition.storage import NutritionStorage

_COLOR_SEQ = px.colors.qualitative.Vivid


def render(storage: NutritionStorage) -> None:
    """Render the Nutrition Overview trends page."""
    st.title("📊 Nutrition Overview")
    st.markdown("Your calorie and macro trends over time.")

    # ---- Date range ----
    today = date.today()
    default_start = today - timedelta(days=30)

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("From", value=default_start, key="nutri_start")
    with col2:
        end_date = st.date_input("To", value=today, key="nutri_end")

    # Load data
    entries_by_day = storage.load_range(start_date.isoformat(), end_date.isoformat())

    if not entries_by_day:
        st.warning("No meal data in this date range. Log some meals first!")
        return

    # Convert to DataFrame
    df = period_totals(entries_by_day)

    # ---- Top-level summary ----
    total_days = len(df)
    avg_calories = df["energy_kcal"].mean()
    avg_protein = df["protein_g"].mean()
    avg_carbs = df["carbs_g"].mean()
    avg_fat = df["fat_g"].mean()

    cols = st.columns(4)
    cols[0].metric("Days Logged", str(total_days))
    cols[1].metric("Avg Calories", f"{avg_calories:.0f} kcal")
    cols[2].metric("Avg Protein", f"{avg_protein:.1f}g")
    cols[3].metric("Avg Carbs / Fat", f"{avg_carbs:.0f}g / {avg_fat:.0f}g")

    st.markdown("---")

    # ---- Calorie trend chart ----
    st.subheader("🔥 Daily Calorie Intake")
    fig = px.bar(
        df,
        x="date",
        y="energy_kcal",
        color_discrete_sequence=[_COLOR_SEQ[0]],
        labels={"date": "Date", "energy_kcal": "Calories (kcal)"},
    )
    # Add average line
    mean_cal = df["energy_kcal"].mean()
    fig.add_hline(
        y=mean_cal,
        line_dash="dash",
        line_color="green",
        annotation_text=f"Avg: {mean_cal:.0f} kcal",
    )
    fig.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    # ---- Macro breakdown ----
    st.markdown("---")
    st.subheader("🥩🍚🧈 Macro Trends")

    col1, col2 = st.columns(2)

    with col1:
        # Stacked bar: protein, carbs, fat per day (in grams)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Protein",
            x=df["date"],
            y=df["protein_g"],
            marker_color="#e74c3c",
        ))
        fig.add_trace(go.Bar(
            name="Carbs",
            x=df["date"],
            y=df["carbs_g"],
            marker_color="#f39c12",
        ))
        fig.add_trace(go.Bar(
            name="Fat",
            x=df["date"],
            y=df["fat_g"],
            marker_color="#3498db",
        ))
        fig.update_layout(
            barmode="group",
            height=350,
            xaxis_title="Date",
            yaxis_title="Grams",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Macro split as percentage (averaged over period)
        # Aggregate all entries
        all_entries = []
        for day_entries in entries_by_day.values():
            all_entries.extend(day_entries)
        macros = macro_percentages(all_entries)

        fig = go.Figure(data=[go.Pie(
            labels=["Protein", "Carbs", "Fat"],
            values=[macros["protein_pct"], macros["carbs_pct"], macros["fat_pct"]],
            marker=dict(colors=["#e74c3c", "#f39c12", "#3498db"]),
            hole=0.4,
            textinfo="label+percent",
        )])
        fig.update_layout(
            height=350,
            title="Macro Split (% of calories)",
        )
        st.plotly_chart(fig, use_container_width=True)

    # ---- Weekly averages ----
    st.markdown("---")
    st.subheader("📈 Weekly Averages")
    weekly = weekly_averages(df)
    if not weekly.empty and len(weekly) > 1:
        fig = px.line(
            weekly,
            x="label",
            y=["energy_kcal", "protein_g", "carbs_g", "fat_g"],
            markers=True,
            labels={"label": "Week", "value": "Amount", "variable": "Metric"},
            color_discrete_map={
                "energy_kcal": _COLOR_SEQ[0],
                "protein_g": "#e74c3c",
                "carbs_g": "#f39c12",
                "fat_g": "#3498db",
            },
        )
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Need at least 2 weeks of data for weekly trends.")

    # ---- Fiber & quality metrics ----
    st.markdown("---")
    st.subheader("🌾 Fiber & Quality")
    if "fiber_g" in df.columns:
        fig = px.area(
            df,
            x="date",
            y="fiber_g",
            color_discrete_sequence=[_COLOR_SEQ[3]],
            labels={"date": "Date", "fiber_g": "Fiber (g)"},
        )
        fig.update_layout(height=250, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        avg_fiber = df["fiber_g"].mean()
        target = 30  # general recommended daily fiber
        st.markdown(
            f"**Average fiber**: {avg_fiber:.1f}g/day "
            f"{'✅' if avg_fiber >= 25 else '⚠️'} "
            f"(recommended: {target}g)"
        )

    # ---- Raw data table ----
    with st.expander("📋 View Raw Data"):
        import pandas as pd
        display = df.copy()
        display["date"] = pd.to_datetime(display["date"]).dt.strftime("%b %d")
        display["kcal"] = display["energy_kcal"].round(0).astype(int)
        display["P"] = display["protein_g"].round(1)
        display["C"] = display["carbs_g"].round(1)
        display["F"] = display["fat_g"].round(1)
        st.dataframe(
            display[["date", "kcal", "P", "C", "F", "meal_count"]].rename(columns={
                "date": "Date", "kcal": "Calories", "P": "Protein (g)",
                "C": "Carbs (g)", "F": "Fat (g)", "meal_count": "Meals",
            }),
            use_container_width=True,
            hide_index=True,
        )
