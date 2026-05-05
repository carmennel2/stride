"""Routes for the planner blueprint.

Algorithm: each open task is broken into equal daily slices from today
through its due date (inclusive). Slices already covered by logged
sessions are subtracted first, so a task that's halfway done only
schedules the remaining half. Overdue tasks collapse onto today.
"""
from collections import defaultdict
from datetime import date, timedelta

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from studypilot.models import Task

bp = Blueprint("planner", __name__, url_prefix="/planner")

# How far ahead the planner shows. Two weeks is enough to plan around
# essay deadlines without becoming overwhelming, and matches the spec.
PLANNER_HORIZON_DAYS = 14


def _build_plan(user_id: int, today: date, horizon_days: int) -> dict:
    """Build the planner data structure.

    Returns a dict with `days` (a list of per-day buckets, each with the
    date, total minutes, and contributing tasks) and `summary` (totals).
    Pure function — easy to unit-test if we ever want to.
    """
    horizon_end = today + timedelta(days=horizon_days)

    open_tasks = (
        Task.query.filter_by(user_id=user_id)
        .filter(Task.status != "done")
        .filter(Task.due_date <= horizon_end)
        .order_by(Task.due_date.asc())
        .all()
    )

    # day -> list of {"task": ..., "minutes": ...}
    by_day: dict[date, list[dict]] = defaultdict(list)

    for task in open_tasks:
        logged = sum(s.duration_minutes for s in task.sessions)
        remaining = max(0, task.predicted_minutes - logged)
        if remaining <= 0:
            continue

        # First scheduled day is today (even if overdue — we can't go back).
        # Last scheduled day is the due date or the horizon end, whichever
        # comes first.
        first_day = today
        last_day = min(max(task.due_date, today), horizon_end)
        days_count = (last_day - first_day).days + 1
        slice_minutes = max(1, round(remaining / days_count))

        # Iterate through the date range inclusively.
        current = first_day
        while current <= last_day:
            by_day[current].append({"task": task, "minutes": slice_minutes})
            current += timedelta(days=1)

    days = []
    total_minutes = 0
    for offset in range(horizon_days + 1):
        d = today + timedelta(days=offset)
        bucket = by_day.get(d, [])
        day_total = sum(slot["minutes"] for slot in bucket)
        total_minutes += day_total
        # Key is "slots" not "items" — Jinja `day.items` would resolve to
        # the dict.items method instead of our value.
        days.append({
            "date": d,
            "total_minutes": day_total,
            "slots": bucket,
        })

    return {
        "days": days,
        "summary": {
            "open_task_count": len([t for t in open_tasks
                                    if max(0, t.predicted_minutes - sum(
                                        s.duration_minutes for s in t.sessions
                                    )) > 0]),
            "total_minutes": total_minutes,
            "horizon_days": horizon_days,
        },
    }


@bp.route("/")
@login_required
def planner():
    """Render the two-week study plan for the current user."""
    plan = _build_plan(current_user.id, date.today(), PLANNER_HORIZON_DAYS)
    return render_template("planner/planner.html", plan=plan)
