"""Routes for the main blueprint."""
from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    """Logged-in users land on the dashboard; everyone else gets the welcome card."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))
    return render_template("index.html")
