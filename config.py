"""Application configuration."""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# True when running outside production. Used to relax cookie-Secure so dev
# logins work over plain http://127.0.0.1.
_IS_DEV = os.getenv("FLASK_ENV", "").lower() in {"", "development", "dev"}


class Config:
    """Base configuration shared across environments."""

    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")

    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'instance' / 'stride.db'}",
    )

    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    DEBUG: bool = False

    WTF_CSRF_ENABLED: bool = True

    # ---- Session cookie hardening ----
    # HttpOnly: JavaScript can't read the cookie (XSS won't lift sessions).
    SESSION_COOKIE_HTTPONLY: bool = True
    # SameSite=Lax: blocks cookies on cross-site POSTs while preserving the
    # normal "click a link from email/Slack" flow.
    SESSION_COOKIE_SAMESITE: str = "Lax"
    # Secure: cookies only travel over HTTPS in production. False in dev so
    # http://127.0.0.1:5050 still works.
    SESSION_COOKIE_SECURE: bool = not _IS_DEV
    # Sessions expire after a week of inactivity by default. The "remember me"
    # cookie below keeps users signed in for longer if they opt in.
    PERMANENT_SESSION_LIFETIME: timedelta = timedelta(days=7)

    # ---- Remember-me cookie ----
    REMEMBER_COOKIE_DURATION: timedelta = timedelta(days=30)
    REMEMBER_COOKIE_HTTPONLY: bool = True
    REMEMBER_COOKIE_SAMESITE: str = "Lax"
    REMEMBER_COOKIE_SECURE: bool = not _IS_DEV

    # ---- OAuth credentials ----
    GOOGLE_CLIENT_ID: str | None = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: str | None = os.getenv("GOOGLE_CLIENT_SECRET")
    MICROSOFT_CLIENT_ID: str | None = os.getenv("MICROSOFT_CLIENT_ID")
    MICROSOFT_CLIENT_SECRET: str | None = os.getenv("MICROSOFT_CLIENT_SECRET")
    FACEBOOK_CLIENT_ID: str | None = os.getenv("FACEBOOK_CLIENT_ID")
    FACEBOOK_CLIENT_SECRET: str | None = os.getenv("FACEBOOK_CLIENT_SECRET")


class TestConfig(Config):
    """Configuration used by the pytest suite."""

    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"
    WTF_CSRF_ENABLED: bool = False
    SECRET_KEY: str = "test-only-do-not-use-in-prod"
    # In-memory test client — no need to constrain cookies.
    SESSION_COOKIE_SECURE: bool = False
    REMEMBER_COOKIE_SECURE: bool = False
    # Disable Flask-Login's session-fingerprint check; the test client
    # can't construct the matching `_id` for session_transaction logins.
    SESSION_PROTECTION: str | None = None
    LOGIN_DISABLED: bool = False
