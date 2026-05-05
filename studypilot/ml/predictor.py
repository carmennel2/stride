"""Predict how many minutes a task will take.

Public entry point: `predict_minutes(task, user)` returning
`(minutes, model_version)`. Day 7 implements the heuristic table from
the spec; Day 8 layers on a per-user Ridge regression that takes over
once that user has 5+ completed tasks.
"""
from __future__ import annotations

# Floor and cap apply to every predictor. Clamping keeps downstream
# views (planner, dashboard) from rendering nonsense if a user puts in
# extreme inputs.
MIN_MINUTES = 15
MAX_MINUTES = 12 * 60


def _clamp(minutes: float) -> int:
    """Round to int and clamp into [MIN_MINUTES, MAX_MINUTES]."""
    return max(MIN_MINUTES, min(MAX_MINUTES, int(round(minutes))))


def _complexity_factor(complexity: int) -> float:
    """Scaling factor for size-driven types (Reading, Essay).

    At complexity=3 (the default) this is 1.15, so a "moderate"
    1500-word essay base of 450 min becomes 517 min — close to the
    spec's intent that complexity shifts the estimate without
    dominating the size signal.
    """
    return 0.7 + 0.15 * complexity


def heuristic_minutes(task) -> int:
    """Estimate minutes for the task using the spec's heuristic table.

    Reading and Essay use the size hints (pages/words) plus a
    complexity multiplier. Problem Set, Coding, Revision, and Other are
    flat bases scaled linearly by complexity. Anything missing a size
    hint when one is needed falls back to the smallest sensible value
    so we still produce a clamped, non-zero estimate.
    """
    type_name = task.task_type.name
    complexity = max(1, min(5, int(task.complexity or 3)))

    if type_name == "Reading":
        pages = max(1, int(task.target_pages or 1))
        return _clamp(3 * pages * _complexity_factor(complexity))

    if type_name == "Essay":
        words = max(100, int(task.target_words or 100))
        return _clamp(30 * (words / 100) * _complexity_factor(complexity))

    # Flat-base types — scaled linearly by complexity.
    base_by_type = {
        "Problem Set": 60,
        "Coding": 90,
        "Revision": 45,
        "Other": 60,
    }
    base = base_by_type.get(type_name, 60)
    return _clamp(base * complexity)


def predict_minutes(task, user) -> tuple[int, str]:
    """Return (minutes, model_version) for the given task.

    Day 7 always uses the heuristic. Day 8 will check the user's
    training-data size and either return a Ridge prediction or fall
    back here.
    """
    del user  # placeholder until Day 8
    return heuristic_minutes(task), "heuristic_v1"
