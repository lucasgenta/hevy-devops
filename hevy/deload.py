"""Fatigue and deload detection — analyzes training trends for overtraining signals."""

from __future__ import annotations

from typing import Any

import pandas as pd

from hevy.analysis import weekly_volume_trend, workouts_over_time


def deload_score(
    summary_df: pd.DataFrame,
    sets_df: pd.DataFrame,
) -> dict[str, Any]:
    """Calculate a deload recommendation score (0-100) and reasoning.

    Factors considered:
    - Volume plateau or decline (40% weight)
    - Frequency drop (25% weight)
    - Consecutive weeks without break (25% weight)
    - RPE trends if available (10% weight)

    Returns:
        Dict with 'score', 'needs_deload', 'factors', and 'recommendation'.
    """
    if summary_df.empty or len(summary_df) < 4:
        return {
            "score": 0,
            "needs_deload": False,
            "factors": [],
            "recommendation": "Not enough data to assess fatigue (need ≥4 weeks).",
            "weeks_since_deload": None,
        }

    factors: list[dict[str, Any]] = []
    score = 0.0

    # 1. Volume trend (40%)
    wvt = weekly_volume_trend(summary_df)
    if len(wvt) >= 4:
        recent_4 = wvt.tail(4)["total_volume_kg"].values
        vol_change = ((recent_4[-1] - recent_4[0]) / max(recent_4[0], 1)) * 100

        if vol_change < -15:
            score += 35
            factors.append({
                "factor": "volume_decline",
                "severity": "high",
                "detail": f"Volume dropped {vol_change:.0f}% over last 4 weeks.",
            })
        elif vol_change < -5:
            score += 20
            factors.append({
                "factor": "volume_decline",
                "severity": "medium",
                "detail": f"Volume slightly declining ({vol_change:.0f}% over 4 weeks).",
            })
        elif abs(vol_change) < 5:
            score += 10
            factors.append({
                "factor": "volume_plateau",
                "severity": "low",
                "detail": "Volume has plateaued over the last 4 weeks.",
            })
        else:
            factors.append({
                "factor": "volume_trend",
                "severity": "none",
                "detail": f"Volume is {vol_change:+.0f}% over last 4 weeks — looks healthy.",
            })
    else:
        score += 5  # small penalty for insufficient data

    # 2. Frequency drop (25%)
    wf = workouts_over_time(summary_df, period="W")
    if len(wf) >= 3:
        recent_freq = wf.tail(3)["workout_count"].values
        avg_freq = recent_freq.mean()
        if avg_freq < 2:
            score += 20
            factors.append({
                "factor": "low_frequency",
                "severity": "high",
                "detail": f"Averaging only {avg_freq:.1f} workouts/week recently.",
            })
        elif avg_freq < 3:
            score += 10
            factors.append({
                "factor": "low_frequency",
                "severity": "medium",
                "detail": f"Averaging {avg_freq:.1f} workouts/week.",
            })

        # Check if frequency dropped
        if len(recent_freq) >= 3:
            if recent_freq[-1] < recent_freq[0] * 0.7:
                score += 15
                factors.append({
                    "factor": "frequency_drop",
                    "severity": "medium",
                    "detail": "Workout frequency has dropped in recent weeks.",
                })
    else:
        score += 5

    # 3. Consecutive weeks without break (25%)
    total_weeks = len(wvt) if len(wvt) > 0 else 0
    if total_weeks >= 6:
        # Check for any week with 0 or 1 workouts (potential deload)
        if len(wf) > 0:
            low_weeks = (wf["workout_count"] <= 1).sum()
            if low_weeks == 0 and total_weeks >= 8:
                score += 20
                factors.append({
                    "factor": "no_deload",
                    "severity": "medium",
                    "detail": f"No deload/de-load week detected in {total_weeks} weeks of training.",
                })
            elif low_weeks >= 1 and total_weeks >= 8:
                factors.append({
                    "factor": "deload_taken",
                    "severity": "none",
                    "detail": f"Good — {low_weeks} low-volume week(s) detected as potential deloads.",
                })

    # 4. RPE trends if available (10%)
    if "rpe" in sets_df.columns and sets_df["rpe"].notna().any():
        recent_rpe = sets_df.dropna(subset=["rpe"]).tail(20)["rpe"]
        if not recent_rpe.empty:
            avg_rpe = recent_rpe.mean()
            if avg_rpe >= 9:
                score += 10
                factors.append({
                    "factor": "high_rpe",
                    "severity": "high",
                    "detail": f"Average RPE of {avg_rpe:.1f} in recent sets — high intensity.",
                })
            elif avg_rpe >= 8:
                score += 5
                factors.append({
                    "factor": "high_rpe",
                    "severity": "low",
                    "detail": f"Average RPE of {avg_rpe:.1f} — moderate intensity.",
                })

    # Calculate weeks since last deload
    weeks_since_deload = None
    if len(wf) > 0 and total_weeks >= 4:
        low_volume_weeks = wf[wf["workout_count"] <= 1]
        if not low_volume_weeks.empty:
            last_deload = low_volume_weeks["period"].max()
            last_deload_end = last_deload.end_time if hasattr(last_deload, 'end_time') else None
            if last_deload_end:
                weeks_since_deload = int(
                    (pd.Timestamp.now() - pd.Timestamp(last_deload_end)).days / 7
                )

    # Final score clamped 0-100
    score = min(max(round(score, 0), 0), 100)

    needs_deload = score >= 50
    if needs_deload:
        recommendation = (
            f"⚠️ **Deload recommended** (score: {score:.0f}/100). "
            "Consider taking a lighter week: reduce volume by 40-50%, "
            "keep intensity moderate, or take 4-5 days off."
        )
    elif score >= 30:
        recommendation = (
            f"🔶 **Monitor fatigue** (score: {score:.0f}/100). "
            "You're not in deload territory yet, but keep an eye on volume and frequency."
        )
    else:
        recommendation = (
            f"✅ **Training looks good** (score: {score:.0f}/100). "
            "Your volume and frequency trends are healthy."
        )

    return {
        "score": score,
        "needs_deload": needs_deload,
        "factors": factors,
        "recommendation": recommendation,
        "weeks_since_deload": weeks_since_deload,
        "total_weeks_tracked": total_weeks,
    }
