"""Dataclass models for food items, meals, and daily intake."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class FoodItem:
    """A food product with its nutritional profile per 100g."""

    barcode: str
    name: str
    brand: str = ""
    energy_kcal_100g: float = 0.0
    protein_100g: float = 0.0
    carbs_100g: float = 0.0
    fat_100g: float = 0.0
    fiber_100g: float = 0.0
    saturated_fat_100g: float = 0.0
    sugars_100g: float = 0.0
    salt_100g: float = 0.0
    serving_size_g: float | None = None
    image_url: str = ""
    ingredients_text: str = ""
    nutriscore: str = ""

    @classmethod
    def from_openfoodfacts(cls, data: dict[str, Any]) -> FoodItem:
        """Parse a FoodItem from the Open Food Facts API response."""
        product = data.get("product", data)
        n = product.get("nutriments", {})

        return cls(
            barcode=str(product.get("code", "")),
            name=product.get("product_name", "Unknown"),
            brand=product.get("brands", "") or "",
            energy_kcal_100g=float(n.get("energy-kcal_100g", 0) or 0),
            protein_100g=float(n.get("proteins_100g", 0) or 0),
            carbs_100g=float(n.get("carbohydrates_100g", 0) or 0),
            fat_100g=float(n.get("fat_100g", 0) or 0),
            fiber_100g=float(n.get("fiber_100g", 0) or 0),
            saturated_fat_100g=float(n.get("saturated-fat_100g", 0) or 0),
            sugars_100g=float(n.get("sugars_100g", 0) or 0),
            salt_100g=float(n.get("salt_100g", 0) or 0),
            serving_size_g=_safe_float(product.get("serving_size")),
            image_url=product.get("image_url", "") or "",
            ingredients_text=product.get("ingredients_text", "") or "",
            nutriscore=product.get("nutrition_grades", "") or "",
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "barcode": self.barcode,
            "name": self.name,
            "brand": self.brand,
            "energy_kcal_100g": self.energy_kcal_100g,
            "protein_100g": self.protein_100g,
            "carbs_100g": self.carbs_100g,
            "fat_100g": self.fat_100g,
            "fiber_100g": self.fiber_100g,
            "saturated_fat_100g": self.saturated_fat_100g,
            "sugars_100g": self.sugars_100g,
            "salt_100g": self.salt_100g,
            "serving_size_g": self.serving_size_g,
            "image_url": self.image_url,
            "ingredients_text": self.ingredients_text,
            "nutriscore": self.nutriscore,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FoodItem:
        """Deserialize from a dict (inverse of to_dict)."""
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


@dataclass
class MealEntry:
    """A single meal entry — a food item consumed at a specific amount."""

    id: str
    food: FoodItem
    amount_g: float
    meal_type: str  # breakfast, lunch, dinner, snack
    timestamp: str  # ISO 8601
    notes: str = ""

    @classmethod
    def create(
        cls,
        food: FoodItem,
        amount_g: float,
        meal_type: str,
        notes: str = "",
    ) -> MealEntry:
        """Create a new meal entry with auto-generated ID and timestamp."""
        return cls(
            id=uuid.uuid4().hex[:12],
            food=food,
            amount_g=amount_g,
            meal_type=meal_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            notes=notes,
        )

    @property
    def energy_kcal(self) -> float:
        return self.food.energy_kcal_100g * self.amount_g / 100

    @property
    def protein(self) -> float:
        return self.food.protein_100g * self.amount_g / 100

    @property
    def carbs(self) -> float:
        return self.food.carbs_100g * self.amount_g / 100

    @property
    def fat(self) -> float:
        return self.food.fat_100g * self.amount_g / 100

    @property
    def fiber(self) -> float:
        return self.food.fiber_100g * self.amount_g / 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "food": self.food.to_dict(),
            "amount_g": self.amount_g,
            "meal_type": self.meal_type,
            "timestamp": self.timestamp,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MealEntry:
        return cls(
            id=data["id"],
            food=FoodItem.from_dict(data["food"]),
            amount_g=data["amount_g"],
            meal_type=data["meal_type"],
            timestamp=data["timestamp"],
            notes=data.get("notes", ""),
        )


def _safe_float(value: Any) -> float | None:
    """Parse a value to float, returning None if not possible."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
