"""AI Nutritionist dashboard page — meal plans + Asana shopping list."""

from __future__ import annotations

import os

import streamlit as st

from nutrition.ai_nutritionist import AINutritionist
from nutrition.analysis import daily_totals
from nutrition.storage import NutritionStorage


def render(storage: NutritionStorage) -> None:
    """Render the AI Nutritionist page."""
    st.title("🤖 AI Nutritionist")
    st.markdown(
        "Generate meal plans and push ingredients to your Asana shopping list. "
        "Powered by the same LLM as the training coach."
    )

    # ---- Check Asana config ----
    asana_token = os.environ.get("ASANA_ACCESS_TOKEN", "")
    asana_project = os.environ.get("ASANA_SHOPPING_PROJECT_GID", "")
    asana_configured = bool(asana_token and asana_project)

    if not asana_configured:
        st.info(
            "⚠️ **Asana not configured** — shopping list sync won't work.\n\n"
            "Set `ASANA_ACCESS_TOKEN` and `ASANA_SHOPPING_PROJECT_GID` in your `.env` file.\n\n"
            "You can still generate meal plans without Asana."
        )

    # ---- Load current nutrition stats ----
    all_days = storage.load_all_days()
    current_calories = 0.0
    current_protein = 0.0

    if all_days:
        # Get the most recent day with data
        latest_day = max(all_days.keys())
        latest_entries = all_days[latest_day]
        latest_totals = daily_totals(latest_entries)
        current_calories = latest_totals["energy_kcal"]
        current_protein = latest_totals["protein_g"]

        st.caption(
            f"📊 Latest logged day ({latest_day}): "
            f"{current_calories:.0f} kcal · {current_protein:.1f}g protein"
        )
    else:
        st.caption("📊 No meal data yet — using defaults.")

    st.markdown("---")

    # ---- Plan form ----
    with st.form("nutritionist_form"):
        col1, col2 = st.columns(2)
        with col1:
            calories = st.number_input(
                "Daily calorie target",
                min_value=1200, max_value=6000, value=max(2000, int(current_calories) or 2500),
                step=50,
            )
            protein = st.number_input(
                "Daily protein target (g)",
                min_value=50, max_value=400, value=max(100, int(current_protein) or 180),
                step=5,
            )
            num_meals = st.selectbox("Number of meals", [3, 4, 5, 6], index=1)

        with col2:
            goal = st.text_input(
                "Training goal",
                value="General health and muscle maintenance",
            )
            preferences = st.text_area(
                "Dietary preferences / restrictions",
                value="No restrictions, prefer whole foods, Dutch supermarket friendly",
                height=68,
            )
            workouts_per_week = st.number_input("Workouts per week", min_value=1, max_value=14, value=4)

        st.markdown("---")

        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            submitted = st.form_submit_button(
                "🍽️ Generate Meal Plan",
                type="primary",
                use_container_width=True,
            )
        with col2:
            plan_and_shop = st.form_submit_button(
                "🛒 Plan + Add to Asana",
                type="secondary",
                use_container_width=True,
                disabled=not asana_configured,
            )

    # ---- Generate ----
    if submitted or plan_and_shop:
        llm_provider = st.session_state.get("ai_provider", "deepseek")

        with st.spinner("🧠 AI Nutritionist is thinking... (10-20s)"):
            nutritionist = AINutritionist(
                storage=storage,
                llm_provider=llm_provider,
            )

            if plan_and_shop:
                result = nutritionist.plan_and_shop(
                    asana_project=asana_project,
                    asana_token=asana_token,
                    calories=calories,
                    protein=protein,
                    num_meals=num_meals,
                    workouts_per_week=workouts_per_week,
                    goal=goal,
                    preferences=preferences,
                    current_calories=current_calories,
                    current_protein=current_protein,
                )
            else:
                result = {"meal_plan": nutritionist.generate_meal_plan(
                    calories=calories, protein=protein, num_meals=num_meals,
                    workouts_per_week=workouts_per_week, goal=goal,
                    preferences=preferences,
                    current_calories=current_calories, current_protein=current_protein,
                )}

        # ---- Display meal plan ----
        st.markdown("---")
        st.subheader("🍽️ Your Meal Plan")

        if "meal_plan" in result:
            st.markdown(result["meal_plan"])
        else:
            st.error("Failed to generate meal plan. Check your LLM provider config.")

        # ---- Display shopping list ----
        if "ingredients" in result and result["ingredients"]:
            st.markdown("---")
            st.subheader("🛒 Shopping List")

            if result.get("tasks_created", 0) > 0:
                st.success(
                    f"✅ {result['tasks_created']} ingredient(s) added to your "
                    f"Asana shopping list!"
                )

            # Group by store section
            from nutrition.ai_nutritionist import guess_store_section
            sections: dict[str, list[str]] = {}
            for item in result["ingredients"]:
                name = item["name"]
                section = guess_store_section(name)
                sections.setdefault(section, []).append(name)

            for section, items in sections.items():
                st.markdown(f"**{section}**")
                for item in items:
                    st.markdown(f"- {item}")
        elif "ingredients" in result:
            st.info("No ingredients could be extracted. Try regenerating.")

        st.markdown("---")
        st.caption(
            "⚠️ This is AI-generated advice. Always consult a qualified "
            "nutritionist for personalized dietary recommendations."
        )
