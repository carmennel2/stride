"""Dashboard routes."""
from collections import defaultdict
from datetime import date, timedelta

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from stride.models import StudySession, Subject, Task

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

WEEKDAY_LABELS: tuple[str, ...] = (
    "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"
)


def _kpis(user_id: int) -> dict:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    sessions = StudySession.query.filter_by(user_id=user_id).all()
    total_minutes = sum(s.duration_minutes for s in sessions)
    minutes_this_week = sum(
        s.duration_minutes for s in sessions
        if s.started_at.date() >= week_start
    )

    tasks_pending = Task.query.filter_by(
        user_id=user_id, status="pending"
    ).count() + Task.query.filter_by(
        user_id=user_id, status="in_progress"
    ).count()
    tasks_done = Task.query.filter_by(user_id=user_id, status="done").count()

    return {
        "total_hours": round(total_minutes / 60, 1),
        "hours_this_week": round(minutes_this_week / 60, 1),
        "tasks_pending": tasks_pending,
        "tasks_done": tasks_done,
    }


def _by_subject(user_id: int) -> tuple[list[str], list[float], list[str]]:
    subjects = Subject.query.filter_by(user_id=user_id).order_by(Subject.name).all()
    sessions = StudySession.query.filter_by(user_id=user_id).all()

    minutes_by_subject: dict[int, int] = defaultdict(int)
    for s in sessions:
        minutes_by_subject[s.task.subject_id] += s.duration_minutes

    labels, hours, colors = [], [], []
    for subj in subjects:
        if minutes_by_subject[subj.id] == 0:
            continue
        labels.append(subj.name)
        hours.append(round(minutes_by_subject[subj.id] / 60, 2))
        colors.append(subj.color)
    return labels, hours, colors


def _by_weekday(user_id: int) -> list[float]:
    sessions = StudySession.query.filter_by(user_id=user_id).all()
    minutes = [0] * 7
    for s in sessions:
        minutes[s.started_at.weekday()] += s.duration_minutes
    return [round(m / 60, 2) for m in minutes]


def _due_soon(user_id: int, days: int = 7) -> list[Task]:
    today = date.today()
    cutoff = today + timedelta(days=days)
    return (
        Task.query.filter_by(user_id=user_id)
        .filter(Task.status != "done")
        .filter(Task.due_date <= cutoff)
        .order_by(Task.due_date.asc())
        .all()
    )


@bp.route("/")
@login_required
def dashboard():
    uid = current_user.id
    kpis = _kpis(uid)
    subj_labels, subj_hours, subj_colors = _by_subject(uid)
    weekday_hours = _by_weekday(uid)
    due_soon = _due_soon(uid)

    today = date.today()
    notify_targets = [
        {
            "id": t.id,
            "title": t.title,
            "subject": t.subject.name,
            "due_label": (
                "today" if t.due_date == today
                else "tomorrow" if t.due_date == today + timedelta(days=1)
                else f"in {(t.due_date - today).days} days"
            ),
        }
        for t in due_soon
        if t.due_date <= today + timedelta(days=1)
    ]

    return render_template(
        "dashboard/dashboard.html",
        kpis=kpis,
        subj_labels=subj_labels,
        subj_hours=subj_hours,
        subj_colors=subj_colors,
        weekday_labels=list(WEEKDAY_LABELS),
        weekday_hours=weekday_hours,
        due_soon=due_soon,
        notify_targets=notify_targets,
    )
