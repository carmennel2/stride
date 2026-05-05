"""Routes for the insights blueprint.

Day 11: layered on accuracy-over-time, per-subject averages, best study
day, and a current-streak counter on top of the Day 9 scatter +
summary.
"""
from collections import Counter
from datetime import date, timedelta

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from studypilot.models import Prediction, StudySession, Subject, Task

bp = Blueprint("insights", __name__, url_prefix="/insights")

WEEKDAY_LABELS: tuple[str, ...] = (
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
)


def _scored_predictions(user_id: int) -> list[Prediction]:
    """Predictions belonging to done tasks that have actual_minutes set."""
    return (
        Prediction.query.join(Task, Prediction.task_id == Task.id)
        .filter(Task.user_id == user_id)
        .filter(Prediction.actual_minutes.isnot(None))
        .order_by(Prediction.created_at.asc())
        .all()
    )


def _accuracy_summary(predictions: list[Prediction]) -> dict:
    """Mean abs error, signed bias, count, and per-version breakdown."""
    if not predictions:
        return {"count": 0, "mae": 0, "bias": 0, "by_version": {}}

    deltas = [p.actual_minutes - p.predicted_minutes for p in predictions]
    return {
        "count": len(predictions),
        "mae": round(sum(abs(d) for d in deltas) / len(deltas), 1),
        "bias": round(sum(deltas) / len(deltas), 1),
        "by_version": dict(Counter(p.model_version for p in predictions)),
    }


def _by_subject(user_id: int) -> list[dict]:
    """Average actual minutes per subject (done tasks only)."""
    subjects = Subject.query.filter_by(user_id=user_id).order_by(Subject.name).all()
    rows = []
    for subj in subjects:
        done_tasks = [t for t in subj.tasks if t.status == "done"]
        actuals = []
        for t in done_tasks:
            total = sum(s.duration_minutes for s in t.sessions)
            if total > 0:
                actuals.append(total)
        if not actuals:
            continue
        rows.append({
            "name": subj.name,
            "color": subj.color,
            "task_count": len(actuals),
            "avg_minutes": round(sum(actuals) / len(actuals), 1),
            "total_minutes": sum(actuals),
        })
    # Heaviest subject first — feels like the more useful sort for users.
    rows.sort(key=lambda r: -r["total_minutes"])
    return rows


def _best_weekday(user_id: int) -> dict | None:
    """Weekday on which the user logs the most minutes. None if no data."""
    sessions = StudySession.query.filter_by(user_id=user_id).all()
    if not sessions:
        return None
    minutes_per_day = [0] * 7
    for s in sessions:
        minutes_per_day[s.started_at.weekday()] += s.duration_minutes
    best = max(range(7), key=lambda i: minutes_per_day[i])
    if minutes_per_day[best] == 0:
        return None
    return {
        "label": WEEKDAY_LABELS[best],
        "minutes": minutes_per_day[best],
        "hours": round(minutes_per_day[best] / 60, 1),
    }


def _streak(user_id: int) -> int:
    """Number of consecutive days, ending today or yesterday, with a session.

    "Yesterday or today" lets the streak survive a user who hasn't
    studied yet today — they shouldn't see their streak reset every
    morning.
    """
    sessions = StudySession.query.filter_by(user_id=user_id).all()
    if not sessions:
        return 0
    days_with_sessions = {s.started_at.date() for s in sessions}
    today = date.today()
    cursor = today if today in days_with_sessions else today - timedelta(days=1)
    streak = 0
    while cursor in days_with_sessions:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _accuracy_over_time(predictions: list[Prediction]) -> list[dict]:
    """Time-series of signed delta (actual - predicted) per scored task.

    Each point is one task; x is the prediction's created_at, y is the
    delta in minutes. Used by the line chart so the user can spot
    whether they're getting better at estimating.
    """
    return [
        {
            "x": p.created_at.strftime("%Y-%m-%d"),
            "y": p.actual_minutes - p.predicted_minutes,
        }
        for p in predictions
    ]


@bp.route("/")
@login_required
def insights():
    """Render the insights page."""
    uid = current_user.id
    predictions = _scored_predictions(uid)
    summary = _accuracy_summary(predictions)

    scatter_points = [
        {"x": p.predicted_minutes, "y": p.actual_minutes}
        for p in predictions
    ]
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
        accuracy_series=_accuracy_over_time(predictions),
        by_subject=_by_subject(uid),
        best_weekday=_best_weekday(uid),
        streak=_streak(uid),
    )
