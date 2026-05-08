"""Tests for the insights aggregations: summary stats, streak, by-subject."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from stride.extensions import db
from stride.insights.routes import (
    _accuracy_summary,
    _best_weekday,
    _by_subject,
    _scored_predictions,
    _streak,
)
from stride.models import (
    Prediction,
    StudySession,
    Task,
    TaskType,
)


def _scored_task(user, subject, predicted, actual, model="heuristic_v1"):
    coding = TaskType.query.filter_by(name="Coding").one()
    task = Task(
        user_id=user.id, subject_id=subject.id, type_id=coding.id,
        title="x", description="", complexity=3,
        predicted_minutes=predicted, status="done",
        due_date=date.today() - timedelta(days=1),
        created_at=datetime.utcnow() - timedelta(days=2),
        completed_at=datetime.utcnow() - timedelta(days=1),
    )
    db.session.add(task)
    db.session.flush()
    db.session.add(Prediction(
        task_id=task.id, predicted_minutes=predicted,
        actual_minutes=actual, model_version=model,
    ))
    db.session.add(StudySession(
        user_id=user.id, task_id=task.id,
        started_at=datetime.utcnow() - timedelta(days=2),
        ended_at=datetime.utcnow() - timedelta(days=2) + timedelta(minutes=actual),
        duration_minutes=actual, note="",
    ))
    db.session.commit()
    return task


class TestAccuracySummary:
    def test_empty_returns_zero_count(self):
        summary = _accuracy_summary([])
        assert summary["count"] == 0
        assert summary["mae"] == 0
        assert summary["bias"] == 0
        assert summary["by_version"] == {}

    def test_perfect_predictions_zero_error(self, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        for _ in range(3):
            _scored_task(user, subj, predicted=60, actual=60)
        preds = _scored_predictions(user.id)
        summary = _accuracy_summary(preds)
        assert summary["mae"] == 0
        assert summary["bias"] == 0
        assert summary["count"] == 3

    def test_consistent_underestimate_positive_bias(self, make_user, make_subject):
        """Predicting 60 when actual is 90 → bias = +30."""
        user = make_user("alice")
        subj = make_subject(user)
        for _ in range(3):
            _scored_task(user, subj, predicted=60, actual=90)
        preds = _scored_predictions(user.id)
        summary = _accuracy_summary(preds)
        assert summary["mae"] == 30.0
        assert summary["bias"] == 30.0

    def test_per_version_counts(self, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        _scored_task(user, subj, 60, 60, model="heuristic_v1")
        _scored_task(user, subj, 60, 60, model="heuristic_v1")
        _scored_task(user, subj, 60, 60, model="regression_v1")
        preds = _scored_predictions(user.id)
        summary = _accuracy_summary(preds)
        assert summary["by_version"] == {"heuristic_v1": 2, "regression_v1": 1}

    def test_only_done_with_actual_counted(self, make_user, make_subject):
        """A pending task with a prediction but no actual_minutes shouldn't count."""
        user = make_user("alice")
        subj = make_subject(user)
        coding = TaskType.query.filter_by(name="Coding").one()
        # Done but with actual
        _scored_task(user, subj, 60, 70)
        # Pending (no actual)
        pending = Task(
            user_id=user.id, subject_id=subj.id, type_id=coding.id,
            title="p", description="", complexity=3,
            predicted_minutes=60, status="pending",
            due_date=date.today() + timedelta(days=1),
            created_at=datetime.utcnow(),
        )
        db.session.add(pending)
        db.session.flush()
        db.session.add(Prediction(
            task_id=pending.id, predicted_minutes=60,
            model_version="heuristic_v1",
        ))
        db.session.commit()

        preds = _scored_predictions(user.id)
        assert len(preds) == 1


class TestStreak:
    def test_no_sessions_zero_streak(self, make_user):
        user = make_user("alice")
        assert _streak(user.id) == 0

    def test_session_today_starts_streak_at_one(self, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        task = _scored_task(user, subj, 60, 60)
        # _scored_task adds a session 2 days ago — replace with one today
        StudySession.query.delete()
        db.session.add(StudySession(
            user_id=user.id, task_id=task.id,
            started_at=datetime.combine(date.today(), datetime.min.time().replace(hour=9)),
            ended_at=datetime.combine(date.today(), datetime.min.time().replace(hour=10)),
            duration_minutes=60, note="",
        ))
        db.session.commit()
        assert _streak(user.id) == 1

    def test_three_consecutive_days_streak_three(self, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        task = _scored_task(user, subj, 60, 60)
        StudySession.query.delete()
        for offset in range(3):
            d = date.today() - timedelta(days=offset)
            db.session.add(StudySession(
                user_id=user.id, task_id=task.id,
                started_at=datetime.combine(d, datetime.min.time().replace(hour=9)),
                ended_at=datetime.combine(d, datetime.min.time().replace(hour=10)),
                duration_minutes=60, note="",
            ))
        db.session.commit()
        assert _streak(user.id) == 3

    def test_gap_yesterday_breaks_streak(self, make_user, make_subject):
        """Sessions today and 2-3 days ago — streak only counts today."""
        user = make_user("alice")
        subj = make_subject(user)
        task = _scored_task(user, subj, 60, 60)
        StudySession.query.delete()
        for offset in [0, 2, 3]:
            d = date.today() - timedelta(days=offset)
            db.session.add(StudySession(
                user_id=user.id, task_id=task.id,
                started_at=datetime.combine(d, datetime.min.time().replace(hour=9)),
                ended_at=datetime.combine(d, datetime.min.time().replace(hour=10)),
                duration_minutes=60, note="",
            ))
        db.session.commit()
        assert _streak(user.id) == 1

    def test_unworked_today_anchors_at_yesterday(self, make_user, make_subject):
        """A user who hasn't studied yet today shouldn't see streak reset."""
        user = make_user("alice")
        subj = make_subject(user)
        task = _scored_task(user, subj, 60, 60)
        StudySession.query.delete()
        for offset in [1, 2]:
            d = date.today() - timedelta(days=offset)
            db.session.add(StudySession(
                user_id=user.id, task_id=task.id,
                started_at=datetime.combine(d, datetime.min.time().replace(hour=9)),
                ended_at=datetime.combine(d, datetime.min.time().replace(hour=10)),
                duration_minutes=60, note="",
            ))
        db.session.commit()
        assert _streak(user.id) == 2


class TestBestWeekday:
    def test_no_sessions_returns_none(self, make_user):
        assert _best_weekday(make_user("alice").id) is None

    def test_returns_weekday_with_most_minutes(self, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        task = _scored_task(user, subj, 60, 60)
        StudySession.query.delete()
        # Pick a known Monday: 2026-01-05 was a Monday.
        monday = datetime(2026, 1, 5, 9)
        wednesday = datetime(2026, 1, 7, 9)
        # Wednesday gets more minutes
        db.session.add(StudySession(
            user_id=user.id, task_id=task.id,
            started_at=monday, ended_at=monday + timedelta(minutes=30),
            duration_minutes=30, note="",
        ))
        db.session.add(StudySession(
            user_id=user.id, task_id=task.id,
            started_at=wednesday, ended_at=wednesday + timedelta(minutes=120),
            duration_minutes=120, note="",
        ))
        db.session.commit()
        best = _best_weekday(user.id)
        assert best["label"] == "Wednesday"
        assert best["minutes"] == 120


class TestBySubject:
    def test_returns_done_tasks_only(self, make_user, make_subject):
        user = make_user("alice")
        maths = make_subject(user, name="Maths")
        biology = make_subject(user, name="Biology")
        _scored_task(user, maths, 60, 90)
        _scored_task(user, maths, 60, 80)
        _scored_task(user, biology, 60, 100)

        rows = _by_subject(user.id)
        assert len(rows) == 2
        # Sorted heaviest first.
        assert rows[0]["name"] == "Maths"  # 170 total > 100
        assert rows[0]["task_count"] == 2
        assert rows[0]["total_minutes"] == 170
        assert rows[0]["avg_minutes"] == 85.0
