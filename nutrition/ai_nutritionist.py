"""AI Nutritionist — meal planning + Asana shopping list integration.

Uses the same LLM provider as the training advisor, but with
nutrition-focused prompts. Generates meal plans and pushes
ingredients straight to your Asana shopping list.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from hevy.env import load_dotenv
from nutrition.asana_shopping import AsanaShoppingList
from nutrition.models import FoodItem, MealEntry
from nutrition.storage import NutritionStorage

load_dotenv()

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

NUTRITIONIST_SYSTEM_PROMPT = """You are an expert nutritionist and meal planning AI. Your specialty is creating practical, nutritious meal plans based on training goals and dietary preferences.

Rules:
1. Base ALL recommendations on science — never guess or make up nutritional data.
2. Be specific: name exact foods, quantities, and preparation methods.
3. Consider the user's training data (workout volume, goals, macros) when planning meals.
4. Always output ingredients as a valid JSON array when asked for a shopping list.
5. Prioritize whole foods over processed options.
6. Account for Dutch supermarkets (Albert Heijn, Jumbo, Lidl) — suggest available products.
7. Keep meals practical and repeatable — nobody has 2 hours to cook every meal.
8. **CRITICAL: Output the COMPLETE meal plan. Do NOT truncate or abbreviate. Every meal must include full ingredient lists, quantities, and macros.**
9. Keep descriptions concise — use bullet points instead of paragraphs. One or two lines per meal component is enough."""

MEAL_PLAN_PROMPT_TEMPLATE = """Create a {num_meals}-meal nutrition plan for {calories} calories/day with approximately {protein}g protein.

Training context:
- Workouts per week: {workouts_per_week}
- Training goal: {goal}
- Dietary preferences: {preferences}
- Current daily avg: {current_calories:.0f} kcal, {current_protein:.0f}g protein

For each meal provide:
1. Meal name and description
2. Specific ingredients with quantities
3. Approximate macros (calories, protein, carbs, fat)

Keep ingredients practical for Dutch supermarkets."""

SHOPPING_LIST_PROMPT = """Based on this meal plan, extract ONLY the shopping list as a JSON array.

Meal plan:
{meal_plan}

Return ONLY a valid JSON array of objects with keys "name" and optionally "notes".
Example:
[
  {{"name": "Kipfilet 500g", "notes": "Albert Heijn"}},
  {{"name": "Volkorenpasta 1kg", "notes": ""}},
  {{"name": "Broccoli 2 stuks", "notes": ""}}
]

Do NOT include any text outside the JSON array."""


# ---------------------------------------------------------------------------
# AI Nutritionist
# ---------------------------------------------------------------------------

class AINutritionist:
    """Generates meal plans and syncs ingredients to Asana shopping list.

    Uses the same LLM provider as the training advisor.
    """

    def __init__(
        self,
        storage: NutritionStorage,
        llm_provider: str = "deepseek",
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._storage = storage
        self._llm_provider_name = llm_provider
        self._api_key = api_key
        self._model = model

    # ------------------------------------------------------------------
    # Meal plan generation
    # ------------------------------------------------------------------

    def generate_meal_plan(
        self,
        calories: int = 2500,
        protein: int = 180,
        num_meals: int = 4,
        workouts_per_week: int = 4,
        goal: str = "General health and muscle maintenance",
        preferences: str = "No restrictions, prefer whole foods",
        current_calories: float = 0,
        current_protein: float = 0,
        max_tokens: int = 8192,
    ) -> str:
        """Generate a meal plan using the LLM."""
        prompt = MEAL_PLAN_PROMPT_TEMPLATE.format(
            num_meals=num_meals,
            calories=calories,
            protein=protein,
            workouts_per_week=workouts_per_week,
            goal=goal,
            preferences=preferences,
            current_calories=current_calories or calories,
            current_protein=current_protein or protein,
        )
        return self._call_llm(prompt, max_tokens=max_tokens)

    def extract_shopping_list(self, meal_plan: str) -> list[dict[str, str]]:
        """Extract ingredients from a meal plan as a structured list."""
        prompt = SHOPPING_LIST_PROMPT.format(meal_plan=meal_plan)
        response = self._call_llm(prompt, max_tokens=2048)

        # Try to extract JSON from the response
        items = self._parse_json_array(response)

        # Add product categories as notes for Dutch supermarkets
        for item in items:
            name = item.get("name", "")
            notes = item.get("notes", "")
            if not notes:
                item["notes"] = guess_store_section(name)

        return items

    def plan_and_shop(
        self,
        asana_project: str | None = None,
        asana_token: str | None = None,
        max_tokens: int = 8192,
        **plan_kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a meal plan and push ingredients to Asana in one call.

        Returns:
            Dict with 'meal_plan' (str) and 'shopping_list' (list of tasks).
        """
        # Step 1: Generate meal plan
        meal_plan = self.generate_meal_plan(max_tokens=max_tokens, **plan_kwargs)

        # Step 2: Extract ingredients
        ingredients = self.extract_shopping_list(meal_plan)

        # Step 3: Push to Asana
        tasks_created = []
        if ingredients:
            try:
                with AsanaShoppingList(
                    access_token=asana_token,
                    project_gid=asana_project,
                ) as asana_api:
                    # Check for existing items first
                    existing = asana_api.list_shopping_tasks()
                    existing_names = {t["name"].lower() for t in existing}

                    new_items = [i for i in ingredients if i["name"].lower() not in existing_names]

                    if new_items:
                        tasks_created = asana_api.add_ingredients(new_items)
            except ValueError as e:
                # Asana not configured - that's ok, just return plan
                pass

        return {
            "meal_plan": meal_plan,
            "ingredients": ingredients,
            "tasks_created": len(tasks_created),
            "total_ingredients": len(ingredients),
            "asana_configured": len(tasks_created) > 0 or not ingredients,
        }

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, max_tokens: int = 8192) -> str:
        """Call the LLM and return the response text."""
        from hevy.llm.providers import LLMProvider

        provider_kwargs: dict[str, Any] = {
            "provider": self._llm_provider_name,
            "max_tokens": max_tokens,
        }
        if self._api_key:
            provider_kwargs["api_key"] = self._api_key
        if self._model:
            provider_kwargs["model"] = self._model

        provider = LLMProvider(**provider_kwargs)
        try:
            response = provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=NUTRITIONIST_SYSTEM_PROMPT,
            )
            return response.content
        finally:
            provider.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json_array(text: str) -> list[dict[str, str]]:
        """Extract a JSON array from LLM response text."""
        # Try to find JSON array between ``` markers
        json_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try parsing the whole response as JSON
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Try finding [...] anywhere in the text
        array_match = re.search(r"\[.*?\]", text, re.DOTALL)
        if array_match:
            try:
                return json.loads(array_match.group(0))
            except json.JSONDecodeError:
                pass

        return []


def guess_store_section(product_name: str) -> str:
    """Guess which supermarket section a product belongs to."""
    product_lower = product_name.lower()

    if any(w in product_lower for w in ["kip", "rund", "varken", "gehakt", "filet", "biefstuk", "kipfilet"]):
        return "🥩 Vlees/kip"
    if any(w in product_lower for w in ["melk", "kaas", "yoghurt", "kwark", "eieren", "boter", "room"]):
        return "🥛 Zuivel"
    if any(w in product_lower for w in ["brood", "pasta", "rijst", "couscous", "meel", "haver"]):
        return "🍞 Brood/graan"
    if any(w in product_lower for w in ["appel", "banaan", "sinaasappel", "druif", "framboos", "bes"]):
        return "🍎 Fruit"
    if any(w in product_lower for w in ["broccoli", "sla", "tomaat", "komkommer", "wortel", "ui", "knoflook", "spinazie"]):
        return "🥦 Groente"
    if any(w in product_lower for w in ["olie", "azijn", "kruid", "specerij", "zout", "peper"]):
        return "🧂 Olie/kruiden"
    if any(w in product_lower for w in ["noten", "amandel", "walnoot", "pinda", "cacao"]):
        return "🥜 Noten/zaden"
    return "🛒 Overig"
