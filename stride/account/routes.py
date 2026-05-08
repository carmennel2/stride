"""Account settings routes."""
from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required, logout_user

from stride.account.forms import ChangePasswordForm, DeleteAccountForm
from stride.auth.oauth import PROVIDER_LABELS, PROVIDERS
from stride.extensions import db
from stride.models import OAuthIdentity

bp = Blueprint("account", __name__, url_prefix="/account")


@bp.route("/")
@login_required
def index():
    return render_template(
        "account/index.html",
        password_form=ChangePasswordForm(),
        delete_form=DeleteAccountForm(),
        identities=current_user.oauth_identities.all(),
        provider_labels=PROVIDER_LABELS,
        all_providers=PROVIDERS,
    )


@bp.route("/password", methods=["POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    has_password = current_user.password_hash is not None

    if not form.validate_on_submit():
        for errors in form.errors.values():
            for err in errors:
                flash(err, "danger")
        return redirect(url_for("account.index"))

    # Users who already have a password must enter the current one.
    # OAuth-only users setting their first password skip this check.
    if has_password and not current_user.check_password(form.current_password.data or ""):
        flash("That doesn't match your current password.", "danger")
        return redirect(url_for("account.index"))

    current_user.set_password(form.new_password.data)
    db.session.commit()
    flash("Password updated.", "success")
    return redirect(url_for("account.index"))


@bp.route("/unlink/<string:provider>", methods=["POST"])
@login_required
def unlink_provider(provider: str):
    if provider not in PROVIDERS:
        abort(404)

    identity = current_user.oauth_identities.filter_by(provider=provider).first()
    if identity is None:
        flash(f"{PROVIDER_LABELS[provider]} isn't linked to your account.", "info")
        return redirect(url_for("account.index"))

    other_count = current_user.oauth_identities.filter(
        OAuthIdentity.provider != provider
    ).count()
    if current_user.password_hash is None and other_count == 0:
        flash(
            "You can't unlink your only sign-in method. Set a password first.",
            "warning",
        )
        return redirect(url_for("account.index"))

    db.session.delete(identity)
    db.session.commit()
    flash(f"{PROVIDER_LABELS[provider]} unlinked.", "success")
    return redirect(url_for("account.index"))


@bp.route("/delete", methods=["POST"])
@login_required
def delete_account():
    form = DeleteAccountForm()
    if not form.validate_on_submit():
        flash("Enter your password to confirm.", "danger")
        return redirect(url_for("account.index"))

    if current_user.password_hash is None:
        # OAuth-only accounts confirm by typing the literal "delete".
        if form.confirm.data.strip().lower() != "delete":
            flash("Type 'delete' to confirm.", "danger")
            return redirect(url_for("account.index"))
    elif not current_user.check_password(form.confirm.data):
        flash("That doesn't match your password.", "danger")
        return redirect(url_for("account.index"))

    user = current_user._get_current_object()
    logout_user()
    db.session.delete(user)
    db.session.commit()
    flash("Your account has been deleted.", "info")
    return redirect(url_for("main.index"))
