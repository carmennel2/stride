"""Session-logging routes (rendered on the task detail page)."""
from flask import Blueprint, flash, redirect, url_for
from flask_login import current_user, login_required

from stride.extensions import db
from stride.models import StudySession, Task
from stride.sessions.forms import StudySessionForm

bp = Blueprint("sessions", __name__, url_prefix="/sessions")


@bp.route("/task/<int:task_id>/new", methods=["POST"])
@login_required
def new_session(task_id: int):
    task = Task.query.filter_by(
        id=task_id, user_id=current_user.id
    ).first_or_404()

    form = StudySessionForm()
    if not form.validate_on_submit():
        # Form lives on the task detail page, so we can't re-render with
        # state — flash each validator message instead.
        for errors in form.errors.values():
            for err in errors:
                flash(err, "danger")
        return redirect(url_for("tasks.task_detail", task_id=task.id))

    delta = form.ended_at.data - form.started_at.data
    minutes = max(1, int(round(delta.total_seconds() / 60)))

    session = StudySession(
        user_id=current_user.id,
        task_id=task.id,
        started_at=form.started_at.data,
        ended_at=form.ended_at.data,
        duration_minutes=minutes,
        note=(form.note.data or "").strip(),
    )
    db.session.add(session)
    task.refresh_actual_minutes()
    db.session.commit()

    flash(f"Logged {minutes} min.", "success")
    return redirect(url_for("tasks.task_detail", task_id=task.id))


@bp.route("/<int:session_id>/delete", methods=["POST"])
@login_required
def delete_session(session_id: int):
    session = StudySession.query.filter_by(
        id=session_id, user_id=current_user.id
    ).first_or_404()
    task = session.task
    db.session.delete(session)
    db.session.flush()  # so the actual_minutes sum doesn't see the deleted row
    task.refresh_actual_minutes()
    db.session.commit()

    flash("Session removed.", "info")
    return redirect(url_for("tasks.task_detail", task_id=task.id))
