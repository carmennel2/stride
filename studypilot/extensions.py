"""Singletons for Flask extensions.

Defining them in their own module avoids circular imports: blueprints can
import `db` and `login_manager` without importing the whole app factory.
"""
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
# CSRFProtect both enforces tokens on bare POST endpoints (like /auth/logout)
# and exposes `csrf_token()` as a Jinja global so non-form POSTs in templates
# can include a token without instantiating a FlaskForm.
csrf = CSRFProtect()


@login_manager.user_loader
def load_user(user_id: str):
    """Look up the current user by ID for Flask-Login.

    Imported lazily to avoid a circular import: models.py needs `db` from
    this module, so we can't import User at module load time.
    """
    from studypilot.models import User

    return db.session.get(User, int(user_id))
