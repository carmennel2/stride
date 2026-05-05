"""Routes for the main blueprint."""
from flask import Blueprint, render_template

bp = Blueprint("main", __name__)


@bp.route("/")
def index() -> str:
    """Public landing page.

    On Day 6 this will redirect to /dashboard for logged-in users.
    """
    return render_template("index.html")
