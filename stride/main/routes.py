"""Main routes."""
from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))
    return render_template("index.html")
