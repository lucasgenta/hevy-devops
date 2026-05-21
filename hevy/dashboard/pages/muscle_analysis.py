"""🦵 Muscle Analysis — balance, symmetry, push/pull/legs split."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from hevy.dashboard.helpers import _COLOR_SEQ, insight
from hevy.analysis import (
    muscle_group_balance,
    muscle_head_balance,
    symmetrical_imbalance,
)


def _generate_head_insights(head_bal: pd.DataFrame) -> str:
    """Generate muscle head insights from balance data."""
    insights = []
    if head_bal.empty:
        return "No muscle head data."

    # Triceps imbalance
    triceps_heads = head_bal[head_bal["muscle_head"].str.contains("triceps", case=False, na=False)]
    if len(triceps_heads) >= 2:
        long = triceps_heads[triceps_heads["muscle_head"].str.contains("long", case=False)]
        lateral = triceps_heads[triceps_heads["muscle_head"].str.contains("lateral", case=False)]
        if not long.empty and not lateral.empty:
            lv = long["percentage"].values[0]
            ltv = lateral["percentage"].values[0]
            if abs(lv - ltv) > 2:
                insights.append(
                    f"🔬 **Triceps balance**: Long head ({lv:.1f}%) vs Lateral head ({ltv:.1f}%) "
                    f"{'looks balanced' if abs(lv - ltv) < 4 else 'may need attention'}."
                )

    # Delts
    delt_heads = head_bal[head_bal["muscle_head"].str.contains("delt", case=False, na=False)]
    if len(delt_heads) >= 2:
        post = delt_heads[delt_heads["muscle_head"].str.contains("posterior", case=False)]
        lateral = delt_heads[delt_heads["muscle_head"].str.contains("lateral", case=False)]
        if not post.empty and not lateral.empty:
            pv = post["percentage"].values[0]
            lv = lateral["percentage"].values[0]
            if lv > 0:
                ratio = pv / lv
                if ratio < 0.5:
                    insights.append(
                        f"⚠️ **Posterior delt lag**: Only {pv:.1f}% vs {lv:.1f}% for lateral delt. "
                        "Add face pulls or reverse flyes."
                    )

    # Quads
    vmo = head_bal[head_bal["muscle_head"].str.contains("vastus_medialis|vmo", case=False, na=False)]
    vl = head_bal[head_bal["muscle_head"].str.contains("vastus_lateralis", case=False, na=False)]
    if not vmo.empty and not vl.empty:
        vmv = vmo["percentage"].values[0]
        vlv = vl["percentage"].values[0]
        if abs(vmv - vlv) < 2:
            insights.append(
                f"🔬 **Quad balance**: VMO ({vmv:.1f}%) vs VL ({vlv:.1f}%) are well balanced."
            )
        else:
            insights.append(
                f"🔬 **Quad balance**: VMO ({vmv:.1f}%) vs VL ({vlv:.1f}%) "
                f"{'looks balanced' if abs(vmv - vlv) < 4 else 'slightly imbalanced'}."
            )

    if not insights:
        insights.append("✅ Your muscle head balance looks reasonably well distributed.")
    return "<br>".join(insights[:4])


def render(
    sets_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    **_,
) -> None:
    st.title("🦵 Muscle Analysis")
    st.markdown("Detailed breakdown of your muscle development.")

    if sets_df.empty or templates_df.empty:
        st.warning("No workout or template data available.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Muscle Group Balance")
        balance = muscle_group_balance(sets_df, templates_df)
        if not balance.empty:
            fig = px.pie(
                balance, names="primary_muscle_group", values="volume_kg",
                color_discrete_sequence=_COLOR_SEQ, hole=0.3,
            )
            fig.update_layout(height=450)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Could not compute.")

    if "muscle_head_names" in sets_df.columns:
        with col2:
            st.subheader("Specific Muscle Head Balance")
            head_bal = muscle_head_balance(sets_df)
            if not head_bal.empty:
                top_h = head_bal.head(15)
                fig = px.bar(
                    top_h, x="percentage", y="muscle_head", orientation="h",
                    color="percentage", color_continuous_scale="viridis",
                    labels={"percentage": "% of volume", "muscle_head": ""},
                )
                fig.update_layout(height=450, yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig, use_container_width=True)

        if not head_bal.empty:
            insight("Muscle Head Insights", _generate_head_insights(head_bal), "🔬")

    st.markdown("---")
    st.subheader("Push vs Pull vs Legs Balance")
    balance = muscle_group_balance(sets_df, templates_df)
    if not balance.empty:
        push = {"chest", "triceps", "shoulders"}
        pull = {"lats", "upper_back", "lower_back", "traps", "biceps", "forearms"}
        legs = {"quadriceps", "hamstrings", "glutes", "calves", "abductors", "adductors"}

        def _cat(g: str) -> str:
            g = g.lower()
            if g in push: return "Push"
            if g in pull: return "Pull"
            if g in legs: return "Legs"
            return "Other"

        balance["category"] = balance["primary_muscle_group"].apply(_cat)
        cat_vol = balance.groupby("category")["volume_kg"].sum().reset_index()

        col1, col2 = st.columns([1, 1])
        with col1:
            fig = px.pie(
                cat_vol, names="category", values="volume_kg", color="category",
                color_discrete_map={"Push": "#FF6B6B", "Pull": "#4ECDC4", "Legs": "#45B7D1", "Other": "#96CEB4"},
                hole=0.4,
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            for _, row in cat_vol.iterrows():
                st.markdown(f"**{row['category']}**: {row['volume_kg']:,.0f} kg")
            if len(cat_vol) >= 3:
                p = cat_vol[cat_vol["category"] == "Push"]["volume_kg"].values[0] if "Push" in cat_vol["category"].values else 0
                pu = cat_vol[cat_vol["category"] == "Pull"]["volume_kg"].values[0] if "Pull" in cat_vol["category"].values else 0
                l = cat_vol[cat_vol["category"] == "Legs"]["volume_kg"].values[0] if "Legs" in cat_vol["category"].values else 0
                total = p + pu + l
                if total > 0:
                    insight("Push/Pull/Legs Ratio",
                        f"Push: **{p/total*100:.0f}%** | Pull: **{pu/total*100:.0f}%** | "
                        f"Legs: **{l/total*100:.0f}%** — "
                        f"{'Balanced' if max(p, pu, l) / total < 0.4 else 'Consider rebalancing.'}", "⚖️")

    st.markdown("---")
    st.subheader("Left vs Right Symmetry")
    try:
        sym = symmetrical_imbalance(sets_df)
        if not sym.empty and "left" in sym.columns and "right" in sym.columns:
            sym["ratio"] = sym["left"] / (sym["right"] + 1)
            sym["imbalance_pct"] = (abs(sym["ratio"] - 1) * 100).round(1)
            sym = sym.sort_values("imbalance_pct", ascending=False)

            fig = go.Figure()
            fig.add_trace(go.Bar(name="Left", x=sym["base_exercise"], y=sym["left"], marker_color="#4ECDC4"))
            fig.add_trace(go.Bar(name="Right", x=sym["base_exercise"], y=sym["right"], marker_color="#FF6B6B"))
            fig.update_layout(barmode="group", height=400, xaxis_title="Exercise", yaxis_title="Volume (kg)")
            st.plotly_chart(fig, use_container_width=True)

            imbalanced = sym[sym["imbalance_pct"] > 15]
            if not imbalanced.empty:
                insight("⚠️ Imbalance Detected",
                    f"{len(imbalanced)} exercise(s) with >15% left/right imbalance. "
                    "Consider adding unilateral work on the weaker side.", "⚠️")

            with st.expander("View symmetry data"):
                st.dataframe(sym, use_container_width=True)
        else:
            st.info("No unilateral (left/right) exercises found.")
    except Exception:
        st.info("No unilateral exercises to compare.")
