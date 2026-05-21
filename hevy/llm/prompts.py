"""Prompt templates for the training advisor.

Each template generates a structured analysis request for the LLM.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

COACH_SYSTEM_PROMPT = """You are an expert strength and hypertrophy coach with deep knowledge of exercise science, anatomy, and program design. Your specialty is analyzing training data to provide evidence-based, personalized recommendations.

Rules:
1. Base ALL recommendations on the provided data — never guess or assume.
2. Be specific: name exact exercises, muscle heads, volume ranges, and rep schemes.
3. Prioritize fixing imbalances and weak points over maintaining strengths.
4. Suggest actionable changes the user can implement next workout/week.
5. Format your response in clear sections with bullet points for readability.
6. If the user has goals (strength, hypertrophy, recomp, endurance), tailor advice accordingly.
7. Keep advice practical — 1-3 key changes are better than a full overhaul.
8. NEVER recommend anything unsafe or unsupported by evidence."""

# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def format_routines_for_prompt(routines_df: pd.DataFrame | None = None) -> str:
    """Format routines data as a readable text block for the LLM prompt."""
    if routines_df is None or routines_df.empty:
        return "- No routine data available."

    lines: list[str] = []
    for title in sorted(routines_df["routine_title"].unique()):
        routine = routines_df[routines_df["routine_title"] == title]
        lines.append(f"- **{title}**")
        for ex_title in routine["exercise_title"].unique():
            ex_rows = routine[routine["exercise_title"] == ex_title]
            sets_summary = _summarize_sets(ex_rows)
            lines.append(f"  • {ex_title} {sets_summary}")
        lines.append("")

    return "\n".join(lines).strip()


def _summarize_sets(ex_rows: pd.DataFrame) -> str:
    """Summarize a routine's sets for an exercise."""
    set_types = ex_rows["set_type"].unique()
    has_reps = ex_rows["reps"].notna().any()
    has_rep_range = ex_rows["rep_range_start"].notna().any()

    parts = []
    if has_rep_range:
        valid = ex_rows.dropna(subset=["rep_range_start", "rep_range_end"])
        if not valid.empty:
            start = int(valid["rep_range_start"].iloc[0])
            end = int(valid["rep_range_end"].iloc[0])
            parts.append(f"{start}-{end} reps")
    elif has_reps:
        valid = ex_rows.dropna(subset=["reps"])
        if not valid.empty:
            reps = int(valid["reps"].iloc[0])
            parts.append(f"{reps} reps")

    if "warmup" in set_types:
        parts.append("warmup sets included")

    n_sets = len(ex_rows)
    parts.append(f"{n_sets} set{'s' if n_sets > 1 else ''}")

    return f"({' · '.join(parts)})" if parts else ""


def build_analysis_prompt(
    stats: dict[str, Any],
    muscle_balance: list[dict[str, Any]],
    head_balance: list[dict[str, Any]] | None = None,
    recent_trends: dict[str, Any] | None = None,
    goals: str = "general fitness and hypertrophy",
    routines_summary: str | None = None,
) -> str:
    """Build a prompt for comprehensive training analysis.

    Args:
        stats: Overview stats (workouts, volume, frequency, avg duration, etc.)
        muscle_balance: List of {primary_muscle_group, percentage} dicts.
        head_balance: Optional list of {muscle_head, percentage} dicts.
        recent_trends: Optional dict with recent volume/frequency trends.
        goals: User's stated training goals.
    """
    sections = []

    # Header
    sections.append(f"## Training Overview")
    sections.append(f"- Total workouts: {stats.get('workouts', 'N/A')}")
    sections.append(f"- Total sets: {stats.get('total_sets', 'N/A')}")
    sections.append(f"- Total volume: {stats.get('total_volume_kg', 'N/A'):,} kg")
    sections.append(f"- Unique exercises: {stats.get('unique_exercises', 'N/A')}")
    sections.append(f"- Avg workout duration: {stats.get('avg_duration_min', 'N/A')} min")
    sections.append(f"- Training frequency: ~{stats.get('avg_workouts_per_week', 'N/A')} workouts/week")

    # Muscle group balance
    sections.append(f"\n## Muscle Group Volume Distribution (%)")
    if muscle_balance:
        for m in muscle_balance:
            sections.append(f"- {m['primary_muscle_group']}: {m['percentage']:.1f}%")
    else:
        sections.append("- No muscle balance data available.")

    # Specific muscle head balance
    if head_balance:
        sections.append(f"\n## Specific Muscle Head Volume Distribution (%)")
        sections.append("(Volume is split among all heads targeted by each exercise)")
        top_heads = sorted(head_balance, key=lambda x: x["percentage"], reverse=True)[:20]
        for h in top_heads:
            sections.append(f"- {h['muscle_head']}: {h['percentage']:.1f}%")

    # Trends
    if recent_trends:
        sections.append(f"\n## Recent Trends")
        if "weekly_volume" in recent_trends:
            sections.append(f"- Current weekly volume: ~{recent_trends['weekly_volume']:,.0f} kg")
        if "volume_trend" in recent_trends:
            sections.append(f"- Volume trend (last 8 weeks): {recent_trends['volume_trend']}")

    # Exercise templates available
    exercises_count = stats.get("exercise_templates_count", 0)
    sections.append(f"\n## Available Exercises")
    sections.append(f"- Exercise library: {exercises_count} templates")

    # User's routines
    if routines_summary:
        sections.append(f"\n## Current Routines / Split")
        sections.append(routines_summary)
        sections.append("")

    # User goal
    sections.append(f"\n## User Goal")
    sections.append(goals)

    # Request
    sections.append(f"\n## Requested Analysis")
    sections.append("Based on the data above, please provide:")

    analysis_points = [
        "Overall training assessment — what's working and what isn't",
        "Muscle group balance analysis — identify over/under-trained groups",
        "Specific muscle head imbalances — point out any heads lagging behind",
        "Exercise selection gaps — suggest 2-3 exercises missing from the routine",
        "Volume recommendations — which muscle groups need more/less volume",
        "Training split suggestion — optimal split based on frequency and goals",
        "Progression assessment — is volume, frequency, or intensity trending well?",
        "Top 3 actionable recommendations the user should implement immediately",
    ]
    for pt in analysis_points:
        sections.append(f"  • {pt}")

    return "\n".join(sections)


def build_focus_prompt(
    focus_area: str,
    stats: dict[str, Any],
    head_balance: list[dict[str, Any]] | None = None,
) -> str:
    """Build a prompt focused on a specific muscle area.

    Args:
        focus_area: e.g. "triceps", "upper chest", "posterior delts", "overall symmetry"
        stats: Overview stats dict.
        head_balance: Optional specific head balance data.
    """
    sections = [
        f"I want to focus on improving my **{focus_area}**.",
        "",
        "## Current Training Stats",
        f"- Total workouts: {stats.get('workouts', 'N/A')}",
        f"- Total volume: {stats.get('total_volume_kg', 'N/A'):,} kg",
    ]

    if head_balance:
        sections.append("\n## Current Muscle Head Volume Distribution")
        top = sorted(head_balance, key=lambda x: x["percentage"], reverse=True)[:15]
        for h in top:
            sections.append(f"- {h['muscle_head']}: {h['percentage']:.1f}%")

    sections.extend([
        "",
        "## Request",
        f"Give me a detailed plan to improve my {focus_area}. Include:",
        "  • 3-5 best exercises for targeting this area with explanation of WHY each works",
        "  • Recommended sets, reps, and frequency per week",
        "  • How to program these into my existing split",
        "  • Common mistakes to avoid",
        "  • How to track progress specifically for this area",
    ])

    return "\n".join(sections)


def build_empty_prompt(goals: str = "general fitness") -> str:
    """Fallback prompt when there's not enough training data."""
    return (
        f"I'm starting my fitness journey and my goal is {goals}. "
        "I don't have training data yet. Can you help me design a beginner-friendly "
        "workout program? Include:\n"
        "  • Recommended split (full body vs PPL vs upper/lower)\n"
        "  • Key exercises to start with\n"
        "  • Sets, reps, and progression scheme\n"
        "  • How to structure my week"
    )
