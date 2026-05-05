"""Routes for the sessions blueprint.

Sessions are always created or deleted in the context of a task — there
is no standalone /sessions list. The form for adding one is rendered on
the task detail page; this blueprint owns the POST endpoints.
"""
from flask import Blueprint, flash, redirect, url_for
from flask_login import current_user, login_required

from studypilot.extensions import db
from studypilot.models import StudySession, Task
from studypilot.sessions.forms import StudySessionForm

bp = Blueprint("sessions", __name__, url_prefix="/sessions")


@bp.route("/task/<int:task_id>/new", methods=["POST"])
@login_required
def new_session(task_id: int):
    """Add a study session to a task."""
    task = Task.query.filter_by(
        id=task_id, user_id=current_user.id
    ).first_or_404()

    form = StudySessionForm()
    if not form.validate_on_submit():
        # Surface the first error as a flash. The detail page re-renders
        # with form.errors anyway via the form passed back via session-flash.
        for field, errors in form.errors.items():
            for err in errors:
                flash(f"{field}: {err}", "danger")
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

    # If the task is already done, keep actual_minutes in sync.
    task.refresh_actual_minutes()

    db.session.commit()
    flash(f"Logged {minutes} min.", "success")
    return redirect(url_for("tasks.task_detail", task_id=task.id))


@bp.route("/<int:session_id>/delete", methods=["POST"])
@login_required
def delete_session(session_id: int):
    """Remove a session. user_id filter prevents cross-user deletion."""
    session = StudySession.query.filter_by(
        id=session_id, user_id=current_user.id
    ).first_or_404()
    task = session.task
    db.session.delete(session)
    db.session.flush()  # so subsequent sum() doesn't see the deleted row

    task.refresh_actual_minutes()

    db.session.commit()
    flash("Session removed.", "info")
    return redirect(url_for("tasks.task_detail", task_id=task.id))
