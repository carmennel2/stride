"""Routes for the tasks blueprint.

Same ownership pattern as subjects: every query starts with
.filter_by(user_id=current_user.id) and uses first_or_404() so cross-user
access is indistinguishable from a missing row.
"""
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from studypilot.extensions import db
from studypilot.ml.predictor import predict_minutes
from studypilot.models import Prediction, Subject, Task, TaskType, TASK_STATUSES
from studypilot.sessions.forms import StudySessionForm
from studypilot.tasks.forms import TaskForm

bp = Blueprint("tasks", __name__, url_prefix="/tasks")


@bp.route("/")
@login_required
def list_tasks():
    """All of the current user's tasks, with optional ?status=... filter."""
    status = request.args.get("status")
    query = Task.query.filter_by(user_id=current_user.id)
    if status in TASK_STATUSES:
        query = query.filter_by(status=status)

    # Pending and in-progress tasks sort by soonest due first; done tasks
    # sort by most-recently-completed since we don't care about old dues.
    tasks = query.order_by(Task.due_date.asc(), Task.created_at.asc()).all()
    return render_template(
        "tasks/list.html",
        tasks=tasks,
        active_status=status,
        statuses=TASK_STATUSES,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_task():
    """Create a task. The predictor runs on save and writes a Prediction row."""
    # Without subjects the form's Subject dropdown is empty and validation
    # would always fail — short-circuit to a friendlier message.
    if not Subject.query.filter_by(user_id=current_user.id).first():
        flash("Add a subject first — tasks have to belong to one.", "warning")
        return redirect(url_for("subjects.new_subject"))

    form = TaskForm()
    if form.validate_on_submit():
        task = Task(
            user_id=current_user.id,
            subject_id=form.subject_id.data,
            type_id=form.type_id.data,
            title=form.title.data.strip(),
            description=(form.description.data or "").strip(),
            complexity=form.complexity.data,
            target_words=form.target_words.data,
            target_pages=form.target_pages.data,
            due_date=form.due_date.data,
            status="pending",
        )
        # Stage the row so it has a sensible state, then ask the predictor.
        # The predictor doesn't read from the DB on Day 4, but Day 8's
        # regression will look up the user's pickled model.
        minutes, version = predict_minutes(task, current_user)
        task.predicted_minutes = minutes

        db.session.add(task)
        db.session.flush()  # populate task.id without committing yet

        db.session.add(Prediction(
            task_id=task.id,
            predicted_minutes=minutes,
            model_version=version,
        ))
        db.session.commit()

        flash(f'Task "{task.title}" added — predicted {minutes} min.', "success")
        return redirect(url_for("tasks.task_detail", task_id=task.id))

    return render_template("tasks/form.html", form=form, action_label="Create",
                           task=None)


@bp.route("/<int:task_id>")
@login_required
def task_detail(task_id: int):
    """View one task. 404 if it doesn't belong to the current user."""
    task = Task.query.filter_by(
        id=task_id, user_id=current_user.id
    ).first_or_404()
    latest_prediction = task.predictions.first()
    session_form = StudySessionForm()
    total_minutes = sum(s.duration_minutes for s in task.sessions)
    return render_template(
        "tasks/detail.html",
        task=task,
        latest_prediction=latest_prediction,
        session_form=session_form,
        total_minutes=total_minutes,
    )


@bp.route("/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit_task(task_id: int):
    """Update an existing task."""
    task = Task.query.filter_by(
        id=task_id, user_id=current_user.id
    ).first_or_404()

    form = TaskForm(obj=task)
    if form.validate_on_submit():
        task.subject_id = form.subject_id.data
        task.type_id = form.type_id.data
        task.title = form.title.data.strip()
        task.description = (form.description.data or "").strip()
        task.complexity = form.complexity.data
        task.target_words = form.target_words.data
        task.target_pages = form.target_pages.data
        task.due_date = form.due_date.data

        # Re-predict — inputs may have changed materially.
        minutes, version = predict_minutes(task, current_user)
        task.predicted_minutes = minutes
        db.session.add(Prediction(
            task_id=task.id,
            predicted_minutes=minutes,
            model_version=version,
        ))
        db.session.commit()

        flash("Task updated.", "success")
        return redirect(url_for("tasks.task_detail", task_id=task.id))

    return render_template(
        "tasks/form.html", form=form, action_label="Save", task=task
    )


@bp.route("/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id: int):
    """Delete a task and its predictions/sessions (cascade)."""
    task = Task.query.filter_by(
        id=task_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(task)
    db.session.commit()
    flash(f'Task "{task.title}" deleted.', "info")
    return redirect(url_for("tasks.list_tasks"))


@bp.route("/<int:task_id>/status", methods=["POST"])
@login_required
def update_status(task_id: int):
    """Move a task between pending/in_progress/done.

    Marking a task done stamps completed_at; un-marking clears it. Day 5
    extends this to write actual_minutes back to the Prediction row.
    """
    task = Task.query.filter_by(
        id=task_id, user_id=current_user.id
    ).first_or_404()

    new_status = request.form.get("status", "")
    if new_status not in TASK_STATUSES:
        flash("Unknown status.", "danger")
        return redirect(url_for("tasks.task_detail", task_id=task.id))

    was_done = task.status == "done"
    task.status = new_status
    if new_status == "done" and not was_done:
        task.completed_at = datetime.utcnow()
    elif new_status != "done" and was_done:
        task.completed_at = None

    # Sync the latest Prediction's actual_minutes from the session log.
    # Reverting to non-done clears it so we don't leave stale data behind.
    if task.is_done:
        task.refresh_actual_minutes()
    else:
        latest = task.predictions.first()
        if latest:
            latest.actual_minutes = None

    db.session.commit()
    flash(f"Task marked {new_status.replace('_', ' ')}.", "success")
    return redirect(url_for("tasks.task_detail", task_id=task.id))
