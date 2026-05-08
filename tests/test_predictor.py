"""Tests for the heuristic and the regression predictor with sanity guards."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from stride.extensions import db
from stride.ml.predictor import (
    MAX_MINUTES,
    MIN_MINUTES,
    REGRESSION_OVER_HEURISTIC,
    heuristic_minutes,
    predict_minutes,
)
from stride.ml.trainer import (
    MIN_TRAINING_ROWS,
    load_model_for_user,
    train_model_for_user,
)
from stride.models import (
    Prediction,
    StudySession,
    Task,
    TaskType,
)


def _fake_task(type_name: str, **kw) -> SimpleNamespace:
    """Build a minimal duck-typed task for unit-testing the heuristic."""
    return SimpleNamespace(
        task_type=SimpleNamespace(name=type_name),
        target_words=kw.get("target_words"),
        target_pages=kw.get("target_pages"),
        complexity=kw.get("complexity", 3),
    )


class TestHeuristic:
    def test_reading_scales_with_pages(self):
        # 3 min × 20 pages × (0.7 + 0.15 × 3) = 3 × 20 × 1.15 = 69
        assert heuristic_minutes(_fake_task("Reading", target_pages=20)) == 69

    def test_essay_scales_with_words(self):
        # 30 × (1500/100) × 1.15 = 30 × 15 × 1.15 = 517.5 → rounds to 518
        assert heuristic_minutes(
            _fake_task("Essay", target_words=1500)
        ) == pytest.approx(518, abs=1)

    def test_problem_set_linear_in_complexity(self):
        # 60 × c
        assert heuristic_minutes(_fake_task("Problem Set", complexity=3)) == 180
        assert heuristic_minutes(_fake_task("Problem Set", complexity=5)) == 300

    def test_coding_uses_higher_base(self):
        # 90 × c
        assert heuristic_minutes(_fake_task("Coding", complexity=4)) == 360

    def test_revision_lower_base(self):
        assert heuristic_minutes(_fake_task("Revision", complexity=2)) == 90

    def test_other_default_base(self):
        assert heuristic_minutes(_fake_task("Other", complexity=5)) == 300

    def test_floor_clamps_below_minimum(self):
        # 1 page, complexity 1 → 3 × 1 × 0.85 = 2.55 → clamps to 15
        assert heuristic_minutes(_fake_task("Reading", target_pages=1, complexity=1)) == \
            MIN_MINUTES

    def test_complexity_clamped_to_5(self):
        # complexity > 5 should be treated as 5 (90 × 5 = 450), not e.g. 900
        result = heuristic_minutes(_fake_task("Coding", complexity=10))
        assert result == 450

    def test_cap_does_not_exceed_max(self):
        # Essay with 100k words → very large, should cap at 12 hours
        result = heuristic_minutes(_fake_task("Essay", target_words=100_000, complexity=5))
        assert result == MAX_MINUTES

    def test_unknown_type_falls_back_to_60_base(self):
        result = heuristic_minutes(_fake_task("ZZZUnknownType", complexity=3))
        assert result == 180  # 60 × 3


class TestRegressionTraining:
    def _build_completed_history(self, db_session, user, subject, task_type, n_rows: int):
        """Insert `n_rows` completed Coding tasks with known actual_minutes."""
        for i in range(n_rows):
            complexity = (i % 5) + 1
            t = Task(
                user_id=user.id,
                subject_id=subject.id,
                type_id=task_type.id,
                title=f"Old {i}",
                description="practice",
                complexity=complexity,
                predicted_minutes=90 * complexity,
                status="done",
                due_date=date.today() - timedelta(days=10 - i),
                created_at=datetime.utcnow() - timedelta(days=10 - i),
                completed_at=datetime.utcnow() - timedelta(days=9 - i),
            )
            db_session.add(t)
            db_session.flush()
            actual = int(90 * complexity * 1.2)  # systematic 20% slowdown
            db_session.add(StudySession(
                user_id=user.id, task_id=t.id,
                started_at=datetime.utcnow() - timedelta(days=10 - i),
                ended_at=(
                    datetime.utcnow() - timedelta(days=10 - i)
                    + timedelta(minutes=actual)
                ),
                duration_minutes=actual, note="",
            ))
            db_session.add(Prediction(
                task_id=t.id, predicted_minutes=90 * complexity,
                actual_minutes=actual, model_version="heuristic_v1",
            ))
        db_session.commit()

    def test_below_threshold_returns_none(self, app, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        coding = TaskType.query.filter_by(name="Coding").one()
        # Below MIN_TRAINING_ROWS
        self._build_completed_history(db.session, user, subj, coding,
                                      n_rows=MIN_TRAINING_ROWS - 1)
        assert train_model_for_user(user.id) is None

    def test_above_threshold_returns_pipeline(self, app, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        coding = TaskType.query.filter_by(name="Coding").one()
        self._build_completed_history(db.session, user, subj, coding,
                                      n_rows=MIN_TRAINING_ROWS + 2)
        pipe = train_model_for_user(user.id)
        assert pipe is not None
        # Persisted to disk.
        assert load_model_for_user(user.id) is not None

    def test_trained_model_learns_user_bias(self, app, make_user, make_subject):
        """A user who is ~20% slower than the heuristic should get higher predictions."""
        user = make_user("alice")
        subj = make_subject(user)
        coding = TaskType.query.filter_by(name="Coding").one()
        self._build_completed_history(db.session, user, subj, coding, n_rows=8)

        train_model_for_user(user.id)

        # Build a new pending task at complexity=3 — heuristic = 270
        new_task = Task(
            user_id=user.id, subject_id=subj.id, type_id=coding.id,
            title="new", description="more", complexity=3,
            predicted_minutes=0, status="pending",
            due_date=date.today() + timedelta(days=5),
            created_at=datetime.utcnow(),
        )
        new_task.task_type = coding
        minutes, version = predict_minutes(new_task, user)

        assert version == "regression_v1"
        # Should land somewhere between heuristic and observed actual
        # (270 and ~324). Allow generous tolerance for noise in the small fit.
        assert 270 <= minutes <= 400, (
            f"regression should learn the slowdown, got {minutes} min"
        )


class TestSanityGuards:
    def _patched_loader(self, monkeypatch, return_value: float):
        """Make load_model_for_user return a stub pipeline returning a fixed value."""
        class FakePipe:
            def predict(self, X):
                return [return_value]

        monkeypatch.setattr(
            "stride.ml.trainer.load_model_for_user",
            lambda uid: FakePipe(),
        )

    def _new_task(self, app, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        coding = TaskType.query.filter_by(name="Coding").one()
        task = Task(
            user_id=user.id, subject_id=subj.id, type_id=coding.id,
            title="t", description="x", complexity=3,
            predicted_minutes=0, status="pending",
            due_date=date.today() + timedelta(days=3),
            created_at=datetime.utcnow(),
        )
        task.task_type = coding
        return task, user

    def test_giant_prediction_falls_back_to_heuristic(
        self, app, make_user, make_subject, monkeypatch
    ):
        task, user = self._new_task(app, make_user, make_subject)
        # Heuristic = 270; force regression to return 5x heuristic
        self._patched_loader(monkeypatch, 270 * REGRESSION_OVER_HEURISTIC * 2)
        minutes, version = predict_minutes(task, user)
        assert version == "heuristic_v1"
        assert minutes == heuristic_minutes(task)

    def test_sub_floor_prediction_falls_back(self, app, make_user, make_subject, monkeypatch):
        task, user = self._new_task(app, make_user, make_subject)
        self._patched_loader(monkeypatch, MIN_MINUTES - 1)
        _, version = predict_minutes(task, user)
        assert version == "heuristic_v1"

    def test_nan_prediction_falls_back(self, app, make_user, make_subject, monkeypatch):
        task, user = self._new_task(app, make_user, make_subject)
        self._patched_loader(monkeypatch, math.nan)
        _, version = predict_minutes(task, user)
        assert version == "heuristic_v1"

    def test_inf_prediction_falls_back(self, app, make_user, make_subject, monkeypatch):
        task, user = self._new_task(app, make_user, make_subject)
        self._patched_loader(monkeypatch, math.inf)
        _, version = predict_minutes(task, user)
        assert version == "heuristic_v1"

    def test_no_pickled_model_falls_back(self, app, make_user, make_subject):
        task, user = self._new_task(app, make_user, make_subject)
        # No model has been trained — should land on the heuristic.
        _, version = predict_minutes(task, user)
        assert version == "heuristic_v1"
