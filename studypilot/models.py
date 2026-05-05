"""Database models.

Each ORM class maps to one normalized table. The schema grows over Days
2-5: User (Day 2), Subject + TaskType (Day 3), Task + Prediction (Day 4),
StudySession (Day 5).
"""
from datetime import date, datetime

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


# Task statuses live in code rather than a lookup table — they're small,
# stable, and we want to validate against them in forms without a join.
TASK_STATUSES: tuple[str, ...] = ("pending", "in_progress", "done")


class Task(db.Model):
    """A piece of study work the user wants to track.

    target_words and target_pages are nullable on purpose — Reading uses
    pages, Essay uses words, the other types use neither. The predictor
    feature builder treats missing values as zero.
    """

    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    subject_id = db.Column(
        db.Integer, db.ForeignKey("subjects.id"), nullable=False, index=True
    )
    type_id = db.Column(
        db.Integer, db.ForeignKey("task_types.id"), nullable=False
    )
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    complexity = db.Column(db.Integer, nullable=False, default=3)
    target_words = db.Column(db.Integer, nullable=True)
    target_pages = db.Column(db.Integer, nullable=True)
    # predicted_minutes is set on create by the predictor; never null.
    predicted_minutes = db.Column(db.Integer, nullable=False, default=0)
    due_date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship(
        "User",
        backref=db.backref("tasks", lazy="dynamic", cascade="all, delete-orphan"),
    )
    subject = db.relationship("Subject", backref=db.backref("tasks", lazy="dynamic"))
    task_type = db.relationship("TaskType")

    @property
    def is_done(self) -> bool:
        return self.status == "done"

    def refresh_actual_minutes(self) -> None:
        """Sync actual_minutes on the latest Prediction with summed sessions.

        Only meaningful for done tasks: actual_minutes is "what the task
        ended up taking," which doesn't apply while it's still pending.
        Caller is responsible for committing the session.
        """
        if not self.is_done:
            return
        latest = self.predictions.first()  # ordered by created_at DESC
        if latest is None:
            return
        total = sum(s.duration_minutes for s in self.sessions)
        latest.actual_minutes = total or None

    def __repr__(self) -> str:
        return f"<Task {self.id} {self.title!r} status={self.status}>"


class Prediction(db.Model):
    """Audit row written every time the predictor estimates a task.

    One row per task: created when the task is first saved, updated with
    actual_minutes when the task is marked done. model_version records
    which predictor produced the estimate so we can compare heuristic
    vs regression accuracy on the insights page.
    """

    __tablename__ = "predictions"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    predicted_minutes = db.Column(db.Integer, nullable=False)
    # Filled in on task completion (Day 5).
    actual_minutes = db.Column(db.Integer, nullable=True)
    model_version = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    task = db.relationship(
        "Task",
        backref=db.backref(
            "predictions", lazy="dynamic", cascade="all, delete-orphan",
            order_by="Prediction.created_at.desc()",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Prediction task={self.task_id} predicted={self.predicted_minutes} "
            f"actual={self.actual_minutes} model={self.model_version}>"
        )


class StudySession(db.Model):
    """One stretch of time spent on a task.

    Stored as start + end + computed duration so we can render a session
    log per task and aggregate by day-of-week / subject for the dashboard.
    Duration is denormalised into duration_minutes for fast aggregations
    without wiring custom SQL on every query.
    """

    __tablename__ = "study_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    started_at = db.Column(db.DateTime, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(500), nullable=False, default="")

    user = db.relationship(
        "User",
        backref=db.backref("sessions", lazy="dynamic", cascade="all, delete-orphan"),
    )
    task = db.relationship(
        "Task",
        backref=db.backref(
            "sessions", lazy="dynamic", cascade="all, delete-orphan",
            order_by="StudySession.started_at.desc()",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<StudySession task={self.task_id} "
            f"{self.duration_minutes}m at {self.started_at}>"
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
