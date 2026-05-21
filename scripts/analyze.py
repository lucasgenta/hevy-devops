#!/usr/bin/env python3
"""CLI for transforming raw Hevy data and computing training metrics.

Usage:
    python scripts/analyze.py                    # Full analysis → CSVs
    python scripts/analyze.py --output reports   # Custom output dir
    python scripts/analyze.py --muscle-heads     # Include specific muscle head analysis
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the project root is on sys.path
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from hevy.env import load_dotenv  # noqa: E402
load_dotenv()

import pandas as pd  # noqa: E402

from hevy.transform import (  # noqa: E402
    build_body_measurements_df,
    build_exercise_templates_df,
    build_routines_df,
    build_workout_sets_df,
    build_workout_summary_df,
)
from hevy.analysis import (  # noqa: E402
    best_set_by_exercise,
    best_weight_by_exercise,
    muscle_group_balance,
    muscle_head_balance,
    volume_by_exercise,
    volume_by_muscle_group,
    volume_by_muscle_head,
    weekly_volume_trend,
    workouts_over_time,
)
from hevy.anatomy import AnatomyMapper  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transform and analyze Hevy workout data.",
    )
    parser.add_argument(
        "--raw-dir",
        default="data/raw",
        help="Directory containing scraped JSON data (default: data/raw)",
    )
    parser.add_argument(
        "--output",
        default="reports",
        help="Directory for output CSV files (default: reports)",
    )
    parser.add_argument(
        "--muscle-heads",
        action="store_true",
        help="Include specific muscle head analysis (requires anatomy mapper)",
    )
    parser.add_argument(
        "--exercise-history",
        action="store_true",
        help="Include per-exercise history analysis (may take a while)",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 55)
    print("  Hevy Data Analysis Pipeline")
    print("=" * 55)

    # ---- Load data ----
    print("\n[1/4] Loading raw data...")
    mapper = AnatomyMapper() if args.muscle_heads else None
    sets_df = build_workout_sets_df(raw_dir=args.raw_dir, mapper=mapper)
    summary_df = build_workout_summary_df(raw_dir=args.raw_dir)
    templates_df = build_exercise_templates_df(raw_dir=args.raw_dir)
    measurements_df = build_body_measurements_df(raw_dir=args.raw_dir)
    routines_df = build_routines_df(raw_dir=args.raw_dir)

    print(f"  • {len(sets_df):,} individual sets across all workouts")
    print(f"  • {len(summary_df)} workouts")
    print(f"  • {len(templates_df)} exercise templates")
    print(f"  • {len(measurements_df)} body measurement entries")
    print(f"  • {len(routines_df)} routine entries")

    # ---- Transform output ----
    print("\n[2/4] Writing transformed data...")
    sets_df.to_csv(output_dir / "sets.csv", index=False)
    summary_df.to_csv(output_dir / "workouts.csv", index=False)
    templates_df.to_csv(output_dir / "exercise_templates.csv", index=False)
    measurements_df.to_csv(output_dir / "body_measurements.csv", index=False)
    routines_df.to_csv(output_dir / "routines.csv", index=False)
    print(f"  → {output_dir}/sets.csv ({len(sets_df)} rows)")
    print(f"  → {output_dir}/workouts.csv ({len(summary_df)} rows)")
    print(f"  → {output_dir}/exercise_templates.csv ({len(templates_df)} rows)")
    print(f"  → {output_dir}/body_measurements.csv ({len(measurements_df)} rows)")
    print(f"  → {output_dir}/routines.csv ({len(routines_df)} rows)")

    # ---- Analysis ----
    print("\n[3/4] Computing metrics...")

    if not sets_df.empty and not templates_df.empty:
        # Volume by exercise (monthly)
        vol_ex = volume_by_exercise(sets_df, period="M")
        vol_ex.to_csv(output_dir / "volume_by_exercise_monthly.csv", index=False)
        print(f"  → {output_dir}/volume_by_exercise_monthly.csv")

        # Volume by muscle group (monthly)
        vol_mg = volume_by_muscle_group(sets_df, templates_df, period="M")
        vol_mg.to_csv(output_dir / "volume_by_muscle_group_monthly.csv", index=False)
        print(f"  → {output_dir}/volume_by_muscle_group_monthly.csv")

        # Muscle group balance
        balance = muscle_group_balance(sets_df, templates_df)
        balance.to_csv(output_dir / "muscle_group_balance.csv", index=False)
        print(f"  → {output_dir}/muscle_group_balance.csv")
        _print_top_balances(balance)

        # PRs: best sets
        prs = best_set_by_exercise(sets_df)
        prs.to_csv(output_dir / "personal_records.csv", index=False)
        print(f"  → {output_dir}/personal_records.csv ({len(prs)} exercises)")

        # PRs: best weights
        best_w = best_weight_by_exercise(sets_df)
        best_w.to_csv(output_dir / "best_weights.csv", index=False)
        print(f"  → {output_dir}/best_weights.csv ({len(best_w)} exercises)")

        # Specific muscle head analysis
        if args.muscle_heads and "muscle_head_names" in sets_df.columns:
            vol_mh = volume_by_muscle_head(sets_df, period="M")
            vol_mh.to_csv(output_dir / "volume_by_muscle_head_monthly.csv", index=False)
            print(f"  → {output_dir}/volume_by_muscle_head_monthly.csv")

            head_balance = muscle_head_balance(sets_df)
            head_balance.to_csv(output_dir / "muscle_head_balance.csv", index=False)
            print(f"  → {output_dir}/muscle_head_balance.csv")
            _print_top_head_balances(head_balance)

    if not summary_df.empty:
        # Weekly volume trend
        wvt = weekly_volume_trend(summary_df)
        wvt.to_csv(output_dir / "weekly_volume_trend.csv", index=False)
        print(f"  → {output_dir}/weekly_volume_trend.csv")

        # Workout frequency
        wot = workouts_over_time(summary_df, period="W")
        wot.to_csv(output_dir / "workouts_per_week.csv", index=False)
        print(f"  → {output_dir}/workouts_per_week.csv")

    # ---- Summary ----
    print("\n[4/4] Summary stats:")
    if not sets_df.empty:
        total_vol = sets_df["volume_kg"].sum()
        print(f"  Total volume lifted: {total_vol:,.0f} kg")
        print(f"  Total sets logged: {len(sets_df)}")
    if not summary_df.empty:
        avg_dur = summary_df["duration_min"].mean()
        print(f"  Avg workout duration: {avg_dur:.0f} min" if pd.notna(avg_dur) else "")
        print(f"  Total workouts: {len(summary_df)}")

    print(f"\n✅ All reports written to {output_dir.resolve()}/")


def _print_top_balances(balance: pd.DataFrame) -> None:
    if balance.empty:
        return
    print("\n  Top muscle groups by volume:")
    for _, row in balance.head(8).iterrows():
        print(f"    {row['primary_muscle_group']:<20s} {row['percentage']:>5.1f}%")


def _print_top_head_balances(balance: pd.DataFrame) -> None:
    if balance.empty:
        return
    print("\n  Top specific muscle heads by volume:")
    for _, row in balance.head(12).iterrows():
        print(f"    {row['muscle_head']:<30s} {row['percentage']:>5.1f}%")


if __name__ == "__main__":
    main()
