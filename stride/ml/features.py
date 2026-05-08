"""Feature extraction for the regression model."""
from __future__ import annotations

from typing import Any

import pandas as pd

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
    description = task.description or ""
    # Computed at task-creation time; re-prediction near the deadline
    # mustn't drop this feature to zero.
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
    return pd.DataFrame([task_to_features(task)])
