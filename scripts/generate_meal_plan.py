#!/usr/bin/env python3
"""Generate a verified weekly meal plan with accurate macros.

Usage:
    .venv/bin/python scripts/generate_meal_plan.py
    .venv/bin/python scripts/generate_meal_plan.py --push-asana
    .venv/bin/python scripts/generate_meal_plan.py --target-calories 2000 --target-protein 160
    .venv/bin/python scripts/generate_meal_plan.py --push-asana --output my-plan.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nutrition.meal_planner import VerifiedMealPlanner, RecipeDatabase


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a verified-macro weekly meal plan",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                         Generate and print a plan
  %(prog)s --push-asana            Generate + push to Asana
  %(prog)s --target-calories 2000  Custom calorie target
        """,
    )
    parser.add_argument(
        "--push-asana",
        action="store_true",
        help="Push the shopping list to Asana",
    )
    parser.add_argument(
        "--target-calories",
        type=int,
        default=2200,
        help="Daily calorie target (default: 2200)",
    )
    parser.add_argument(
        "--target-protein",
        type=float,
        default=170,
        help="Daily protein target in grams (default: 170)",
    )
    parser.add_argument(
        "--target-fat",
        type=float,
        default=60,
        help="Daily fat target in grams (default: 60)",
    )
    parser.add_argument(
        "--target-carbs",
        type=float,
        default=245,
        help="Daily carbs target in grams (default: 245)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="",
        help="Start date (ISO format, e.g. 2026-05-18). Defaults to next Monday.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Save the plan as JSON to this file path",
    )

    args = parser.parse_args()

    # Resolve start date
    if args.start_date:
        try:
            start = date.fromisoformat(args.start_date)
        except ValueError:
            print(f"Error: Invalid date format: {args.start_date}. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        # Default: next Monday
        today = date.today()
        start = today + timedelta(days=(7 - today.weekday()) % 7)

    # Output path
    output_path = None
    if args.output:
        output_path = Path(args.output)
    else:
        # Default: data/meal-plans/{week-starting}.json
        output_path = Path(__file__).resolve().parent.parent / "data" / "meal-plans" / f"{start.isoformat()}.json"

    # Load recipe DB
    print("📖 Loading recipe database...", file=sys.stderr)
    db = RecipeDatabase()
    stats = db.stats()
    total = sum(stats.values())
    print(f"   {total} recipes loaded:", file=sys.stderr)
    for mt, count in stats.items():
        print(f"     - {mt}: {count}", file=sys.stderr)
    print(file=sys.stderr)

    # Generate plan
    print(f"🎯 Generating weekly plan starting {start}...", file=sys.stderr)
    print(f"   Targets: {args.target_calories} kcal, {args.target_protein}g P, {args.target_carbs}g C, {args.target_fat}g F", file=sys.stderr)
    print(file=sys.stderr)

    planner = VerifiedMealPlanner(recipe_db=db)
    plan = planner.generate_weekly_plan(
        target_calories=args.target_calories,
        target_protein=args.target_protein,
        target_fat=args.target_fat,
        target_carbs=args.target_carbs,
        start_date=start,
    )

    # Print plan
    print(planner.format_plan_text(plan))

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(planner.to_dict(plan), indent=2, ensure_ascii=False))
    print(f"📁 Plan saved to: {output_path}", file=sys.stderr)

    # Push to Asana
    if args.push_asana:
        print("📋 Pushing shopping list to Asana...", file=sys.stderr)
        created = planner.push_to_asana(plan.shopping_list)
        if created:
            print(f"   ✅ {created} items added to shopping list!", file=sys.stderr)
        else:
            print("   ⚠️  No new items added (already on list or Asana not configured)", file=sys.stderr)

    # Summary
    avg_cal = plan.totals.calories / 7
    avg_prot = plan.totals.protein / 7
    avg_carbs = plan.totals.carbs / 7
    avg_fat = plan.totals.fat / 7
    print(f"📊 Weekly average: {avg_cal:.0f} kcal/day | P{avg_prot:.0f}g | C{avg_carbs:.0f}g | F{avg_fat:.0f}g", file=sys.stderr)


if __name__ == "__main__":
    main()
