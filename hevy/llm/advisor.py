"""Training advisor — analyzes your Hevy data and generates LLM-powered recommendations."""

from __future__ import annotations

from typing import Any

import pandas as pd

from hevy.analysis import (
    muscle_group_balance,
    muscle_head_balance,
    best_set_by_exercise,
    weekly_volume_trend,
    workouts_over_time,
)
from hevy.llm.providers import LLMProvider, LLMResponse
from hevy.llm.prompts import (
    COACH_SYSTEM_PROMPT,
    build_analysis_prompt,
    build_focus_prompt,
    format_routines_for_prompt,
)


class TrainingAdvisor:
    """Analyzes training data and queries an LLM for personalized recommendations.

    Usage::

        advisor = TrainingAdvisor(sets_df, summary_df, templates_df)
        response = advisor.analyze(goals="hypertrophy, focus on chest")
        print(response.content)
    """

    def __init__(
        self,
        sets_df: pd.DataFrame,
        summary_df: pd.DataFrame,
        templates_df: pd.DataFrame,
        measurements_df: pd.DataFrame | None = None,
        routines_df: pd.DataFrame | None = None,
    ) -> None:
        self._sets = sets_df
        self._summary = summary_df
        self._templates = templates_df
        self._measurements = measurements_df
        self._routines = routines_df

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def analyze(
        self,
        goals: str = "general fitness and hypertrophy",
        provider: LLMProvider | None = None,
    ) -> LLMResponse:
        """Get comprehensive training analysis from the LLM.

        Args:
            goals: Your training goals (e.g. "strength, hypertrophy, focus on chest").
            provider: LLMProvider instance. Creates a default Deepseek one if None.

        Returns:
            LLMResponse with the analysis content.
        """
        if provider is None:
            provider = LLMProvider("deepseek")

        stats = self._build_stats()
        muscle_bal = self._build_muscle_balance()
        head_bal = self._build_head_balance()
        trends = self._build_trends()

        routines_summary = self._format_routines()
        prompt = build_analysis_prompt(
            stats, muscle_bal, head_bal, trends, goals,
            routines_summary=routines_summary,
        )
        return provider.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=COACH_SYSTEM_PROMPT,
        )

    def focus_on(
        self,
        area: str,
        provider: LLMProvider | None = None,
    ) -> LLMResponse:
        """Get targeted advice for a specific muscle area."""
        if provider is None:
            provider = LLMProvider("deepseek")

        stats = self._build_stats()
        head_bal = self._build_head_balance()

        prompt = build_focus_prompt(area, stats, head_bal)
        return provider.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=COACH_SYSTEM_PROMPT,
        )

    def ask(
        self,
        question: str,
        provider: LLMProvider | None = None,
    ) -> LLMResponse:
        """Ask a free-form question about your training data."""
        if provider is None:
            provider = LLMProvider("deepseek")

        stats_summary = self._quick_stats_summary()

        context = (
            "Here is my training data summary:\n"
            f"{stats_summary}\n\n"
            f"My question is: {question}"
        )

        return provider.chat(
            messages=[{"role": "user", "content": context}],
            system_prompt=COACH_SYSTEM_PROMPT,
        )

    def get_snapshot(self) -> dict[str, Any]:
        """Return a plain dict snapshot of training stats (no LLM call)."""
        return {
            "stats": self._build_stats(),
            "muscle_balance": self._build_muscle_balance(),
            "head_balance": self._build_head_balance(),
            "trends": self._build_trends(),
            "routines": self._build_routines_summary(),
        }

    def _build_routines_summary(self) -> list[dict[str, Any]]:
        if self._routines is None or self._routines.empty:
            return []
        summary = []
        for title in sorted(self._routines["routine_title"].unique()):
            routine = self._routines[self._routines["routine_title"] == title]
            summary.append({
                "title": title,
                "exercises": routine["exercise_title"].unique().tolist(),
            })
        return summary

    # ------------------------------------------------------------------
    # Internal — data summarization
    # ------------------------------------------------------------------

    def _build_stats(self) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "workouts": len(self._summary),
            "total_sets": len(self._sets),
            "total_volume_kg": round(self._sets["volume_kg"].sum(), 0),
            "unique_exercises": self._sets["exercise_title"].nunique(),
        }

        if not self._summary.empty:
            stats["avg_duration_min"] = round(
                self._summary["duration_min"].mean(), 0
            )

        if not self._summary.empty and len(self._summary) > 1:
            date_range = (
                pd.to_datetime(self._summary["start_time"]).max()
                - pd.to_datetime(self._summary["start_time"]).min()
            )
            weeks = max(date_range.days / 7, 1)
            stats["avg_workouts_per_week"] = round(len(self._summary) / weeks, 1)
        else:
            stats["avg_workouts_per_week"] = "N/A"

        stats["exercise_templates_count"] = len(self._templates)

        return stats

    def _build_muscle_balance(self) -> list[dict[str, Any]]:
        if self._sets.empty or self._templates.empty:
            return []
        balance = muscle_group_balance(self._sets, self._templates)
        if balance.empty:
            return []
        return balance.to_dict(orient="records")

    def _build_head_balance(self) -> list[dict[str, Any]] | None:
        if "muscle_head_names" not in self._sets.columns:
            return None
        if self._sets.empty:
            return None
        balance = muscle_head_balance(self._sets)
        if balance.empty:
            return None
        return balance.to_dict(orient="records")

    def _build_trends(self) -> dict[str, Any] | None:
        if self._summary.empty or len(self._summary) < 4:
            return None

        trends: dict[str, Any] = {}

        wvt = weekly_volume_trend(self._summary)
        if not wvt.empty and len(wvt) > 1:
            trends["weekly_volume"] = round(wvt["total_volume_kg"].iloc[-1], 0)
            recent = wvt.tail(8)
            if len(recent) > 1:
                first_half = recent.head(len(recent) // 2)["total_volume_kg"].mean()
                second_half = recent.tail(len(recent) // 2)["total_volume_kg"].mean()
                if first_half > 0:
                    change = ((second_half - first_half) / first_half) * 100
                    direction = "increasing" if change > 5 else ("decreasing" if change < -5 else "stable")
                    trends["volume_trend"] = f"{direction} ({change:+.0f}% over last {len(recent)} weeks)"
                else:
                    trends["volume_trend"] = "stable (insufficient baseline)"
            else:
                trends["volume_trend"] = "not enough data"

        return trends

    def _format_routines(self) -> str | None:
        """Format selected routines for the prompt."""
        if self._routines is None or self._routines.empty:
            return None
        return format_routines_for_prompt(self._routines)

    def _quick_stats_summary(self) -> str:
        """Short one-line summary for free-form questions."""
        stats = self._build_stats()
        return (
            f"{stats['workouts']} workouts, {stats['total_sets']} sets, "
            f"{stats['total_volume_kg']:,.0f} kg total volume, "
            f"{stats['unique_exercises']} different exercises, "
            f"~{stats.get('avg_workouts_per_week', '?')} workouts/week"
        )
