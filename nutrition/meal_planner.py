"""Verified weekly meal planner — selects recipes from database to hit macro targets.

Algorithm:
1. Load all recipes from YAML files
2. For each day, try combinations of breakfast + lunch + dinner + (optional snack)
3. Score combos by how close they are to daily target macros
4. Ensure variety (no recipe repeats within a week)
5. Generate aggregated shopping list
6. Push to Asana
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any

import yaml

from nutrition.asana_shopping import AsanaShoppingList

# ── Types ───────────────────────────────────────────────────────────────


@dataclass
class Macros:
    calories: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0

    def __add__(self, other: Macros) -> Macros:
        return Macros(
            calories=self.calories + other.calories,
            protein=self.protein + other.protein,
            carbs=self.carbs + other.carbs,
            fat=self.fat + other.fat,
        )

    def score_vs_target(self, target: Macros) -> float:
        """Lower score = better fit. Penalizes deviation from target."""
        score = 0.0

        # Calorie match: under = heavily penalized, over = moderately penalized
        cal_pct = self.calories / target.calories if target.calories else 0
        if cal_pct < 0.90:
            score += (0.90 - cal_pct) * 300  # Heavy penalty for being under
        elif cal_pct < 0.97:
            score += (0.97 - cal_pct) * 150  # Moderate penalty
        elif cal_pct > 1.15:
            score += (cal_pct - 1.15) * 80   # Mild penalty for over
        elif cal_pct > 1.05:
            score += (cal_pct - 1.05) * 40   # Slight over

        # Protein: must hit at least 85%, slight excess is fine
        prot_pct = self.protein / target.protein if target.protein else 0
        if prot_pct < 0.85:
            score += (0.85 - prot_pct) * 150
        elif prot_pct > 1.4:
            score += (prot_pct - 1.4) * 40

        # Fat: stay within range
        fat_pct = self.fat / target.fat if target.fat else 0
        score += abs(fat_pct - 1.0) * 60

        # Carbs: moderate penalty for deviation
        carb_pct = self.carbs / target.carbs if target.carbs else 0
        if carb_pct < 0.6:
            score += (0.6 - carb_pct) * 60
        elif carb_pct > 1.5:
            score += (carb_pct - 1.5) * 30

        return score


@dataclass
class Ingredient:
    name: str
    amount: float
    unit: str
    macros: Macros = field(default_factory=Macros)


@dataclass
class Recipe:
    name: str
    meal_type: str
    prep_time_minutes: int
    servings: int
    ingredients: list[Ingredient]
    totals: Macros
    instructions: str
    tags: list[str] = field(default_factory=list)
    file_path: str = ""


@dataclass
class DayPlan:
    day: str = ""
    date: str = ""
    breakfast: Recipe | None = None
    lunch: Recipe | None = None
    dinner: Recipe | None = None
    snack: Recipe | None = None
    snack2: Recipe | None = None
    totals: Macros = field(default_factory=Macros)

    @property
    def recipes(self) -> list[Recipe]:
        return [r for r in [self.breakfast, self.lunch, self.dinner, self.snack, self.snack2] if r]


@dataclass
class WeeklyPlan:
    days: list[DayPlan]
    week_start: str  # ISO date of Monday
    totals: Macros = field(default_factory=Macros)
    shopping_list: list[Ingredient] = field(default_factory=list)


# ── Recipe Loader ───────────────────────────────────────────────────────


class RecipeDatabase:
    """Loads recipes from YAML files in nutrition/recipes/."""

    def __init__(self, recipes_dir: str | None = None) -> None:
        if recipes_dir is None:
            recipes_dir = str(Path(__file__).parent / "recipes")
        self._dir = Path(recipes_dir)
        self._recipes: list[Recipe] = []
        self._by_type: dict[str, list[Recipe]] = {}
        self._load()

    def _load(self) -> None:
        for yaml_file in sorted(self._dir.glob("*.yaml")):
            text = yaml_file.read_text()
            # Strip frontmatter if present
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    text = parts[2]

            recipes_data = yaml.safe_load(text)
            if not recipes_data:
                continue

            for r in recipes_data:
                if not isinstance(r, dict):
                    continue
                ingredients = []
                for ing in r.get("ingredients", []):
                    macros = ing.get("macros_per_100g", {})
                    ingredients.append(Ingredient(
                        name=ing.get("name", ""),
                        amount=float(ing.get("amount", 0)),
                        unit=ing.get("unit", "g"),
                        macros=Macros(
                            calories=macros.get("calories", 0),
                            protein=macros.get("protein", 0),
                            carbs=macros.get("carbs", 0),
                            fat=macros.get("fat", 0),
                        ),
                    ))

                totals = r.get("totals", {})
                recipe = Recipe(
                    name=r.get("name", ""),
                    meal_type=r.get("meal_type", ""),
                    prep_time_minutes=r.get("prep_time_minutes", 0),
                    servings=r.get("servings", 1),
                    ingredients=ingredients,
                    totals=Macros(
                        calories=totals.get("calories", 0),
                        protein=totals.get("protein", 0),
                        carbs=totals.get("carbs", 0),
                        fat=totals.get("fat", 0),
                    ),
                    instructions=r.get("instructions", ""),
                    tags=r.get("tags", []),
                    file_path=str(yaml_file),
                )
                self._recipes.append(recipe)
                meal_type = r.get("meal_type", "other")
                if meal_type not in self._by_type:
                    self._by_type[meal_type] = []
                self._by_type[meal_type].append(recipe)

    @property
    def all(self) -> list[Recipe]:
        return self._recipes

    def by_type(self, meal_type: str) -> list[Recipe]:
        return self._by_type.get(meal_type, [])

    @property
    def breakfasts(self) -> list[Recipe]:
        return self.by_type("breakfast")

    @property
    def brunches(self) -> list[Recipe]:
        return self.by_type("brunch")

    @property
    def lunches(self) -> list[Recipe]:
        return self.by_type("lunch")

    @property
    def dinners(self) -> list[Recipe]:
        return self.by_type("dinner")

    @property
    def snacks(self) -> list[Recipe]:
        return self.by_type("snack")

    def stats(self) -> dict[str, int]:
        return {t: len(v) for t, v in sorted(self._by_type.items())}


# ── Meal Planner ────────────────────────────────────────────────────────


class VerifiedMealPlanner:
    """Generates weekly meal plans from verified recipe data."""

    def __init__(
        self,
        recipe_db: RecipeDatabase | None = None,
    ) -> None:
        self._db = recipe_db or RecipeDatabase()

    def generate_weekly_plan(
        self,
        target_calories: int = 2200,
        target_protein: float = 170,
        target_fat: float = 60,
        target_carbs: float = 245,
        start_date: date | None = None,
        max_attempts: int = 2000,
    ) -> WeeklyPlan:
        """Generate a 7-day meal plan hitting the macro targets."""
        target = Macros(
            calories=float(target_calories),
            protein=target_protein,
            carbs=target_carbs,
            fat=target_fat,
        )

        if start_date is None:
            # Find next Monday
            today = date.today()
            start_date = today + timedelta(days=(7 - today.weekday()) % 7)

        days: list[DayPlan] = []
        used_recipes: set[str] = set()

        for i in range(7):
            day_date = start_date + timedelta(days=i)
            day_name = day_date.strftime("%A")
            day = self._generate_day(
                target=target,
                used_recipes=used_recipes,
                max_attempts=max_attempts,
            )
            day.day = day_name
            day.date = day_date.isoformat()

            for r in day.recipes:
                used_recipes.add(r.name)

            days.append(day)

        # Compute weekly totals
        weekly_totals = Macros()
        for day in days:
            weekly_totals += day.totals

        # Generate shopping list
        shopping_list = self.generate_shopping_list(days)

        return WeeklyPlan(
            days=days,
            week_start=start_date.isoformat(),
            totals=weekly_totals,
            shopping_list=shopping_list,
        )

    def _generate_day(
        self,
        target: Macros,
        used_recipes: set[str],
        max_attempts: int = 200,
    ) -> DayPlan:
        """Generate one day by trying recipe combinations."""
        best_score = float("inf")
        best_combo: dict[str, Recipe | None] = {
            "breakfast": None,
            "lunch": None,
            "dinner": None,
            "snack": None,
            "snack2": None,
        }

        breakfasts = [r for r in self._db.breakfasts if r.name not in used_recipes]
        lunches = [r for r in self._db.lunches if r.name not in used_recipes]
        dinners = [r for r in self._db.dinners if r.name not in used_recipes]
        snacks = [r for r in self._db.snacks if r.name not in used_recipes]

        # Fallback: allow repeats if we run out of unique recipes
        if not breakfasts:
            breakfasts = self._db.breakfasts
        if not lunches:
            lunches = self._db.lunches
        if not dinners:
            dinners = self._db.dinners
        if not snacks:
            snacks = self._db.snacks

        for _ in range(max_attempts):
            b = random.choice(breakfasts) if breakfasts else None
            l = random.choice(lunches) if lunches else None
            d = random.choice(dinners) if dinners else None

            # Check if we need a snack (breakfast+lunch+dinner < 75% target calories)
            base_cals = (b.totals.calories if b else 0) + (l.totals.calories if l else 0) + (d.totals.calories if d else 0)
            need_snack = base_cals < target.calories * 0.75

            # Allow up to 2 snacks if calories are too low
            s1 = random.choice(snacks) if snacks and (need_snack or random.random() < 0.7) else None
            s1_cals = s1.totals.calories if s1 else 0
            remaining_after_s1 = snacks
            if s1:
                remaining_after_s1 = [s for s in snacks if s.name != s1.name]
            s2 = random.choice(remaining_after_s1) if remaining_after_s1 and s1 and base_cals + s1_cals < target.calories * 0.90 and random.random() < 0.6 else None

            combo_totals = Macros()
            if b:
                combo_totals += b.totals
            if l:
                combo_totals += l.totals
            if d:
                combo_totals += d.totals
            if s1:
                combo_totals += s1.totals
            if s2:
                combo_totals += s2.totals

            score = combo_totals.score_vs_target(target)
            if score < best_score:
                best_score = score
                best_combo = {"breakfast": b, "lunch": l, "dinner": d, "snack": s1, "snack2": s2}

            # Early exit if good enough
            if score < 12:
                break

        day = DayPlan()
        day.breakfast = best_combo["breakfast"]
        day.lunch = best_combo["lunch"]
        day.dinner = best_combo["dinner"]
        day.snack = best_combo.get("snack")
        day.snack2 = best_combo.get("snack2")

        day.totals = Macros()
        for r in day.recipes:
            day.totals += r.totals

        return day

    def generate_shopping_list(
        self,
        days: list[DayPlan],
    ) -> list[Ingredient]:
        """Aggregate and deduplicate ingredients across all days."""
        # Collect all ingredients
        all_items: dict[str, dict[str, Any]] = {}

        for day in days:
            for recipe in day.recipes:
                for ing in recipe.ingredients:
                    key = ing.name.lower().strip()
                    if key in all_items:
                        all_items[key]["amount"] += ing.amount
                    else:
                        all_items[key] = {
                            "name": ing.name,
                            "amount": ing.amount,
                            "unit": ing.unit,
                            "macros": ing.macros,
                        }

        # Convert back to Ingredient list, sorted by supermarket section
        result = []
        for key, item in all_items.items():
            result.append(Ingredient(
                name=item["name"],
                amount=round(item["amount"], 1),
                unit=item["unit"],
                macros=item["macros"],
            ))

        return result

    def push_to_asana(
        self,
        shopping_list: list[Ingredient],
        project_gid: str | None = None,
        asana_token: str | None = None,
    ) -> int:
        """Push the shopping list to Asana. Returns number of tasks created."""
        from hevy.env import load_dotenv
        load_dotenv()

        token = asana_token or os.environ.get("ASANA_ACCESS_TOKEN", "")
        gid = project_gid or os.environ.get("ASANA_SHOPPING_PROJECT_GID", "")

        if not token or not gid:
            return 0

        try:
            with AsanaShoppingList(access_token=token, project_gid=gid) as asana_api:
                existing = asana_api.list_shopping_tasks()
                existing_names = {t["name"].lower() for t in existing}

                created = 0
                for ing in shopping_list:
                    # Format: "Kipfilet 600g"
                    item_name = f"{ing.name} {ing.amount:.0f}{ing.unit}"
                    if item_name.lower() in existing_names:
                        continue

                    macros_str = f"P{ing.macros.protein:.0f}/C{ing.macros.carbs:.0f}/F{ing.macros.fat:.0f} — {ing.macros.calories:.0f}kcal"
                    task = asana_api.add_ingredient(
                        name=item_name,
                        notes=macros_str,
                    )
                    if task:
                        created += 1

                return created
        except Exception:
            return 0

    def to_dict(self, plan: WeeklyPlan) -> dict[str, Any]:
        """Serialize a weekly plan to a dict (for JSON export)."""
        return {
            "week_start": plan.week_start,
            "generated_at": datetime.now().isoformat(),
            "target_macros": {
                "calories": sum(d.totals.calories for d in plan.days) / len(plan.days),
                "protein": sum(d.totals.protein for d in plan.days) / len(plan.days),
                "carbs": sum(d.totals.carbs for d in plan.days) / len(plan.days),
                "fat": sum(d.totals.fat for d in plan.days) / len(plan.days),
            },
            "weekly_totals": asdict(plan.totals),
            "days": [
                {
                    "day": d.day,
                    "date": d.date,
                    "meals": [
                        {
                            "type": r.meal_type,
                            "name": r.name,
                            "macros": asdict(r.totals),
                            "ingredients": [
                                {"name": i.name, "amount": i.amount, "unit": i.unit}
                                for i in r.ingredients
                            ],
                            "instructions": r.instructions,
                        }
                        for r in d.recipes
                    ],
                    "daily_totals": asdict(d.totals),
                }
                for d in plan.days
            ],
            "shopping_list": [
                {"name": i.name, "amount": i.amount, "unit": i.unit}
                for i in plan.shopping_list
            ],
        }

    def format_plan_text(self, plan: WeeklyPlan) -> str:
        """Format a weekly plan as readable text."""
        lines = [
            "╔══════════════════════════════════════╗",
            f"║  WEEKLY MEAL PLAN  —  {plan.week_start}  ║",
            "╚══════════════════════════════════════╝",
            "",
        ]

        for day in plan.days:
            lines.append(f"─── {day.day} ({day.date}) ───")
            for meal in day.recipes:
                m = meal.totals
                lines.append(f"  {meal.meal_type.upper()}: {meal.name}")
                lines.append(f"    {m.calories:.0f} kcal | P{m.protein:.0f}g | C{m.carbs:.0f}g | F{m.fat:.0f}g")
            lines.append(f"  ── Totaal: {day.totals.calories:.0f} kcal | P{day.totals.protein:.0f}g | C{day.totals.carbs:.0f}g | F{day.totals.fat:.0f}g")
            lines.append("")

        # Weekly averages
        avg = Macros(
            calories=plan.totals.calories / 7,
            protein=plan.totals.protein / 7,
            carbs=plan.totals.carbs / 7,
            fat=plan.totals.fat / 7,
        )
        lines.append("═══════════════════════════════════════")
        lines.append("WEEKLY AVERAGES:")
        lines.append(f"  {avg.calories:.0f} kcal | P{avg.protein:.0f}g | C{avg.carbs:.0f}g | F{avg.fat:.0f}g")
        lines.append(f"  Weekly totals: {plan.totals.calories:.0f} kcal total")
        lines.append("")

        lines.append("═══ SHOPPING LIST ═══")
        for ing in plan.shopping_list:
            lines.append(f"  ☐ {ing.name} — {ing.amount:.0f}{ing.unit}")
        lines.append("")

        return "\n".join(lines)
