"""Two-layer time predictor: Ridge regression with heuristic fallback."""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

MIN_MINUTES = 15
MAX_MINUTES = 12 * 60
REGRESSION_OVER_HEURISTIC = 3.0


def _clamp(minutes: float) -> int:
    return max(MIN_MINUTES, min(MAX_MINUTES, int(round(minutes))))


def _complexity_factor(complexity: int) -> float:
    return 0.7 + 0.15 * complexity


def heuristic_minutes(task) -> int:
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
    """Return a regression prediction, or None to fall back to the heuristic."""
    # Lazy import — heuristic-only path shouldn't pull pandas/numpy/sklearn.
    from stride.ml.features import task_to_feature_frame
    from stride.ml.trainer import load_model_for_user

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
    if prediction < MIN_MINUTES:
        return None
    if prediction > heuristic * REGRESSION_OVER_HEURISTIC:
        return None

    return _clamp(prediction)


def predict_minutes(task, user) -> tuple[int, str]:
    regression = _try_regression(task, user)
    if regression is not None:
        return regression, "regression_v1"
    return heuristic_minutes(task), "heuristic_v1"
