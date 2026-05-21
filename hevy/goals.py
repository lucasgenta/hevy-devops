"""Goal tracking — define training goals, track e1RM progression, project timelines."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from hevy.analysis import e1rm_progression

# Where goals are stored
_DEFAULT_GOALS_PATH = Path(__file__).resolve().parents[1] / "goals.json"


@dataclass
class TrainingGoal:
    """A strength or physique goal."""

    exercise: str
    target_weight_kg: float
    target_reps: int = 1
    target_date: str | None = None  # ISO date string
    notes: str = ""
    created_at: str = ""
    current_e1rm: float = 0.0
    projected_date: str | None = None
    on_track: bool = True


class GoalTracker:
    """Manage training goals and project achievement timelines.

    Usage::

        tracker = GoalTracker(sets_df)
        tracker.add_goal("Bench Press (Barbell)", 100.0, reps=1)
        tracker.check_progress()
        tracker.save()
        print(tracker.report())
    """

    def __init__(
        self,
        sets_df: pd.DataFrame,
        goals_path: str | Path | None = None,
    ) -> None:
        self._sets = sets_df
        self._path = Path(goals_path or _DEFAULT_GOALS_PATH)
        self._goals: list[TrainingGoal] = []
        self._load()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def add_goal(
        self,
        exercise: str,
        target_weight_kg: float,
        reps: int = 1,
        target_date: str | None = None,
        notes: str = "",
    ) -> TrainingGoal:
        """Add a new training goal."""
        goal = TrainingGoal(
            exercise=exercise,
            target_weight_kg=target_weight_kg,
            target_reps=reps,
            target_date=target_date,
            notes=notes,
            created_at=datetime.now().isoformat(),
        )
        self._goals.append(goal)
        return goal

    def remove_goal(self, exercise: str) -> bool:
        """Remove goals for an exercise."""
        before = len(self._goals)
        self._goals = [g for g in self._goals if g.exercise.lower() != exercise.lower()]
        return len(self._goals) < before

    def check_progress(self) -> list[TrainingGoal]:
        """Update e1RM and projected dates for all goals."""
        for goal in self._goals:
            e1rm = e1rm_progression(self._sets, goal.exercise)
            if not e1rm.empty:
                goal.current_e1rm = float(round(e1rm["e1rm"].iloc[-1], 1))
                goal.on_track = bool(goal.current_e1rm > 0)

                # Project when the goal will be reached
                goal.projected_date = self._project_date(e1rm, goal.target_weight_kg)
            else:
                goal.current_e1rm = 0.0
                goal.on_track = False
                goal.projected_date = None

        return self._goals

    def report(self) -> str:
        """Generate a human-readable progress report."""
        if not self._goals:
            return "No goals defined. Add some with `add_goal()`."

        lines = ["## 🎯 Goal Progress Report", ""]
        for goal in self._goals:
            status = "✅ ON TRACK" if goal.on_track else "⚠️ NEEDS WORK"
            progress = f"{goal.current_e1rm:.0f} / {goal.target_weight_kg} kg" if goal.current_e1rm else "No data yet"

            line = f"**{goal.exercise}**: {progress} ({status})"
            if goal.projected_date:
                line += f" → Projected: {goal.projected_date}"
            if goal.target_date:
                line += f" (Target: {goal.target_date})"
            lines.append(line)
            if goal.notes:
                lines.append(f"  > {goal.notes}")

        return "\n".join(lines)

    def save(self) -> None:
        """Persist goals to JSON file."""
        data = [asdict(g) for g in self._goals]
        self._path.write_text(json.dumps(data, indent=2))

    def list_goals(self) -> list[TrainingGoal]:
        """Return current goals (with progress checked)."""
        self.check_progress()
        return self._goals

    def to_dataframe(self) -> pd.DataFrame:
        """Return goals as a DataFrame."""
        self.check_progress()
        return pd.DataFrame([asdict(g) for g in self._goals])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            data = json.loads(self._path.read_text())
            self._goals = [TrainingGoal(**g) for g in data]

    @staticmethod
    def _project_date(
        e1rm_df: pd.DataFrame,
        target: float,
    ) -> str | None:
        """Estimate when the goal will be reached using linear projection."""
        if len(e1rm_df) < 2:
            return None

        # Use last few data points for trend
        recent = e1rm_df.tail(5)
        if len(recent) < 2:
            recent = e1rm_df

        values = recent["e1rm"].values
        dates = pd.to_datetime(recent["date"])

        if values[-1] >= target:
            return "ACHIEVED 🎉"

        # Simple linear projection
        x = (dates - dates.iloc[0]).dt.days.values.astype(float)
        y = values

        # Calculate slope (kg per day)
        n = len(x)
        if n < 2:
            return None
        slope = (n * (x * y).sum() - x.sum() * y.sum()) / (n * (x**2).sum() - x.sum()**2)

        if slope <= 0:
            return None  # Not progressing

        days_to_goal = (target - y[-1]) / slope
        if days_to_goal > 365 * 5:  # More than 5 years
            return None

        projected = dates.iloc[-1] + pd.Timedelta(days=days_to_goal)
        return projected.strftime("%b %d, %Y")
