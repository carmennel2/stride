"""Routes for the subjects blueprint.

Ownership pattern: every query starts with .filter_by(user_id=current_user.id).
Combined with first_or_404(), an attempt to read or modify another user's
subject returns 404 — same response as a non-existent ID, so we don't even
leak whether the row exists.
"""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from studypilot.extensions import db
from studypilot.models import Subject
from studypilot.subjects.forms import SubjectForm

bp = Blueprint("subjects", __name__, url_prefix="/subjects")


@bp.route("/")
@login_required
def list_subjects():
    """Show every subject belonging to the logged-in user, A→Z."""
    subjects = (
        Subject.query.filter_by(user_id=current_user.id)
        .order_by(Subject.name)
        .all()
    )
    return render_template("subjects/list.html", subjects=subjects)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_subject():
    """Create a new subject for the current user."""
    form = SubjectForm()
    if form.validate_on_submit():
        subject = Subject(
            user_id=current_user.id,
            name=form.name.data.strip(),
            color=form.color.data.lower(),
        )
        db.session.add(subject)
        db.session.commit()
        flash(f'Subject "{subject.name}" created.', "success")
        return redirect(url_for("subjects.list_subjects"))

    return render_template(
        "subjects/form.html", form=form, action_label="Create", subject=None
    )


@bp.route("/<int:subject_id>/edit", methods=["GET", "POST"])
@login_required
def edit_subject(subject_id: int):
    """Update an existing subject. 404 if it doesn't belong to this user."""
    subject = Subject.query.filter_by(
        id=subject_id, user_id=current_user.id
    ).first_or_404()

    form = SubjectForm(obj=subject, original_name=subject.name)
    if form.validate_on_submit():
        subject.name = form.name.data.strip()
        subject.color = form.color.data.lower()
        db.session.commit()
        flash(f'Subject "{subject.name}" updated.', "success")
        return redirect(url_for("subjects.list_subjects"))

    return render_template(
        "subjects/form.html", form=form, action_label="Save", subject=subject
    )


@bp.route("/<int:subject_id>/delete", methods=["POST"])
@login_required
def delete_subject(subject_id: int):
    """Delete a subject. 404 protects against cross-user deletes.

    Day 4 will add tasks that reference subjects via FK; once that lands,
    deleting a subject with tasks will need either CASCADE (already declared
    on the relationship) or a "you have N tasks, can't delete" guard.
    """
    subject = Subject.query.filter_by(
        id=subject_id, user_id=current_user.id
    ).first_or_404()

    db.session.delete(subject)
    db.session.commit()
    flash(f'Subject "{subject.name}" deleted.', "info")
    return redirect(url_for("subjects.list_subjects"))
