"""Seed a demo account (`flask seed-demo`)."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from stride.extensions import db
from stride.ml.predictor import heuristic_minutes
from stride.ml.trainer import train_model_for_user
from stride.models import (
    Prediction,
    StudySession,
    Subject,
    Task,
    TaskType,
    User,
    seed_task_types,
)

DEMO_USERNAME = "demo"
DEMO_EMAIL = "demo@stride.local"
DEMO_PASSWORD = "Demo1234!"

DEMO_SUBJECTS = [
    ("Mathematics", "#3b82f6"),
    ("Biology", "#10b981"),
    ("History", "#f59e0b"),
    ("Programming", "#8b5cf6"),
]

COMPLETED_TASK_TEMPLATES = [
    (0, "Problem Set", {"complexity": 3}),
    (0, "Problem Set", {"complexity": 4}),
    (0, "Problem Set", {"complexity": 2}),
    (0, "Revision",    {"complexity": 3}),
    (0, "Revision",    {"complexity": 4}),
    (0, "Reading",     {"complexity": 2, "target_pages": 18}),
    (1, "Reading",     {"complexity": 3, "target_pages": 24}),
    (1, "Reading",     {"complexity": 2, "target_pages": 12}),
    (1, "Essay",       {"complexity": 3, "target_words": 1200}),
    (1, "Revision",    {"complexity": 3}),
    (1, "Revision",    {"complexity": 4}),
    (2, "Essay",       {"complexity": 4, "target_words": 1800}),
    (2, "Essay",       {"complexity": 3, "target_words": 1500}),
    (2, "Reading",     {"complexity": 3, "target_pages": 30}),
    (2, "Reading",     {"complexity": 2, "target_pages": 20}),
    (2, "Revision",    {"complexity": 2}),
    (3, "Coding",      {"complexity": 3}),
    (3, "Coding",      {"complexity": 4}),
    (3, "Coding",      {"complexity": 5}),
    (3, "Coding",      {"complexity": 2}),
    (3, "Problem Set", {"complexity": 4}),
    (3, "Reading",     {"complexity": 2, "target_pages": 14}),
    (3, "Other",       {"complexity": 3}),
    (3, "Revision",    {"complexity": 3}),
    (3, "Coding",      {"complexity": 3}),
]

OPEN_TASK_TEMPLATES = [
    (0, "Problem Set", {"complexity": 4}, 2),
    (1, "Essay",       {"complexity": 3, "target_words": 1500}, 6),
    (2, "Reading",     {"complexity": 3, "target_pages": 22}, 3),
    (2, "Essay",       {"complexity": 4, "target_words": 2000}, 9),
    (3, "Coding",      {"complexity": 4}, 5),
    (3, "Revision",    {"complexity": 2}, 1),
]


def _drop_existing_demo_user() -> None:
    user = User.query.filter_by(username=DEMO_USERNAME).first()
    if user is None:
        return
    db.session.delete(user)
    db.session.commit()


def seed_demo(rng_seed: int = 42) -> dict:
    """Build the demo user. Idempotent: drops the existing demo user first."""
    seed_task_types()
    _drop_existing_demo_user()

    rng = random.Random(rng_seed)

    user = User(username=DEMO_USERNAME, email=DEMO_EMAIL)
    user.set_password(DEMO_PASSWORD)
    db.session.add(user)
    db.session.flush()

    subjects = []
    for name, color in DEMO_SUBJECTS:
        s = Subject(user_id=user.id, name=name, color=color)
        db.session.add(s)
        subjects.append(s)
    db.session.flush()

    types_by_name = {t.name: t for t in TaskType.query.all()}

    completed_count = 0
    today = date.today()

    # Spread completed tasks across the previous ~60 days. Actual minutes
    # are heuristic * 1.15 with ±15% noise so the regression has a
    # learnable bias on top of irreducible per-task variance.
    for offset, (subj_idx, type_name, kw) in enumerate(COMPLETED_TASK_TEMPLATES):
        days_ago = 60 - offset * 2
        created = datetime.utcnow() - timedelta(days=days_ago)
        completed = created + timedelta(days=1)
        due = (created + timedelta(days=2)).date()

        task = Task(
            user_id=user.id,
            subject_id=subjects[subj_idx].id,
            type_id=types_by_name[type_name].id,
            title=_title_for(subjects[subj_idx].name, type_name, offset),
            description=_description_for(type_name),
            complexity=kw.get("complexity", 3),
            target_words=kw.get("target_words"),
            target_pages=kw.get("target_pages"),
            due_date=due,
            status="done",
            created_at=created,
            completed_at=completed,
        )
        task.task_type = types_by_name[type_name]
        predicted = heuristic_minutes(task)
        task.predicted_minutes = predicted
        db.session.add(task)
        db.session.flush()

        actual = max(15, int(predicted * 1.15 * rng.uniform(0.85, 1.15)))

        n_sessions = rng.choice([1, 2, 2, 3])
        slices = _split_minutes(actual, n_sessions, rng)
        cursor = created.replace(hour=9, minute=0, second=0, microsecond=0)
        for slice_min in slices:
            db.session.add(StudySession(
                user_id=user.id, task_id=task.id,
                started_at=cursor,
                ended_at=cursor + timedelta(minutes=slice_min),
                duration_minutes=slice_min,
                note="",
            ))
            cursor += timedelta(minutes=slice_min + rng.randint(60, 180))

        db.session.add(Prediction(
            task_id=task.id,
            predicted_minutes=predicted,
            actual_minutes=actual,
            model_version="heuristic_v1",
            created_at=created,
        ))
        completed_count += 1

    open_count = 0
    for subj_idx, type_name, kw, days_until_due in OPEN_TASK_TEMPLATES:
        created = datetime.utcnow()
        due = today + timedelta(days=days_until_due)
        task = Task(
            user_id=user.id,
            subject_id=subjects[subj_idx].id,
            type_id=types_by_name[type_name].id,
            title=_title_for(subjects[subj_idx].name, type_name, 100 + open_count),
            description=_description_for(type_name),
            complexity=kw.get("complexity", 3),
            target_words=kw.get("target_words"),
            target_pages=kw.get("target_pages"),
            due_date=due,
            status="pending",
            created_at=created,
        )
        task.task_type = types_by_name[type_name]
        predicted = heuristic_minutes(task)
        task.predicted_minutes = predicted
        db.session.add(task)
        db.session.flush()
        db.session.add(Prediction(
            task_id=task.id,
            predicted_minutes=predicted,
            model_version="heuristic_v1",
            created_at=created,
        ))
        open_count += 1

    db.session.commit()

    pipe = train_model_for_user(user.id)

    return {
        "username": DEMO_USERNAME,
        "password": DEMO_PASSWORD,
        "subjects": len(subjects),
        "completed_tasks": completed_count,
        "open_tasks": open_count,
        "model_trained": pipe is not None,
    }


def _split_minutes(total: int, n_pieces: int, rng: random.Random) -> list[int]:
    if n_pieces == 1:
        return [total]
    cuts = sorted(rng.randint(15, total - 15) for _ in range(n_pieces - 1))
    parts = []
    prev = 0
    for c in cuts:
        parts.append(c - prev)
        prev = c
    parts.append(total - prev)
    fixed = [max(5, p) for p in parts]
    deficit = sum(fixed) - total
    fixed[-1] -= deficit
    return [max(5, p) for p in fixed]


def _title_for(subject: str, type_name: str, idx: int) -> str:
    bank = {
        "Reading":     ["Read chapter", "Skim chapter", "Re-read section"],
        "Essay":       ["Draft essay", "Write essay", "Edit essay"],
        "Problem Set": ["Problem set", "Tutorial set", "Practice problems"],
        "Coding":      ["Coding lab", "Project sprint", "Algorithm warm-up"],
        "Revision":    ["Revise", "Recap", "Spaced revision"],
        "Other":       ["Notes review", "Quiz prep", "Catch-up"],
    }
    head = bank.get(type_name, ["Task"])[idx % len(bank.get(type_name, ["Task"]))]
    return f"{subject} — {head} {idx + 1}"


def _description_for(type_name: str) -> str:
    return {
        "Reading": "Pages from this week's textbook chapter.",
        "Essay": "Written piece for the upcoming submission.",
        "Problem Set": "Problems from the tutorial sheet.",
        "Coding": "Implementation work; aim for a clean, tested commit.",
        "Revision": "Spaced revision over recent material.",
        "Other": "Catch-up / planning / housekeeping.",
    }.get(type_name, "")
