"""Database models."""
from datetime import date, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from stride.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    # Nullable for OAuth-only users.
    password_hash = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if self.password_hash is None:
            return False
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class OAuthIdentity(db.Model):
    """Links a User to one identity at an external provider."""
    __tablename__ = "oauth_identities"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = db.Column(db.String(32), nullable=False)
    provider_user_id = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship(
        "User",
        backref=db.backref(
            "oauth_identities", lazy="dynamic", cascade="all, delete-orphan"
        ),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "provider", "provider_user_id", name="uq_oauth_provider_subject"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<OAuthIdentity {self.provider}:{self.provider_user_id} "
            f"user={self.user_id}>"
        )


class Subject(db.Model):
    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(80), nullable=False)
    color = db.Column(db.String(7), nullable=False, default="#10b981")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

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
    """Global lookup of task categories."""
    __tablename__ = "task_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), unique=True, nullable=False)

    def __repr__(self) -> str:
        return f"<TaskType {self.name}>"


DEFAULT_TASK_TYPES: tuple[str, ...] = (
    "Reading",
    "Essay",
    "Problem Set",
    "Coding",
    "Revision",
    "Other",
)


TASK_STATUSES: tuple[str, ...] = ("pending", "in_progress", "done")


class Task(db.Model):
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
        """Sync actual_minutes on the latest Prediction with summed sessions."""
        if not self.is_done:
            return
        latest = self.predictions.first()
        if latest is None:
            return
        total = sum(s.duration_minutes for s in self.sessions)
        latest.actual_minutes = total or None

    def __repr__(self) -> str:
        return f"<Task {self.id} {self.title!r} status={self.status}>"


class Prediction(db.Model):
    """One row per task; predicted_minutes on create, actual_minutes on done."""
    __tablename__ = "predictions"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    predicted_minutes = db.Column(db.Integer, nullable=False)
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
    # Denormalised — sums hot on the dashboard.
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
    """Insert any missing default task types. Idempotent."""
    existing = {t.name for t in TaskType.query.all()}
    added = 0
    for name in DEFAULT_TASK_TYPES:
        if name not in existing:
            db.session.add(TaskType(name=name))
            added += 1
    if added:
        db.session.commit()
    return added
