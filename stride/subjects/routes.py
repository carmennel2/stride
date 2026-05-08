"""Subjects routes (per-user)."""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from stride.extensions import db
from stride.models import Subject
from stride.subjects.forms import SubjectForm

bp = Blueprint("subjects", __name__, url_prefix="/subjects")


@bp.route("/")
@login_required
def list_subjects():
    subjects = (
        Subject.query.filter_by(user_id=current_user.id)
        .order_by(Subject.name)
        .all()
    )
    return render_template("subjects/list.html", subjects=subjects)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_subject():
    form = SubjectForm()
    if form.validate_on_submit():
        subject = Subject(
            user_id=current_user.id,
            name=form.name.data.strip(),
            color=form.color.data.lower(),
        )
        db.session.add(subject)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("You already have a subject with that name.", "danger")
            return render_template(
                "subjects/form.html", form=form, action_label="Create", subject=None
            )
        flash(f'Subject "{subject.name}" created.', "success")
        return redirect(url_for("subjects.list_subjects"))

    return render_template(
        "subjects/form.html", form=form, action_label="Create", subject=None
    )


@bp.route("/<int:subject_id>/edit", methods=["GET", "POST"])
@login_required
def edit_subject(subject_id: int):
    subject = Subject.query.filter_by(
        id=subject_id, user_id=current_user.id
    ).first_or_404()

    form = SubjectForm(obj=subject, original_name=subject.name)
    if form.validate_on_submit():
        subject.name = form.name.data.strip()
        subject.color = form.color.data.lower()
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("You already have a subject with that name.", "danger")
            return render_template(
                "subjects/form.html", form=form, action_label="Save", subject=subject
            )
        flash(f'Subject "{subject.name}" updated.', "success")
        return redirect(url_for("subjects.list_subjects"))

    return render_template(
        "subjects/form.html", form=form, action_label="Save", subject=subject
    )


@bp.route("/<int:subject_id>/delete", methods=["POST"])
@login_required
def delete_subject(subject_id: int):
    subject = Subject.query.filter_by(
        id=subject_id, user_id=current_user.id
    ).first_or_404()

    db.session.delete(subject)
    db.session.commit()
    flash(f'Subject "{subject.name}" deleted.', "info")
    return redirect(url_for("subjects.list_subjects"))
