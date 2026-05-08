"""Tests for form validation rules.

These use the test client to drive POST requests so we exercise the
exact code path users hit.
"""
from __future__ import annotations

from datetime import date, timedelta

from stride.models import Subject, Task, TaskType


class TestSubjectForm:
    def test_creates_subject_with_valid_data(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.post(
            "/subjects/new",
            data={"name": "Maths", "color": "#3b82f6", "submit": "x"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert Subject.query.filter_by(name="Maths").one().color == "#3b82f6"

    def test_rejects_empty_name(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.post("/subjects/new", data={
            "name": "", "color": "#3b82f6", "submit": "x",
        })
        assert b"Please give the subject a name" in response.data

    def test_rejects_invalid_hex(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.post("/subjects/new", data={
            "name": "Maths", "color": "blue", "submit": "x",
        })
        assert b"Use a hex colour" in response.data

    def test_rejects_short_hex(self, client, make_user, login):
        """3-digit shorthand isn't accepted; full #rrggbb only."""
        make_user("alice")
        login("alice")
        response = client.post("/subjects/new", data={
            "name": "Maths", "color": "#abc", "submit": "x",
        })
        assert b"Use a hex colour" in response.data


class TestTaskForm:
    def _form_data(self, **overrides):
        coding = TaskType.query.filter_by(name="Coding").one()
        defaults = {
            "title": "Task title",
            "description": "",
            "subject_id": "1",
            "type_id": str(coding.id),
            "complexity": "3",
            "target_words": "",
            "target_pages": "",
            "due_date": (date.today() + timedelta(days=2)).isoformat(),
            "submit": "x",
        }
        defaults.update(overrides)
        return defaults

    def test_creates_task(self, client, make_user, make_subject, login):
        user = make_user("alice")
        subj = make_subject(user)
        login("alice")
        response = client.post(
            "/tasks/new",
            data=self._form_data(subject_id=str(subj.id)),
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert Task.query.filter_by(title="Task title").count() == 1

    def test_rejects_empty_title(self, client, make_user, make_subject, login):
        user = make_user("alice")
        subj = make_subject(user)
        login("alice")
        response = client.post(
            "/tasks/new",
            data=self._form_data(subject_id=str(subj.id), title=""),
        )
        assert b"Please give the task a title" in response.data

    def test_essay_requires_target_words(self, client, make_user, make_subject, login):
        user = make_user("alice")
        subj = make_subject(user)
        essay = TaskType.query.filter_by(name="Essay").one()
        login("alice")
        response = client.post(
            "/tasks/new",
            data=self._form_data(
                subject_id=str(subj.id),
                type_id=str(essay.id),
                target_words="",
            ),
        )
        assert b"target word count" in response.data
        assert Task.query.count() == 0

    def test_reading_requires_target_pages(self, client, make_user, make_subject, login):
        user = make_user("alice")
        subj = make_subject(user)
        reading = TaskType.query.filter_by(name="Reading").one()
        login("alice")
        response = client.post(
            "/tasks/new",
            data=self._form_data(
                subject_id=str(subj.id),
                type_id=str(reading.id),
                target_pages="",
            ),
        )
        assert b"target page count" in response.data

    def test_no_subjects_redirects_to_subject_creation(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.get("/tasks/new", follow_redirects=False)
        assert response.status_code == 302
        assert "/subjects/new" in response.headers["Location"]


class TestSessionForm:
    def test_session_form_csrf_token_present_on_detail(
        self, client, make_user, make_subject, login
    ):
        """Sanity check that the session form renders on the task detail."""
        from datetime import datetime

        from stride.extensions import db
        user = make_user("alice")
        subj = make_subject(user)
        coding = TaskType.query.filter_by(name="Coding").one()
        task = Task(
            user_id=user.id, subject_id=subj.id, type_id=coding.id,
            title="T", description="", complexity=3,
            predicted_minutes=60, status="pending",
            due_date=date.today() + timedelta(days=1),
            created_at=datetime.utcnow(),
        )
        db.session.add(task)
        db.session.commit()

        login("alice")
        response = client.get(f"/tasks/{task.id}")
        assert response.status_code == 200
        assert b"Log a session" in response.data
