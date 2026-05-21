"""Nutrition analysis — daily totals, macro splits, and trends.

Mirrors the patterns in hevy/analysis.py.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from nutrition.models import MealEntry


# ---------------------------------------------------------------------------
# Per-day helpers
# ---------------------------------------------------------------------------

def daily_totals(entries: list[MealEntry]) -> dict[str, float]:
    """Aggregate a list of entries into total daily nutrition."""
    return {
        "energy_kcal": sum(e.energy_kcal for e in entries),
        "protein_g": sum(e.protein for e in entries),
        "carbs_g": sum(e.carbs for e in entries),
        "fat_g": sum(e.fat for e in entries),
        "fiber_g": sum(e.fiber for e in entries),
        "saturated_fat_g": sum(e.food.saturated_fat_100g * e.amount_g / 100 for e in entries),
        "sugars_g": sum(e.food.sugars_100g * e.amount_g / 100 for e in entries),
        "salt_g": sum(e.food.salt_100g * e.amount_g / 100 for e in entries),
        "meal_count": len(entries),
    }


def totals_by_meal_type(entries: list[MealEntry]) -> dict[str, dict[str, float]]:
    """Split daily totals by meal type (breakfast/lunch/dinner/snack)."""
    by_type: dict[str, list[MealEntry]] = {}
    for e in entries:
        by_type.setdefault(e.meal_type, []).append(e)
    return {mtype: daily_totals(mtype_entries) for mtype, mtype_entries in by_type.items()}


def macro_percentages(entries: list[MealEntry]) -> dict[str, float]:
    """Calculate macro split as percentages of total calories.

    Protein/Carbs/Fat → kcal (protein=4cal/g, carbs=4cal/g, fat=9cal/g).
    """
    totals = daily_totals(entries)
    p = totals["protein_g"] * 4
    c = totals["carbs_g"] * 4
    f = totals["fat_g"] * 9
    total = p + c + f
    if total == 0:
        return {"protein_pct": 0, "carbs_pct": 0, "fat_pct": 0}
    return {
        "protein_pct": round(p / total * 100, 1),
        "carbs_pct": round(c / total * 100, 1),
        "fat_pct": round(f / total * 100, 1),
    }


# ---------------------------------------------------------------------------
# Period aggregators
# ---------------------------------------------------------------------------

def period_totals(
    entries_by_day: dict[str, list[MealEntry]],
) -> pd.DataFrame:
    """Convert per-day meal data into a DataFrame with daily totals.

    Returns a DataFrame with columns: date, energy_kcal, protein_g, carbs_g, fat_g, ...
    """
    rows: list[dict[str, Any]] = []
    for day, entries in sorted(entries_by_day.items()):
        totals = daily_totals(entries)
        totals["date"] = day
        rows.append(totals)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def weekly_averages(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute weekly averages from a daily totals DataFrame.

    Expects a 'date' column (convertible to datetime).
    """
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].dt.isocalendar().week.astype(int)
    df["year"] = df["date"].dt.year
    numeric_cols = [c for c in df.columns if c not in ("date", "week", "year")]
    weekly = df.groupby(["year", "week"])[numeric_cols].mean().reset_index()
    weekly["label"] = weekly.apply(lambda r: f"W{r['week']} {r['year']}", axis=1)
    return weekly


# ---------------------------------------------------------------------------
# Meal density helpers
# ---------------------------------------------------------------------------

def meal_density(entry: MealEntry) -> dict[str, float]:
    """Calculate nutrient density per 100g for a single meal entry."""
    if entry.amount_g <= 0:
        return {"energy_kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    factor = 100 / entry.amount_g
    return {
        "energy_kcal": entry.energy_kcal * factor,
        "protein_g": entry.protein * factor,
        "carbs_g": entry.carbs * factor,
        "fat_g": entry.fat * factor,
    }
