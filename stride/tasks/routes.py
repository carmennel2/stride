"""Tasks routes (per-user)."""
import logging
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from stride.extensions import db
from stride.ml.predictor import predict_minutes
from stride.ml.trainer import train_model_for_user
from stride.models import TASK_STATUSES, Prediction, Subject, Task, TaskType
from stride.sessions.forms import StudySessionForm
from stride.tasks.forms import TaskForm

bp = Blueprint("tasks", __name__, url_prefix="/tasks")
logger = logging.getLogger(__name__)


@bp.route("/")
@login_required
def list_tasks():
    status = request.args.get("status")
    query = Task.query.filter_by(user_id=current_user.id)
    if status in TASK_STATUSES:
        query = query.filter_by(status=status)
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
        # Attach the type relationship before predict — task isn't flushed yet.
        task.task_type = db.session.get(TaskType, form.type_id.data)

        minutes, version = predict_minutes(task, current_user)
        task.predicted_minutes = minutes

        db.session.add(task)
        db.session.flush()
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
    task = Task.query.filter_by(
        id=task_id, user_id=current_user.id
    ).first_or_404()

    form = TaskForm(obj=task)
    if form.validate_on_submit():
        task.subject_id = form.subject_id.data
        task.type_id = form.type_id.data
        task.task_type = db.session.get(TaskType, form.type_id.data)
        task.title = form.title.data.strip()
        task.description = (form.description.data or "").strip()
        task.complexity = form.complexity.data
        task.target_words = form.target_words.data
        task.target_pages = form.target_pages.data
        task.due_date = form.due_date.data

        # Re-predict — inputs may have changed.
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

    if task.is_done:
        task.refresh_actual_minutes()
    else:
        # Reverting from done: clear actual_minutes so we don't leave stale data.
        latest = task.predictions.first()
        if latest:
            latest.actual_minutes = None

    db.session.commit()

    if task.is_done:
        try:
            train_model_for_user(current_user.id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to retrain regression for user %s after task %s",
                current_user.id, task.id,
            )
    flash(f"Task marked {new_status.replace('_', ' ')}.", "success")
    return redirect(url_for("tasks.task_detail", task_id=task.id))
