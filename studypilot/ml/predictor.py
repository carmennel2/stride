"""Predict how many minutes a task will take.

Public entry point: `predict_minutes(task, user)` returning
`(minutes, model_version)`. Day 4 ships a stub that returns 60 for every
task. Day 7 replaces the body with the heuristic table from the spec;
Day 8 adds a Ridge regression that takes over once a user has 5+
completed tasks (with a sanity-guard fallback to the heuristic).
"""
from __future__ import annotations

# Floor and cap apply to every predictor — even the stub — so the rest of
# the app can rely on predicted_minutes being in a sane range.
MIN_MINUTES = 15
MAX_MINUTES = 12 * 60


def _clamp(minutes: float) -> int:
    """Round to int and clamp into the [MIN_MINUTES, MAX_MINUTES] range."""
    return max(MIN_MINUTES, min(MAX_MINUTES, int(round(minutes))))


def predict_minutes(task, user) -> tuple[int, str]:
    """Return (minutes, model_version) for the given task.

    The `user` argument is unused on Day 4 but stays in the signature
    because Day 8's regression looks up that user's training data and
    pickled model.
    """
    del user  # placeholder until Day 8
    return _clamp(60), "stub_v1"
