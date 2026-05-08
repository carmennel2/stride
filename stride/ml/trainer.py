"""Train and load the per-user Ridge regression."""
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

from stride.ml.features import (
    ALL_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    task_to_features,
)
from stride.models import Task

logger = logging.getLogger(__name__)

MIN_TRAINING_ROWS = 5


def model_path(user_id: int) -> Path:
    return Path(current_app.instance_path) / f"model_{user_id}.pkl"


def _build_training_frame(user_id: int) -> pd.DataFrame:
    tasks = Task.query.filter_by(user_id=user_id, status="done").all()
    rows = []
    for task in tasks:
        actual = sum(s.duration_minutes for s in task.sessions)
        if actual <= 0:
            continue
        rows.append({**task_to_features(task), "actual_minutes": actual})
    return pd.DataFrame(rows, columns=list(ALL_FEATURES) + ["actual_minutes"])


def _build_pipeline() -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            # handle_unknown="ignore" so a brand-new subject_id at predict
            # time doesn't crash — produces an all-zeros one-hot row instead.
            ("cat", OneHotEncoder(handle_unknown="ignore"),
             list(CATEGORICAL_FEATURES)),
            ("num", "passthrough", list(NUMERIC_FEATURES)),
        ]
    )
    return Pipeline([("pre", pre), ("ridge", Ridge(alpha=1.0))])


def train_model_for_user(user_id: int) -> Pipeline | None:
    """Fit and pickle the model. Returns None if there's not enough data."""
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
    path = model_path(user_id)
    if not path.exists():
        return None
    try:
        with path.open("rb") as fh:
            return pickle.load(fh)
    except Exception as exc:  # noqa: BLE001
        # Corrupt or version-mismatched pickle — fall back to heuristic.
        logger.warning("Failed to load model for user %s: %s", user_id, exc)
        return None
