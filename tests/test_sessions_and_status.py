"""Tests for the session-logging flow and the actual_minutes sync on completion."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from stride.extensions import db
from stride.models import Prediction, StudySession, Task, TaskType


def _make_pending_task(user, subject):
    coding = TaskType.query.filter_by(name="Coding").one()
    task = Task(
        user_id=user.id,
        subject_id=subject.id,
        type_id=coding.id,
        title="T",
        description="",
        complexity=3,
        predicted_minutes=180,
        status="pending",
        due_date=date.today() + timedelta(days=2),
        created_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.flush()
    db.session.add(Prediction(
        task_id=task.id, predicted_minutes=180, model_version="heuristic_v1",
    ))
    db.session.commit()
    return task


class TestSessionLogging:
    def test_log_session_via_form(self, client, make_user, make_subject, login):
        user = make_user("alice")
        subj = make_subject(user)
        task = _make_pending_task(user, subj)
        login("alice")
        response = client.post(
            f"/sessions/task/{task.id}/new",
            data={
                "started_at": "2026-05-05T09:00",
                "ended_at": "2026-05-05T09:45",
                "note": "warm-up",
                "submit": "x",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert task.sessions.count() == 1
        assert task.sessions.first().duration_minutes == 45

    def test_end_before_start_rejected(self, client, make_user, make_subject, login):
        user = make_user("alice")
        subj = make_subject(user)
        task = _make_pending_task(user, subj)
        login("alice")
        response = client.post(
            f"/sessions/task/{task.id}/new",
            data={
                "started_at": "2026-05-05T10:00",
                "ended_at": "2026-05-05T09:00",
                "note": "", "submit": "x",
            },
            follow_redirects=True,
        )
        assert b"End time must be after" in response.data
        assert task.sessions.count() == 0

    def test_session_longer_than_24h_rejected(self, client, make_user, make_subject, login):
        user = make_user("alice")
        subj = make_subject(user)
        task = _make_pending_task(user, subj)
        login("alice")
        response = client.post(
            f"/sessions/task/{task.id}/new",
            data={
                "started_at": "2026-05-05T08:00",
                "ended_at": "2026-05-06T09:00",  # 25 hours
                "note": "", "submit": "x",
            },
            follow_redirects=True,
        )
        assert b"more than 24" in response.data
        assert task.sessions.count() == 0

    def test_other_user_cannot_log_session(
        self, client, make_user, make_subject, login
    ):
        alice = make_user("alice")
        bob = make_user("bob")
        alice_subj = make_subject(alice)
        alice_task = _make_pending_task(alice, alice_subj)

        login("bob")
        response = client.post(
            f"/sessions/task/{alice_task.id}/new",
            data={
                "started_at": "2026-05-05T09:00",
                "ended_at": "2026-05-05T10:00",
                "note": "", "submit": "x",
            },
        )
        assert response.status_code == 404
        assert alice_task.sessions.count() == 0


class TestStatusTransitions:
    def test_marking_done_stamps_completed_at(self, client, make_user, make_subject, login):
        user = make_user("alice")
        subj = make_subject(user)
        task = _make_pending_task(user, subj)
        login("alice")
        client.post(f"/tasks/{task.id}/status", data={"status": "done"})
        refreshed = Task.query.get(task.id)
        assert refreshed.status == "done"
        assert refreshed.completed_at is not None

    def test_marking_done_syncs_actual_minutes(self, client, make_user, make_subject, login):
        user = make_user("alice")
        subj = make_subject(user)
        task = _make_pending_task(user, subj)
        # Two sessions totalling 150 min.
        for start, end in [("09:00", "10:00"), ("10:30", "12:00")]:
            db.session.add(StudySession(
                user_id=user.id, task_id=task.id,
                started_at=datetime.fromisoformat(f"2026-05-05T{start}"),
                ended_at=datetime.fromisoformat(f"2026-05-05T{end}"),
                duration_minutes=60 if start == "09:00" else 90,
                note="",
            ))
        db.session.commit()

        login("alice")
        client.post(f"/tasks/{task.id}/status", data={"status": "done"})
        pred = Prediction.query.filter_by(task_id=task.id).first()
        assert pred.actual_minutes == 150

    def test_reverting_done_clears_actual_minutes(
        self, client, make_user, make_subject, login
    ):
        user = make_user("alice")
        subj = make_subject(user)
        task = _make_pending_task(user, subj)
        db.session.add(StudySession(
            user_id=user.id, task_id=task.id,
            started_at=datetime(2026, 5, 5, 9),
            ended_at=datetime(2026, 5, 5, 10),
            duration_minutes=60, note="",
        ))
        db.session.commit()

        login("alice")
        client.post(f"/tasks/{task.id}/status", data={"status": "done"})
        # Now revert.
        client.post(f"/tasks/{task.id}/status", data={"status": "pending"})

        refreshed = Task.query.get(task.id)
        assert refreshed.completed_at is None
        pred = Prediction.query.filter_by(task_id=task.id).first()
        assert pred.actual_minutes is None

    def test_unknown_status_rejected(self, client, make_user, make_subject, login):
        user = make_user("alice")
        subj = make_subject(user)
        task = _make_pending_task(user, subj)
        login("alice")
        response = client.post(
            f"/tasks/{task.id}/status",
            data={"status": "imaginary"},
            follow_redirects=True,
        )
        assert b"Unknown status" in response.data
        assert Task.query.get(task.id).status == "pending"
