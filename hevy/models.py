"""Dataclass models representing Hevy API response shapes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Set:
    """A single set within an exercise."""

    index: int
    type: str  # normal, warmup, dropset, failure
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None
    rpe: float | None = None
    custom_metric: float | None = None


@dataclass
class Exercise:
    """An exercise performed during a workout."""

    index: int
    title: str
    exercise_template_id: str
    notes: str = ""
    supersets_id: int | None = None
    sets: list[Set] = field(default_factory=list)


@dataclass
class Workout:
    """A completed workout."""

    id: str
    title: str
    start_time: str
    end_time: str
    created_at: str
    updated_at: str
    description: str = ""
    routine_id: str | None = None
    exercises: list[Exercise] = field(default_factory=list)


@dataclass
class RoutineSet:
    """A set template within a routine."""

    index: int
    type: str
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None
    rpe: float | None = None
    custom_metric: float | None = None
    rep_range: dict | None = None


@dataclass
class RoutineExercise:
    """An exercise template within a routine."""

    index: int
    title: str
    exercise_template_id: str
    notes: str = ""
    supersets_id: int | None = None
    rest_seconds: int | None = None
    sets: list[RoutineSet] = field(default_factory=list)


@dataclass
class Routine:
    """A routine (workout template)."""

    id: str
    title: str
    created_at: str
    updated_at: str
    folder_id: int | None = None
    exercises: list[RoutineExercise] = field(default_factory=list)


@dataclass
class ExerciseTemplate:
    """An exercise template definition."""

    id: str
    title: str
    type: str
    primary_muscle_group: str
    secondary_muscle_groups: list[str] = field(default_factory=list)
    is_custom: bool = False


@dataclass
class BodyMeasurement:
    """Body measurements for a given date."""

    date: str  # YYYY-MM-DD
    weight_kg: float | None = None
    lean_mass_kg: float | None = None
    fat_percent: float | None = None
    neck_cm: float | None = None
    shoulder_cm: float | None = None
    chest_cm: float | None = None
    left_bicep_cm: float | None = None
    right_bicep_cm: float | None = None
    left_forearm_cm: float | None = None
    right_forearm_cm: float | None = None
    abdomen: float | None = None
    waist: float | None = None
    hips: float | None = None
    left_thigh: float | None = None
    right_thigh: float | None = None
    left_calf: float | None = None
    right_calf: float | None = None


@dataclass
class UserInfo:
    """Authenticated user profile info."""

    id: str
    name: str
    url: str


# Mapping from API JSON keys to dataclass types for deserialization
MODEL_REGISTRY: dict[str, type] = {
    "Workout": Workout,
    "Exercise": Exercise,
    "Set": Set,
    "Routine": Routine,
    "ExerciseTemplate": ExerciseTemplate,
    "BodyMeasurement": BodyMeasurement,
    "UserInfo": UserInfo,
}


def dict_to_dataclass(data: dict, model: type) -> Any:
    """Convert a raw dict to the corresponding dataclass instance."""
    if model is Workout:
        exercises = [dict_to_dataclass(e, Exercise) for e in data.get("exercises", [])]
        return Workout(**{**data, "exercises": exercises})

    if model is Exercise:
        sets = [dict_to_dataclass(s, Set) for s in data.get("sets", [])]
        return Exercise(**{**data, "sets": sets})

    if model is Routine:
        exercises = [dict_to_dataclass(e, RoutineExercise) for e in data.get("exercises", [])]
        return Routine(**{**data, "exercises": exercises})

    if model is RoutineExercise:
        sets = [dict_to_dataclass(s, RoutineSet) for s in data.get("sets", [])]
        return RoutineExercise(**{**data, "sets": sets})

    if model is BodyMeasurement:
        return BodyMeasurement(**data)

    if model is UserInfo:
        return UserInfo(**data)

    if model is ExerciseTemplate:
        return ExerciseTemplate(**data)

    return model(**data)
