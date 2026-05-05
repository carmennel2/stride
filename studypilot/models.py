"""Database models.

Each ORM class maps to one normalized table. Day 2 introduces only the
User model; subjects, task types, tasks, sessions, and predictions are
added on Days 3-5 as the schema grows.
"""
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from studypilot.extensions import db


class User(UserMixin, db.Model):
    """A registered StudyPilot account.

    UserMixin gives us the boilerplate Flask-Login expects (`is_authenticated`,
    `is_active`, `is_anonymous`, `get_id`). Passwords are never stored in
    plain text — only the salted hash produced by Werkzeug.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        """Hash and store the given plain-text password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Return True if the given plain-text password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"
