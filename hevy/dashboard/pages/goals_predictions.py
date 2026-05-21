"""🎯 Goals & Predictions — track goals, get next-session targets, check fatigue."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from hevy.dashboard.helpers import _COLOR_SEQ
from hevy.goals import GoalTracker
from hevy.predictor import suggest_all_exercises
from hevy.deload import deload_score
from hevy.swaps import suggest_swaps, suggest_head_swaps
from hevy.analysis import e1rm_progression


def render(
    sets_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    routines_df_raw: pd.DataFrame,
    **_,
) -> None:
    st.title("🎯 Goals & Predictions")
    st.markdown("Track goals, get next-session targets, and check fatigue.")

    if sets_df.empty:
        st.warning("No workout data available.")
        return

    tab1, tab2, tab3, tab4 = st.tabs([
        "🎯 Goal Tracker", "🏋️ Next Session Targets",
        "⚠️ Fatigue & Deload", "🔄 Exercise Swaps",
    ])

    goals_path = Path(__file__).resolve().parents[2] / "goals.json"

    # ---- Tab 1: Goal Tracker ----
    with tab1:
        st.subheader("Your Training Goals")
        tracker = GoalTracker(sets_df, goals_path=goals_path)
        goals_df = tracker.to_dataframe()

        with st.expander("➕ Add New Goal", expanded=False):
            col1, col2, col3 = st.columns(3)
            with col1:
                ex_options = sorted(sets_df["exercise_title"].unique())
                new_ex = st.selectbox("Exercise", ex_options, key="goal_ex")
            with col2:
                new_weight = st.number_input("Target weight (kg)", min_value=1.0, value=100.0, step=2.5, key="goal_w")
            with col3:
                new_reps = st.number_input("Reps", min_value=1, value=1, key="goal_r")
            new_date = st.date_input("Target date (optional)", value=None, key="goal_date")
            new_notes = st.text_input("Notes (optional)", key="goal_notes")
            if st.button("Add Goal", type="primary"):
                tracker.add_goal(exercise=new_ex, target_weight_kg=new_weight, reps=new_reps,
                                 target_date=new_date.isoformat() if new_date else None, notes=new_notes)
                tracker.save()
                st.success(f"Goal added: {new_ex} → {new_weight}kg × {new_reps}")
                st.rerun()

        if not goals_df.empty:
            for _, goal in goals_df.iterrows():
                with st.container():
                    cols = st.columns([4, 2, 2, 2, 1])
                    with cols[0]:
                        status = "✅" if goal["on_track"] else "⚠️"
                        st.markdown(f"**{status} {goal['exercise']}**")
                    with cols[1]:
                        st.metric("Current e1RM", f'{goal["current_e1rm"]:.0f} kg' if goal["current_e1rm"] else "—")
                    with cols[2]:
                        st.metric("Target", f'{goal["target_weight_kg"]}kg × {goal["target_reps"]}')
                    with cols[3]:
                        proj = goal.get("projected_date") or "—"
                        st.caption(f"Projected: {proj}")
                    with cols[4]:
                        if st.button("🗑️", key=f'del_goal_{goal["exercise"]}', help="Remove goal"):
                            tracker.remove_goal(goal["exercise"])
                            tracker.save()
                            st.rerun()
                    st.markdown("---")

            for _, goal in goals_df.iterrows():
                with st.expander(f"📈 {goal['exercise']} Progression"):
                    prog = e1rm_progression(sets_df, goal["exercise"])
                    if not prog.empty:
                        fig = px.line(
                            prog, x="date", y="e1rm", markers=True,
                            color_discrete_sequence=[_COLOR_SEQ[5]],
                            labels={"date": "Date", "e1rm": "e1RM (kg)"},
                        )
                        fig.add_hline(y=goal["target_weight_kg"], line_dash="dash", line_color="red",
                                      annotation_text=f'Target: {goal["target_weight_kg"]}kg')
                        fig.update_layout(height=300)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.caption("Not enough data.")
        else:
            st.info("No goals yet. Add one above!")

    # ---- Tab 2: Next Session Targets ----
    with tab2:
        st.subheader("Progressive Overload Predictions")
        predictions = suggest_all_exercises(sets_df, routines_df_raw, min_sets=2)
        if predictions:
            for p in predictions:
                icon = "🟢" if p["confidence"] == "high" else "🟡" if p["confidence"] == "medium" else "⚪"
                suggested = f'{p["suggested_weight_kg"]}kg × {p["suggested_reps"]}' if p["suggested_weight_kg"] else "—"
                last = f'{p["last_weight_kg"]}kg × {p["last_reps"]}' if p["last_weight_kg"] else "—"
                with st.container():
                    cols = st.columns([3, 2, 2, 4])
                    with cols[0]:
                        st.markdown(f"{icon} **{p['exercise']}**")
                    with cols[1]:
                        st.markdown(f"**→ {suggested}**")
                    with cols[2]:
                        st.caption(f"Last: {last}")
                    with cols[3]:
                        st.caption(p["reasoning"])
                st.markdown("---")
        else:
            st.info("Not enough data for predictions.")

    # ---- Tab 3: Fatigue & Deload ----
    with tab3:
        st.subheader("Fatigue & Deload Detection")
        result = deload_score(summary_df, sets_df)
        score = result["score"]
        if result["needs_deload"]:
            st.error(result["recommendation"])
        elif score >= 30:
            st.warning(result["recommendation"])
        else:
            st.success(result["recommendation"])

        col1, col2 = st.columns([1, 2])
        with col1:
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=score,
                domain={"x": [0, 1], "y": [0, 1]},
                title={"text": "Fatigue Score"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "#e74c3c" if score >= 50 else "#f39c12" if score >= 30 else "#2ecc71"},
                    "steps": [
                        {"range": [0, 30], "color": "#d5f5e3"},
                        {"range": [30, 50], "color": "#fdebd0"},
                        {"range": [50, 100], "color": "#fadbd8"},
                    ],
                    "threshold": {"line": {"color": "red", "width": 4}, "thickness": 0.75, "value": score},
                },
            ))
            fig.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            st.subheader("Factors")
            for factor in result["factors"]:
                sev_icon = {"high": "🔴", "medium": "🟡", "low": "🔵", "none": "⚪"}
                st.markdown(f"{sev_icon.get(factor['severity'], '⚪')} {factor['detail']}")
            if result["weeks_since_deload"] is not None:
                st.caption(f"⏱️ {result['weeks_since_deload']} weeks since last deload week")

    # ---- Tab 4: Exercise Swaps ----
    with tab4:
        st.subheader("Exercise Swap Suggestions")
        if not sets_df.empty and not templates_df.empty:
            swaps = suggest_swaps(sets_df, templates_df, routines_df_raw, n_suggestions=5)
            if swaps:
                for sw in swaps:
                    with st.container():
                        st.markdown(f"### 🔸 {sw['under_targeted'].title()}")
                        st.markdown(f"*Currently {sw['volume_percentage']}% of total volume*")
                        for ex in sw["suggested_exercises"]:
                            st.markdown(f"- **{ex}**")
                        if sw.get("head_info"):
                            for hi in sw["head_info"]:
                                st.caption(f"  {hi}")
                        st.markdown("---")
            else:
                st.info("No swap suggestions — your muscle balance looks good!")

            if "muscle_head_names" in sets_df.columns:
                with st.expander("🔬 Specific Muscle Head Suggestions"):
                    head_swaps = suggest_head_swaps(sets_df, templates_df, n_suggestions=5)
                    if head_swaps:
                        for sw in head_swaps:
                            st.markdown(f"**{sw['under_targeted']}** ({sw['volume_percentage']}%):")
                            for ex in sw["suggested_exercises"]:
                                st.markdown(f"- {ex}")
                            st.markdown("---")
                    else:
                        st.info("No specific head suggestions.")
        else:
            st.info("Load workout and template data to get suggestions.")
