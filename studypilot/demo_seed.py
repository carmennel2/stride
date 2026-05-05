"""Demo seed used by the `flask seed-demo` CLI.

Builds a realistic-looking account named `demo` (password `demo1234`)
with four subjects, twenty-five completed tasks and a handful of open
tasks across the next two weeks. Each completed task has one or more
study sessions whose duration varies around the heuristic estimate —
giving the regression a non-trivial signal to learn.

Re-running drops everything the demo user already owns so the seed is
idempotent.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from studypilot.extensions import db
from studypilot.ml.predictor import heuristic_minutes
from studypilot.ml.trainer import train_model_for_user
from studypilot.models import (
    Prediction,
    StudySession,
    Subject,
    Task,
    TaskType,
    User,
    seed_task_types,
)

DEMO_USERNAME = "demo"
DEMO_EMAIL = "demo@studypilot.local"
DEMO_PASSWORD = "demo1234"

DEMO_SUBJECTS = [
    ("Mathematics", "#3366ff"),
    ("Biology", "#22aa44"),
    ("History", "#aa6622"),
    ("Programming", "#aa2266"),
]

# Templates for 25 completed tasks. (subject_index, type_name, kw)
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

# Six open tasks spread across the planner horizon.
OPEN_TASK_TEMPLATES = [
    (0, "Problem Set", {"complexity": 4}, 2),
    (1, "Essay",       {"complexity": 3, "target_words": 1500}, 6),
    (2, "Reading",     {"complexity": 3, "target_pages": 22}, 3),
    (2, "Essay",       {"complexity": 4, "target_words": 2000}, 9),
    (3, "Coding",      {"complexity": 4}, 5),
    (3, "Revision",    {"complexity": 2}, 1),
]


def _drop_existing_demo_user() -> None:
    """Remove the demo user — cascades take care of everything they own."""
    user = User.query.filter_by(username=DEMO_USERNAME).first()
    if user is None:
        return
    db.session.delete(user)
    db.session.commit()


def seed_demo(rng_seed: int = 42) -> dict:
    """Build the demo user, return a small summary dict."""
    # Make sure task_types are present even if the caller didn't run init-db.
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

    # Completed tasks span the previous ~60 days. Each task's actual
    # minutes vary around the heuristic estimate by ±25%, with a slight
    # systematic bias so the regression has something to learn.
    for offset, (subj_idx, type_name, kw) in enumerate(COMPLETED_TASK_TEMPLATES):
        days_ago = 60 - offset * 2  # spaced roughly every other day
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
        # Set predicted_minutes from the heuristic so it's realistic.
        # (We can't call predict_minutes() with the user yet — no model.)
        task.task_type = types_by_name[type_name]
        predicted = heuristic_minutes(task)
        task.predicted_minutes = predicted
        db.session.add(task)
        db.session.flush()

        # Actual minutes: heuristic * a per-user-style scale (1.15)
        # plus per-task noise. This gives the regression a learnable bias.
        actual = max(15, int(predicted * 1.15 * rng.uniform(0.85, 1.15)))

        # Split into 1-3 sessions across the day.
        n_sessions = rng.choice([1, 2, 2, 3])
        # Distribute actual across sessions.
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
            # Next session a couple of hours later.
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

    # Train the regression model on the seeded history. Most tasks are
    # done, so this should hit the threshold comfortably.
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
    """Split a total minute count into `n_pieces` positive chunks."""
    if n_pieces == 1:
        return [total]
    # Generate n-1 internal cut points, build the increments.
    cuts = sorted(rng.randint(15, total - 15) for _ in range(n_pieces - 1))
    parts = []
    prev = 0
    for c in cuts:
        parts.append(c - prev)
        prev = c
    parts.append(total - prev)
    # Floor each piece at 5 minutes; rebalance any deficit onto the last.
    fixed = [max(5, p) for p in parts]
    deficit = sum(fixed) - total
    fixed[-1] -= deficit
    return [max(5, p) for p in fixed]


def _title_for(subject: str, type_name: str, idx: int) -> str:
    """Generate a short, plausible task title."""
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
