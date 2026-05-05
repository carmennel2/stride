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


class Subject(db.Model):
    """A study subject scoped to one user.

    Subject names are unique per-user, not globally — two students can both
    have a "Maths" subject without conflict. Colour is a #rrggbb hex string,
    used by the dashboard charts on Day 6.
    """

    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(80), nullable=False)
    # Stored as a 7-char hex string including the leading '#'.
    color = db.Column(db.String(7), nullable=False, default="#3366ff")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Deleting a user cascades to their subjects (and, on Day 4, their tasks).
    user = db.relationship(
        "User",
        backref=db.backref(
            "subjects", lazy="dynamic", cascade="all, delete-orphan"
        ),
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_subject_user_name"),
    )

    def __repr__(self) -> str:
        return f"<Subject {self.name} (user={self.user_id})>"


class TaskType(db.Model):
    """Global lookup of task categories (Reading, Essay, ...).

    Shared across all users — the predictor uses type as a feature, so
    consistent categories make the model trainable. Seeded on init-db
    via seed_task_types().
    """

    __tablename__ = "task_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), unique=True, nullable=False)

    def __repr__(self) -> str:
        return f"<TaskType {self.name}>"


# Default categories. Order is preserved by sequential insert IDs, which
# the dashboard uses to render bars/pies in a stable order.
DEFAULT_TASK_TYPES: tuple[str, ...] = (
    "Reading",
    "Essay",
    "Problem Set",
    "Coding",
    "Revision",
    "Other",
)


def seed_task_types() -> int:
    """Insert any missing default task types. Idempotent.

    Returns the number of rows added so the caller (typically the init-db
    CLI) can report progress. Existing rows are left alone, so re-running
    after manual edits won't overwrite anything.
    """
    existing = {t.name for t in TaskType.query.all()}
    added = 0
    for name in DEFAULT_TASK_TYPES:
        if name not in existing:
            db.session.add(TaskType(name=name))
            added += 1
    if added:
        db.session.commit()
    return added
