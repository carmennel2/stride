"""Calendar routes — month grid of tasks by due date."""
import calendar as _calendar
from collections import defaultdict
from datetime import date

from flask import Blueprint, abort, render_template, url_for
from flask_login import current_user, login_required

from stride.models import Task

bp = Blueprint("calendar", __name__, url_prefix="/calendar")

WEEKDAY_LABELS: tuple[str, ...] = (
    "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"
)


def _month_grid(year: int, month: int) -> list[list[date | None]]:
    """6×7 grid of dates for the calendar; None for spillover."""
    cal = _calendar.Calendar(firstweekday=0)  # Monday
    weeks = cal.monthdatescalendar(year, month)
    # Spillover dates become None so the template can grey them out.
    return [
        [d if d.month == month else None for d in week]
        for week in weeks
    ]


def _tasks_by_date(user_id: int, year: int, month: int) -> dict[date, list[Task]]:
    """Tasks owned by user_id whose due_date falls in the given month."""
    first = date(year, month, 1)
    last_day = _calendar.monthrange(year, month)[1]
    last = date(year, month, last_day)
    tasks = (
        Task.query.filter_by(user_id=user_id)
        .filter(Task.due_date >= first)
        .filter(Task.due_date <= last)
        .order_by(Task.due_date.asc())
        .all()
    )
    by_date: dict[date, list[Task]] = defaultdict(list)
    for t in tasks:
        by_date[t.due_date].append(t)
    return by_date


def _adjacent_month(year: int, month: int, delta: int) -> tuple[int, int]:
    new_month = month + delta
    new_year = year
    while new_month < 1:
        new_year -= 1
        new_month += 12
    while new_month > 12:
        new_year += 1
        new_month -= 12
    return new_year, new_month


@bp.route("/")
@bp.route("/<int:year>/<int:month>")
@login_required
def calendar_view(year: int | None = None, month: int | None = None):
    today = date.today()
    if year is None or month is None:
        year, month = today.year, today.month
    if not (1 <= month <= 12) or not (1900 <= year <= 2100):
        abort(404)

    grid = _month_grid(year, month)
    by_date = _tasks_by_date(current_user.id, year, month)

    prev_year, prev_month = _adjacent_month(year, month, -1)
    next_year, next_month = _adjacent_month(year, month, +1)

    return render_template(
        "calendar/calendar.html",
        year=year,
        month=month,
        month_name=_calendar.month_name[month],
        weekday_labels=list(WEEKDAY_LABELS),
        grid=grid,
        tasks_by_date=by_date,
        today=today,
        prev_url=url_for("calendar.calendar_view", year=prev_year, month=prev_month),
        next_url=url_for("calendar.calendar_view", year=next_year, month=next_month),
        today_url=url_for("calendar.calendar_view", year=today.year, month=today.month),
    )
