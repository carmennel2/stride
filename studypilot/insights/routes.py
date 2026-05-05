"""Routes for the insights blueprint.

Day 9: summary accuracy stats and predicted-vs-actual scatter. Day 11
adds accuracy-over-time, per-subject averages, best study day, streak.
"""
from collections import Counter

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from studypilot.models import Prediction, Task

bp = Blueprint("insights", __name__, url_prefix="/insights")


def _scored_predictions(user_id: int) -> list[Prediction]:
    """Predictions belonging to done tasks that have an actual_minutes set."""
    return (
        Prediction.query.join(Task, Prediction.task_id == Task.id)
        .filter(Task.user_id == user_id)
        .filter(Prediction.actual_minutes.isnot(None))
        .order_by(Prediction.created_at.asc())
        .all()
    )


def _accuracy_summary(predictions: list[Prediction]) -> dict:
    """Mean abs error, mean signed error, count, and per-version breakdown."""
    if not predictions:
        return {
            "count": 0, "mae": 0, "bias": 0, "by_version": {},
        }

    deltas = [p.actual_minutes - p.predicted_minutes for p in predictions]
    mae = sum(abs(d) for d in deltas) / len(deltas)
    bias = sum(deltas) / len(deltas)
    by_version = Counter(p.model_version for p in predictions)

    return {
        "count": len(predictions),
        "mae": round(mae, 1),
        "bias": round(bias, 1),
        "by_version": dict(by_version),
    }


@bp.route("/")
@login_required
def insights():
    """Render the insights page with the data Day 9 provides."""
    predictions = _scored_predictions(current_user.id)
    summary = _accuracy_summary(predictions)

    # Scatter data: predicted (x) vs actual (y). Chart.js scatter expects
    # a list of {x, y} points.
    scatter_points = [
        {"x": p.predicted_minutes, "y": p.actual_minutes}
        for p in predictions
    ]
    # Diagonal reference line: y = x — when prediction equals actual.
    if scatter_points:
        max_axis = max(
            max(pt["x"] for pt in scatter_points),
            max(pt["y"] for pt in scatter_points),
        )
    else:
        max_axis = 60

    return render_template(
        "insights/insights.html",
        summary=summary,
        scatter_points=scatter_points,
        max_axis=max_axis,
    )
