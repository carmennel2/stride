"""Flask extension singletons."""
from authlib.integrations.flask_client import OAuth
from flask import current_app, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
oauth = OAuth()
# In-memory rate-limit store; swap storage_uri to redis:// in production
# behind multiple workers.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    headers_enabled=True,
)


@login_manager.user_loader
def load_user(user_id: str):
    # Lazy import — models.py imports `db` from here.
    from stride.models import User

    return db.session.get(User, int(user_id))


@limiter.request_filter
def _exempt_in_testing():
    return bool(current_app.config.get("TESTING"))


def rate_limit_response(_error):
    return render_template("errors/429.html"), 429
