"""Routes for the auth blueprint.

Three endpoints — signup, login, logout — plus the convention that
`next` query-string redirects must point at our own host so a
malicious link can't bounce a logged-in user off-site.
"""
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

from studypilot.auth.forms import LoginForm, SignupForm
from studypilot.extensions import db
from studypilot.models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _safe_next_url(target: str | None) -> str | None:
    """Return `target` only if it's a relative URL on our own host.

    Blocks open-redirect attacks where ?next=https://evil.example/...
    would otherwise drop the user on a phishing page after login.
    """
    if not target:
        return None
    parsed = urlparse(target)
    # Relative URLs have no netloc — those are safe.
    if parsed.netloc == "" and parsed.scheme == "":
        return target
    return None


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    """Create a new account, then drop the user straight onto the dashboard."""
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
        db.session.commit()

        # Log them in immediately — saves a redundant trip through the login form.
        login_user(user)
        flash("Welcome to StudyPilot — your account is ready.", "success")
        return redirect(url_for("main.index"))

    return render_template("auth/signup.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate an existing user against username-or-email + password."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.identifier.data.strip()
        # Allow either field — small UX win, no security cost.
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
    """End the session. POST-only so a stray <img> tag can't log users out."""
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("main.index"))
