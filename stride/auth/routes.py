"""Auth routes: signup, login, logout."""
from urllib.parse import urlparse

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from stride.auth.forms import LoginForm, SignupForm
from stride.extensions import db, limiter
from stride.models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _safe_next_url(target: str | None) -> str | None:
    """Return `target` only if it's a relative URL (open-redirect guard)."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc == "" and parsed.scheme == "":
        return target
    return None


@bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("10/hour", methods=["POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = SignupForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip().lower(),
        )
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            # Race against form-level uniqueness check.
            db.session.rollback()
            flash(
                "That username or email is already taken. "
                "Please pick another.",
                "danger",
            )
            return render_template("auth/signup.html", form=form)

        login_user(user)
        flash("Welcome to Stride — your account is ready.", "success")
        return redirect(url_for("main.index"))

    return render_template("auth/signup.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20/minute;100/hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.identifier.data.strip()
        user = (
            User.query.filter(
                (User.username == identifier) | (User.email == identifier.lower())
            ).first()
        )
        if user is None or not user.check_password(form.password.data):
            # Same message either way so we don't leak which usernames exist.
            flash("Invalid username/email or password.", "danger")
            return render_template("auth/login.html", form=form)

        login_user(user, remember=form.remember_me.data)
        flash(f"Welcome back, {user.username}.", "success")

        next_url = _safe_next_url(request.args.get("next"))
        return redirect(next_url or url_for("main.index"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """POST-only so a stray <img> tag can't log users out."""
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("main.index"))
