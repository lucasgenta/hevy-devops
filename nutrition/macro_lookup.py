"""Verified macro lookup — authoritative nutritional data for ingredients.

Combines multiple data sources:
1. Built-in reference database (USDA SR Legacy values for common ingredients)
2. Open Food Facts API (branded products, NL-focused)
3. USDA FoodData Central API (fallback for novel ingredients)

Results are cached to avoid redundant API calls.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import httpx

from nutrition.client import OpenFoodFactsClient

# ── Built-in reference macros (per 100g) from USDA SR Legacy ────────────
# These are well-established values for common cooking ingredients.
# Source: USDA FoodData Central SR Legacy database.

MACRO_DB: dict[str, dict[str, float]] = {
    # Proteins (raw unless noted)
    "kipfilet": {"calories": 110, "protein": 23.0, "carbs": 0.0, "fat": 1.5},
    "kipfilet (rauw)": {"calories": 110, "protein": 23.0, "carbs": 0.0, "fat": 1.5},
    "kipfilet (gegrild)": {"calories": 165, "protein": 31.0, "carbs": 0.0, "fat": 3.6},
    "zalmfilet (rauw)": {"calories": 188, "protein": 20.4, "carbs": 0.0, "fat": 11.0},
    "zalm (rauw)": {"calories": 188, "protein": 20.4, "carbs": 0.0, "fat": 11.0},
    "gerookte zalm": {"calories": 117, "protein": 18.0, "carbs": 0.0, "fat": 4.5},
    "tilapiafilet (rauw)": {"calories": 96, "protein": 20.0, "carbs": 0.0, "fat": 1.7},
    "tonijn (blik in water)": {"calories": 116, "protein": 26.0, "carbs": 0.0, "fat": 0.8},
    "rundergehakt (mager)": {"calories": 160, "protein": 21.0, "carbs": 0.0, "fat": 8.0},
    "rundergehakt (mager 93/7)": {"calories": 160, "protein": 21.0, "carbs": 0.0, "fat": 8.0},
    "runderlappen (voor stoof)": {"calories": 180, "protein": 26.0, "carbs": 0.0, "fat": 8.0},
    "eieren": {"calories": 143, "protein": 12.4, "carbs": 0.7, "fat": 10.0},

    # Dairy & Eggs
    "magere kwark": {"calories": 59, "protein": 10.0, "carbs": 3.6, "fat": 0.2},
    "griekse yoghurt (0% vet)": {"calories": 59, "protein": 10.3, "carbs": 3.6, "fat": 0.2},
    "skyr (icelandic yogurt)": {"calories": 60, "protein": 11.0, "carbs": 3.7, "fat": 0.2},
    "hüttenkäse (cottage cheese)": {"calories": 72, "protein": 10.0, "carbs": 3.0, "fat": 1.0},
    "halfvolle melk": {"calories": 50, "protein": 3.4, "carbs": 4.8, "fat": 1.5},
    "mozzarella (part skim)": {"calories": 280, "protein": 28.0, "carbs": 3.0, "fat": 17.0},
    "feta": {"calories": 264, "protein": 14.2, "carbs": 4.0, "fat": 21.0},
    "parmezaanse kaas": {"calories": 431, "protein": 38.0, "carbs": 4.1, "fat": 29.0},

    # Grains & Carbs
    "havermout": {"calories": 379, "protein": 13.0, "carbs": 68.0, "fat": 7.0},
    "basmatirijst (droog)": {"calories": 350, "protein": 7.0, "carbs": 78.0, "fat": 0.5},
    "basmatirijst (ongekookt)": {"calories": 350, "protein": 7.0, "carbs": 78.0, "fat": 0.5},
    "volkoren pasta (droog)": {"calories": 350, "protein": 13.0, "carbs": 71.0, "fat": 1.7},
    "volkoren spaghetti (droog)": {"calories": 350, "protein": 13.0, "carbs": 71.0, "fat": 1.7},
    "quinoa (droog)": {"calories": 368, "protein": 14.0, "carbs": 64.0, "fat": 6.0},
    "couscous (droog)": {"calories": 376, "protein": 13.0, "carbs": 77.0, "fat": 0.6},
    "volkorenbrood": {"calories": 247, "protein": 13.0, "carbs": 44.0, "fat": 3.6},
    "volkoren wrap": {"calories": 300, "protein": 9.0, "carbs": 52.0, "fat": 6.0},
    "volkoren crackers": {"calories": 380, "protein": 10.0, "carbs": 68.0, "fat": 6.0},
    "rijstwafels (naturel)": {"calories": 380, "protein": 8.0, "carbs": 80.0, "fat": 3.0},
    "granola (zonder suiker)": {"calories": 450, "protein": 10.0, "carbs": 65.0, "fat": 15.0},

    # Vegetables
    "broccoli": {"calories": 34, "protein": 2.8, "carbs": 7.0, "fat": 0.4},
    "spinazie (vers)": {"calories": 23, "protein": 2.9, "carbs": 3.6, "fat": 0.4},
    "zoete aardappel": {"calories": 86, "protein": 1.6, "carbs": 20.0, "fat": 0.1},
    "sperziebonen": {"calories": 31, "protein": 1.8, "carbs": 7.0, "fat": 0.2},
    "romeinse sla": {"calories": 17, "protein": 1.2, "carbs": 3.3, "fat": 0.3},
    "ijsbergsla": {"calories": 14, "protein": 0.9, "carbs": 3.0, "fat": 0.1},
    "komkommer": {"calories": 15, "protein": 0.7, "carbs": 3.6, "fat": 0.1},
    "paprika": {"calories": 31, "protein": 1.0, "carbs": 6.0, "fat": 0.3},
    "cherry tomaten": {"calories": 18, "protein": 0.9, "carbs": 3.9, "fat": 0.2},
    "courgette": {"calories": 17, "protein": 1.2, "carbs": 3.1, "fat": 0.3},
    "ui": {"calories": 40, "protein": 1.1, "carbs": 9.0, "fat": 0.1},
    "uien": {"calories": 40, "protein": 1.1, "carbs": 9.0, "fat": 0.1},
    "wortel": {"calories": 41, "protein": 0.9, "carbs": 10.0, "fat": 0.2},
    "groene asperges": {"calories": 20, "protein": 2.2, "carbs": 4.0, "fat": 0.1},

    # Fruit
    "banaan": {"calories": 89, "protein": 1.1, "carbs": 23.0, "fat": 0.3},
    "appel (goudreinette)": {"calories": 52, "protein": 0.3, "carbs": 14.0, "fat": 0.2},
    "blauwe bessen": {"calories": 57, "protein": 0.7, "carbs": 14.5, "fat": 0.3},
    "frambozen (diepvries)": {"calories": 52, "protein": 1.2, "carbs": 12.0, "fat": 0.7},
    "avocado": {"calories": 160, "protein": 2.0, "carbs": 9.0, "fat": 15.0},

    # Fats, Oils & Nuts
    "olijfolie": {"calories": 884, "protein": 0.0, "carbs": 0.0, "fat": 100.0},
    "pindakaas (100% pinda)": {"calories": 588, "protein": 25.0, "carbs": 20.0, "fat": 50.0},
    "amandelen (ongezouten)": {"calories": 579, "protein": 21.0, "carbs": 22.0, "fat": 50.0},

    # Other
    "whey protein (vanille)": {"calories": 395, "protein": 90.0, "carbs": 4.0, "fat": 3.0},
    "whey protein": {"calories": 395, "protein": 90.0, "carbs": 4.0, "fat": 3.0},
    "passata (gezeefde tomaten)": {"calories": 32, "protein": 1.5, "carbs": 7.0, "fat": 0.3},
    "currypasta (rode)": {"calories": 100, "protein": 2.0, "carbs": 10.0, "fat": 6.0},
    "kokosmelk (light)": {"calories": 66, "protein": 0.7, "carbs": 2.8, "fat": 6.0},
    "runderbouillon": {"calories": 5, "protein": 0.5, "carbs": 0.5, "fat": 0.1},
    "krielaardappeltjes": {"calories": 77, "protein": 2.0, "carbs": 17.5, "fat": 0.1},
    "aardappels": {"calories": 77, "protein": 2.0, "carbs": 17.5, "fat": 0.1},
    "groene pesto": {"calories": 490, "protein": 5.0, "carbs": 8.0, "fat": 49.0},
    "zwarte bonen (blik)": {"calories": 132, "protein": 8.9, "carbs": 24.0, "fat": 0.5},
    "yoghurt dressing (0% vet)": {"calories": 59, "protein": 10.3, "carbs": 3.6, "fat": 0.2},
}

# Normalize lookups: lowercase, strip parentheticals
_LOOKUP_MAP: dict[str, dict[str, float]] = {}
for key, val in MACRO_DB.items():
    clean = key.lower().strip()
    _LOOKUP_MAP[clean] = val
    # Also add without parentheticals
    if "(" in clean:
        base = clean.split("(")[0].strip()
        _LOOKUP_MAP[base] = val


# ── Cache ───────────────────────────────────────────────────────────────

CACHE_DIR = Path(__file__).parent / ".." / "data" / "macro_cache"
CACHE_FILE = CACHE_DIR / "lookup_cache.json"


def _load_cache() -> dict[str, dict[str, float]]:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(cache: dict[str, dict[str, float]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


# ── Public API ──────────────────────────────────────────────────────────


@dataclass
class MacroResult:
    calories: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0
    source: str = "builtin"
    per_100g: bool = True


def lookup_ingredient(
    name: str,
    use_openfoodfacts: bool = True,
    use_usda: bool = True,
) -> MacroResult | None:
    """Look up macros for an ingredient by name.

    Priority: local cache → built-in database → Open Food Facts → USDA FDC.
    Returns macros per 100g, or None if not found.
    """
    clean = name.strip().lower()

    # 1. Check cache
    cache = _load_cache()
    if clean in cache:
        return MacroResult(**cache[clean], source="cache")

    # 2. Built-in DB
    if clean in _LOOKUP_MAP:
        result = MacroResult(**_LOOKUP_MAP[clean], source="builtin")
        cache[clean] = asdict(result)
        _save_cache(cache)
        return result

    # Try to match by substring
    for key, val in _LOOKUP_MAP.items():
        if clean in key or key in clean:
            result = MacroResult(**val, source="builtin")
            cache[clean] = asdict(result)
            _save_cache(cache)
            return result

    # 3. Open Food Facts
    if use_openfoodfacts:
        try:
            with OpenFoodFactsClient(country="nl") as off:
                results = off.search(clean, page_size=3)
                if results:
                    item = results[0]
                    result = MacroResult(
                        calories=item.energy_kcal_100g,
                        protein=item.protein_100g,
                        carbs=item.carbs_100g,
                        fat=item.fat_100g,
                        source="openfoodfacts",
                    )
                    cache[clean] = asdict(result)
                    _save_cache(cache)
                    return result
        except Exception:
            pass

    # 4. USDA FoodData Central
    if use_usda:
        try:
            result = _lookup_usda(clean)
            if result:
                cache[clean] = asdict(result)
                _save_cache(cache)
                return result
        except Exception:
            pass

    return None


def _lookup_usda(query: str) -> MacroResult | None:
    """Query USDA FoodData Central API for ingredient macros."""
    import httpx

    # Map common Dutch ingredients to English for USDA search
    nl_to_en = {
        "kip": "chicken",
        "kipfilet": "chicken breast",
        "rundvlees": "beef",
        "rundergehakt": "ground beef",
        "zalm": "salmon",
        "tonijn": "tuna",
        "eieren": "egg",
        "melk": "milk",
        "kwark": "cottage cheese quark",
        "kaas": "cheese",
        "brood": "bread",
        "rijst": "rice",
        "pasta": "pasta",
        "aardappel": "potato",
        "groente": "vegetable",
        "olijfolie": "olive oil",
        "boter": "butter",
        "ui": "onion",
    }

    search_query = nl_to_en.get(query.split()[0], query)
    url = f"https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "query": search_query,
        "api_key": "DEMO_KEY",
        "pageSize": 1,
        "dataType": "Foundation,SR Legacy",
    }

    with httpx.Client(timeout=10) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    foods = data.get("foods", [])
    if not foods:
        return None

    food = foods[0]
    nutrients = {}
    for n in food.get("foodNutrients", []):
        name = n.get("nutrient", {}).get("name", "")
        val = n.get("amount", 0) or 0
        if "Energy" in name:
            nutrients["calories"] = float(val)
        elif "Protein" in name:
            nutrients["protein"] = float(val)
        elif "Carbohydrate, by difference" in name:
            nutrients["carbs"] = float(val)
        elif "Total lipid" in name or "Total fat" in name:
            nutrients["fat"] = float(val)

    if not nutrients:
        return None

    return MacroResult(
        calories=nutrients.get("calories", 0),
        protein=nutrients.get("protein", 0),
        carbs=nutrients.get("carbs", 0),
        fat=nutrients.get("fat", 0),
        source="usda",
    )


def compute_macros(
    amount: float,
    unit: str,
    macros_per_100g: dict[str, float],
) -> dict[str, float]:
    """Scale per-100g macros to the actual portion size."""
    factor = amount / 100.0 if unit in ("g", "ml") else 1.0
    return {
        "calories": round(macros_per_100g.get("calories", 0) * factor, 1),
        "protein": round(macros_per_100g.get("protein", 0) * factor, 1),
        "carbs": round(macros_per_100g.get("carbs", 0) * factor, 1),
        "fat": round(macros_per_100g.get("fat", 0) * factor, 1),
    }
