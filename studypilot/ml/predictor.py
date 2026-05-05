"""Predict how many minutes a task will take.

Public entry point: `predict_minutes(task, user)` returning
`(minutes, model_version)`.

Layering, in priority order:
  1. Per-user Ridge regression (trained from that user's completed
     tasks; reloaded from instance/model_<user_id>.pkl).
  2. Heuristic from the spec table.

The regression's output is sanity-checked — if it's smaller than the
floor or more than 3x the heuristic, we discard it and fall back. That
guards against a brand-new model fitted on a tiny / oddly-shaped
training set producing nonsense.
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

# Floor and cap apply to every predictor.
MIN_MINUTES = 15
MAX_MINUTES = 12 * 60

# Regression output beyond REGRESSION_OVER_HEURISTIC * heuristic is
# treated as a sanity-check failure. Three was chosen as comfortably
# wide for a Ridge model that's just learned the user's typical scaling
# while still catching wild over-predictions.
REGRESSION_OVER_HEURISTIC = 3.0


def _clamp(minutes: float) -> int:
    """Round to int and clamp into [MIN_MINUTES, MAX_MINUTES]."""
    return max(MIN_MINUTES, min(MAX_MINUTES, int(round(minutes))))


def _complexity_factor(complexity: int) -> float:
    """Scaling factor for size-driven types (Reading, Essay)."""
    return 0.7 + 0.15 * complexity


def heuristic_minutes(task) -> int:
    """Estimate minutes for the task using the spec's heuristic table."""
    type_name = task.task_type.name
    complexity = max(1, min(5, int(task.complexity or 3)))

    if type_name == "Reading":
        pages = max(1, int(task.target_pages or 1))
        return _clamp(3 * pages * _complexity_factor(complexity))

    if type_name == "Essay":
        words = max(100, int(task.target_words or 100))
        return _clamp(30 * (words / 100) * _complexity_factor(complexity))

    base_by_type = {
        "Problem Set": 60,
        "Coding": 90,
        "Revision": 45,
        "Other": 60,
    }
    base = base_by_type.get(type_name, 60)
    return _clamp(base * complexity)


def _try_regression(task, user) -> int | None:
    """Return a clamped regression prediction, or None to skip.

    Returns None on every "fall back to heuristic" path — no model
    trained yet, prediction outside sanity bounds, NaN, or any exception
    while loading/predicting. The caller treats None as "use heuristic".
    """
    # Imported lazily so the heuristic-only code path doesn't pull
    # numpy/pandas/sklearn until they're actually needed (matters for
    # the very first heuristic-only request after a cold start).
    from studypilot.ml.features import task_to_feature_frame
    from studypilot.ml.trainer import load_model_for_user

    if user is None or not getattr(user, "id", None):
        return None

    pipe = load_model_for_user(user.id)
    if pipe is None:
        return None

    try:
        prediction = float(pipe.predict(task_to_feature_frame(task))[0])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Regression predict failed for user %s: %s", user.id, exc)
        return None

    if math.isnan(prediction) or math.isinf(prediction):
        return None

    heuristic = heuristic_minutes(task)
    # Floor/cap is enforced by the heuristic path too, so checking
    # against MIN_MINUTES picks up sub-floor predictions and the upper
    # bound catches "way larger than the heuristic" cases.
    if prediction < MIN_MINUTES:
        return None
    if prediction > heuristic * REGRESSION_OVER_HEURISTIC:
        return None

    return _clamp(prediction)


def predict_minutes(task, user) -> tuple[int, str]:
    """Return (minutes, model_version) for the given task.

    The regression takes priority once the user has 5+ usable training
    rows AND its prediction passes the sanity guards. Otherwise the
    heuristic answers.
    """
    regression = _try_regression(task, user)
    if regression is not None:
        return regression, "regression_v1"
    return heuristic_minutes(task), "heuristic_v1"
