"""Feature extraction for the per-user regression model.

Same features come out of `task_to_features` whether the row is being
used for training or prediction — that's the contract sklearn pipelines
need (the ColumnTransformer in trainer.py expects identically-shaped
input on fit and predict).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

# Categorical features get one-hot encoded by trainer.py; numeric
# features pass through. Listing them here keeps the trainer and the
# predictor in sync without either one growing a hidden assumption.
CATEGORICAL_FEATURES: tuple[str, ...] = ("subject_id", "type_id")
NUMERIC_FEATURES: tuple[str, ...] = (
    "complexity",
    "target_words",
    "target_pages",
    "description_word_count",
    "days_until_due",
)
ALL_FEATURES: tuple[str, ...] = CATEGORICAL_FEATURES + NUMERIC_FEATURES


def task_to_features(task) -> dict[str, Any]:
    """Build the feature dict for a single task.

    Nullable size hints (target_words, target_pages) become 0 — that's
    what the heuristic does too, so the regression learns the same
    "missing means none" semantics. days_until_due is computed at
    creation time, not now, so re-prediction near the deadline doesn't
    suddenly drop the feature to zero.
    """
    description = task.description or ""
    days_until_due = max(
        0, (task.due_date - task.created_at.date()).days
    )
    return {
        "subject_id": int(task.subject_id),
        "type_id": int(task.type_id),
        "complexity": int(task.complexity or 3),
        "target_words": int(task.target_words or 0),
        "target_pages": int(task.target_pages or 0),
        "description_word_count": len(description.split()),
        "days_until_due": int(days_until_due),
    }


def task_to_feature_frame(task) -> pd.DataFrame:
    """Wrap task_to_features() as a 1-row DataFrame for pipe.predict()."""
    return pd.DataFrame([task_to_features(task)])
