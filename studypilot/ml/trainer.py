"""Train the per-user regression model.

One Ridge pipeline per user, pickled to <instance>/model_<user_id>.pkl.
We re-train on every task completion (Day 5/8 hook) — small training
sets, fit time is sub-millisecond, no need for incremental fitting.

The pipeline is the entire contract: load it, call .predict(...) on a
DataFrame produced by features.task_to_feature_frame(), and trust the
result (subject to the sanity guards in predictor.predict_minutes).
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path

import pandas as pd
from flask import current_app
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from studypilot.ml.features import (
    ALL_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    task_to_features,
)
from studypilot.models import Task

logger = logging.getLogger(__name__)

# Below this many usable training rows the regression isn't trustworthy
# and predictor.predict_minutes() falls back to the heuristic.
MIN_TRAINING_ROWS = 5


def model_path(user_id: int) -> Path:
    """Pickle path for a user's trained model."""
    return Path(current_app.instance_path) / f"model_{user_id}.pkl"


def _build_training_frame(user_id: int) -> pd.DataFrame:
    """Pull every "done" task with logged time and turn it into a row."""
    tasks = Task.query.filter_by(user_id=user_id, status="done").all()
    rows = []
    for task in tasks:
        actual = sum(s.duration_minutes for s in task.sessions)
        if actual <= 0:
            # Done but no sessions — no signal, would skew towards zero.
            continue
        rows.append({**task_to_features(task), "actual_minutes": actual})
    return pd.DataFrame(rows, columns=list(ALL_FEATURES) + ["actual_minutes"])


def _build_pipeline() -> Pipeline:
    """Construct the Ridge pipeline. Same shape used at train and predict."""
    pre = ColumnTransformer(
        transformers=[
            # handle_unknown="ignore" means a brand-new subject_id at
            # predict-time produces an all-zeros one-hot row instead of
            # crashing. Less accurate than retraining, but harmless.
            ("cat", OneHotEncoder(handle_unknown="ignore"),
             list(CATEGORICAL_FEATURES)),
            ("num", "passthrough", list(NUMERIC_FEATURES)),
        ]
    )
    return Pipeline([("pre", pre), ("ridge", Ridge(alpha=1.0))])


def train_model_for_user(user_id: int) -> Pipeline | None:
    """Train and pickle the user's model. Returns None if not enough data.

    Idempotent and safe to call from anywhere with an app context — used
    by the task-completion hook and the seed-demo CLI.
    """
    df = _build_training_frame(user_id)
    if len(df) < MIN_TRAINING_ROWS:
        return None

    X = df[list(ALL_FEATURES)]
    y = df["actual_minutes"]

    pipe = _build_pipeline()
    pipe.fit(X, y)

    path = model_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump(pipe, fh)

    logger.info("Trained Ridge model for user %s on %d rows.", user_id, len(df))
    return pipe


def load_model_for_user(user_id: int) -> Pipeline | None:
    """Return the pickled pipeline, or None if there isn't one yet.

    Wrapped in try/except because a corrupt or stale pickle (e.g. from
    a sklearn version mismatch) shouldn't take down the predict path —
    the caller will fall back to the heuristic.
    """
    path = model_path(user_id)
    if not path.exists():
        return None
    try:
        with path.open("rb") as fh:
            return pickle.load(fh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load model for user %s: %s", user_id, exc)
        return None
