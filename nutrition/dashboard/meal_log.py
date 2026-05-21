"""Meal Log page — log food, search Open Food Facts, track daily intake."""

from __future__ import annotations

from datetime import date

import streamlit as st

from nutrition.analysis import daily_totals, macro_percentages, totals_by_meal_type
from nutrition.client import OpenFoodFactsClient
from nutrition.models import FoodItem, MealEntry
from nutrition.storage import NutritionStorage


def render(storage: NutritionStorage) -> None:
    """Render the Meal Log page."""
    st.title("🍽️ Meal Log")
    st.markdown("Log what you eat. Search by name or enter a barcode.")

    # ---- Date selector ----
    log_date = st.date_input("Date", value=date.today(), key="meal_log_date")
    day_str = log_date.isoformat()

    # Load existing entries for this day
    day_entries = storage.load_day(day_str)

    # ---- Search / Manual entry ----
    with st.expander("➕ Add Meal Entry", expanded=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input(
                "Search food (name or barcode)",
                placeholder="e.g. 'hagelslag', 'kipfilet', or scan barcode...",
                key="meal_search",
            )
        with col2:
            meal_type = st.selectbox(
                "Meal type",
                ["breakfast", "lunch", "dinner", "snack"],
                key="meal_type_select",
            )

        if search_query:
            with st.spinner("Searching Open Food Facts..."):
                items = _search_food(search_query)

            if items:
                st.markdown(f"Found **{len(items)}** product(s):")
                for i, item in enumerate(items):
                    _render_search_result(item, meal_type, day_entries, storage, day_str)
            else:
                st.info("No results found. Try a different search term or barcode.")

        # Manual entry fallback
        with st.expander("✏️ Or enter manually"):
            with st.form("manual_food_form"):
                name = st.text_input("Food name")
                brand = st.text_input("Brand (optional)")
                kcal = st.number_input("kcal/100g", min_value=0.0, value=0.0, step=10.0)
                protein = st.number_input("Protein/100g (g)", min_value=0.0, value=0.0, step=1.0)
                carbs = st.number_input("Carbs/100g (g)", min_value=0.0, value=0.0, step=1.0)
                fat = st.number_input("Fat/100g (g)", min_value=0.0, value=0.0, step=1.0)
                fiber = st.number_input("Fiber/100g (g)", min_value=0.0, value=0.0, step=0.1)
                amount_g = st.number_input("Amount eaten (g)", min_value=1.0, value=100.0, step=10.0)

                if st.form_submit_button("Add Manual Entry"):
                    food = FoodItem(
                        barcode="manual",
                        name=name,
                        brand=brand,
                        energy_kcal_100g=kcal,
                        protein_100g=protein,
                        carbs_100g=carbs,
                        fat_100g=fat,
                        fiber_100g=fiber,
                    )
                    entry = MealEntry.create(food=food, amount_g=amount_g, meal_type=meal_type)
                    storage.save_entry(entry)
                    st.success(f"✅ Added: {name}")
                    st.rerun()

    # ---- Today's meals summary ----
    st.markdown("---")
    st.subheader(f"📋 Meals on {day_str}")

    if not day_entries:
        st.info("No meals logged for this day. Add something above!")
    else:
        # Calculate and display totals
        totals = daily_totals(day_entries)
        macros = macro_percentages(day_entries)
        by_type = totals_by_meal_type(day_entries)

        # Top-level metrics
        cols = st.columns(5)
        cols[0].metric("🔥 Calories", f'{totals["energy_kcal"]:.0f} kcal')
        cols[1].metric("💪 Protein", f'{totals["protein_g"]:.1f}g')
        cols[2].metric("🍚 Carbs", f'{totals["carbs_g"]:.1f}g')
        cols[3].metric("🧈 Fat", f'{totals["fat_g"]:.1f}g')
        cols[4].metric("🌾 Fiber", f'{totals["fiber_g"]:.1f}g')

        st.markdown(
            f"**Macro split**: Protein {macros['protein_pct']}% "
            f"· Carbs {macros['carbs_pct']}% · Fat {macros['fat_pct']}%"
        )

        # Per-meal-type breakdown
        st.markdown("#### By Meal")
        for mtype in ["breakfast", "lunch", "dinner", "snack"]:
            if mtype in by_type:
                t = by_type[mtype]
                emoji = {"breakfast": "🌅", "lunch": "☀️", "dinner": "🌙", "snack": "🍪"}
                with st.expander(f"{emoji.get(mtype, '🍽️')} {mtype.title()} ({t['energy_kcal']:.0f} kcal)", expanded=True):
                    cols = st.columns([4, 2, 2, 1])
                    cols[0].markdown("**Food**")
                    cols[1].markdown("**Amount**")
                    cols[2].markdown("**Calories**")
                    cols[3].markdown("**Del**")

                    for entry in day_entries:
                        if entry.meal_type != mtype:
                            continue
                        cols = st.columns([4, 2, 2, 1])
                        cols[0].markdown(
                            f"{entry.food.name}"
                            + (f" *({entry.food.brand})*" if entry.food.brand else "")
                        )
                        cols[1].markdown(f"{entry.amount_g:.0f}g")
                        cols[2].markdown(f"{entry.energy_kcal:.0f}")
                        if cols[3].button("🗑️", key=f"del_{entry.id}"):
                            storage.delete_entry(entry.id, day_str)
                            st.rerun()


def _search_food(query: str) -> list[FoodItem]:
    """Search Open Food Facts, trying NL first, then global."""
    client = OpenFoodFactsClient()
    try:
        # Check if it looks like a barcode
        if query.isdigit() and len(query) >= 8:
            result = client.lookup_barcode(query)
            if result:
                return [result]

        # Text search — NL first, then all countries
        items = client.search(query, page_size=8)
        if items:
            return items
        return client.search_all_countries(query, page_size=8)
    finally:
        client.close()


def _render_search_result(
    item: FoodItem,
    meal_type: str,
    day_entries: list[MealEntry],
    storage: NutritionStorage,
    day_str: str,
) -> None:
    """Display a single search result with an 'Add' button."""
    with st.container():
        cols = st.columns([3, 1, 1, 1, 1])
        with cols[0]:
            st.markdown(f"**{item.name}**")
            if item.brand:
                st.caption(f"{item.brand}")
        with cols[1]:
            st.caption(f"{item.energy_kcal_100g:.0f} kcal/100g")
        with cols[2]:
            st.caption(f"P:{item.protein_100g:.1f} C:{item.carbs_100g:.1f} F:{item.fat_100g:.1f}")

        # Amount + Add button
        amount_key = f"amt_{item.barcode}"
        default_amount = item.serving_size_g or 100.0
        amount = st.number_input(
            "g",
            min_value=1.0,
            value=default_amount,
            step=10.0,
            key=amount_key,
            label_visibility="collapsed",
        )

        with cols[3]:
            st.caption(f"→ {item.energy_kcal_100g * amount / 100:.0f} kcal")

        with cols[4]:
            if st.button("➕ Add", key=f"add_{item.barcode}_{meal_type}"):
                entry = MealEntry.create(food=item, amount_g=amount, meal_type=meal_type)
                storage.save_entry(entry)
                st.success(f"✅ Added {item.name}")
                st.rerun()

        # Show ingredients/nutriscore if available
        if item.ingredients_text or item.nutriscore:
            details = []
            if item.nutriscore:
                details.append(f"Nutri-Score: **{item.nutriscore.upper()}**")
            if item.ingredients_text:
                details.append(f"📝 {item.ingredients_text[:120]}...")
            st.caption(" | ".join(details))

        st.markdown("---")
