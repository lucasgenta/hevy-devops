"""🏆 Personal Records — best sets, best weights, e1RM progression."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from hevy.dashboard.helpers import _COLOR_SEQ, insight
from hevy.analysis import best_set_by_exercise, best_weight_by_exercise, e1rm_progression


def render(
    sets_df: pd.DataFrame,
    **_,
) -> None:
    st.title("🏆 Personal Records")
    st.markdown("Your best performances in the selected period.")

    if sets_df.empty:
        st.warning("No workout data available.")
        return

    tab1, tab2, tab3 = st.tabs(["🏋️ Best Sets (Volume)", "🏋️ Best Weights", "📈 e1RM Progression"])

    with tab1:
        st.subheader("Top Sets by Volume (kg × reps)")
        prs = best_set_by_exercise(sets_df)
        if not prs.empty:
            prs["date"] = pd.to_datetime(prs["start_time"]).dt.date
            display = prs[["exercise_title", "volume_kg", "weight_kg", "reps", "date", "workout_title"]]
            display.columns = ["Exercise", "Volume", "Weight", "Reps", "Date", "Workout"]
            st.dataframe(display, use_container_width=True, hide_index=True)
            insight("Top PR",
                f"Highest volume set: **{display.iloc[0]['Exercise']}** "
                f"at **{display.iloc[0]['Volume']:,.0f} kg** "
                f"({display.iloc[0]['Weight']} kg × {display.iloc[0]['Reps']} reps).", "🏆")
        else:
            st.info("No PR data.")

    with tab2:
        st.subheader("Best Weights Lifted")
        bws = best_weight_by_exercise(sets_df)
        if not bws.empty:
            bws["date"] = pd.to_datetime(bws["start_time"]).dt.date
            display = bws[["exercise_title", "weight_kg", "reps", "date", "workout_title"]]
            display.columns = ["Exercise", "Weight (kg)", "Reps", "Date", "Workout"]
            st.dataframe(display, use_container_width=True, hide_index=True)
            insight("Heaviest Lift",
                f"Your heaviest lift was **{display.iloc[0]['Exercise']}** at **{display.iloc[0]['Weight (kg)']} kg**.", "💪")
        else:
            st.info("No weight data.")

    with tab3:
        st.subheader("Estimated 1RM Progression")
        st.markdown("Uses the Brzycki formula: weight × 36 / (37 − reps)")
        exercises_with_weight = sets_df[sets_df["weight_kg"].notna()]["exercise_title"].unique()
        if len(exercises_with_weight) == 0:
            st.info("No weighted exercises in the selected range.")
            return
        selected = st.selectbox("Select exercise", sorted(exercises_with_weight))
        if selected:
            e1rm = e1rm_progression(sets_df, selected)
            if not e1rm.empty:
                fig = px.line(
                    e1rm, x="date", y="e1rm", markers=True,
                    color_discrete_sequence=[_COLOR_SEQ[5]],
                    labels={"date": "Date", "e1rm": "Estimated 1RM (kg)"},
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
                current = e1rm["e1rm"].iloc[-1]
                best = e1rm["e1rm"].max()
                col1, col2 = st.columns(2)
                col1.metric("Current e1RM", f"{current:.0f} kg")
                col2.metric("All-Time Best e1RM", f"{best:.0f} kg")
                if len(e1rm) > 1:
                    change = ((current - e1rm["e1rm"].iloc[0]) / e1rm["e1rm"].iloc[0]) * 100
                    insight("Progression", f"e1RM has **changed by {change:+.0f}%** over the recorded period.", "📈")
            else:
                st.info("Not enough data (need sets with 1-36 reps and weight)")
