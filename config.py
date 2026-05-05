"""Application configuration.

A single Config class keeps environment-specific values (secret key, database
URL) out of the source code and reads them from environment variables. This is
loaded by the app factory in studypilot/__init__.py.
"""
import os
from pathlib import Path

# Project root — used to build the default SQLite path.
BASE_DIR = Path(__file__).resolve().parent


class Config:
    """Base configuration shared across environments."""

    # SECRET_KEY signs session cookies and CSRF tokens. Set a real value in .env
    # before deploying anywhere — the default below is only safe for development.
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")

    # SQLite is fine for the assessment. instance/ is created automatically
    # by the app factory if it doesn't exist yet.
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'instance' / 'studypilot.db'}",
    )

    # Quietens a deprecation warning we don't care about.
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
