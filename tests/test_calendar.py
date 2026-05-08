"""Calendar view tests."""
from __future__ import annotations

from datetime import date, datetime

from stride.extensions import db
from stride.models import Task, TaskType


def _add_task_due(user, subject, due: date, title: str = "T"):
    coding = TaskType.query.filter_by(name="Coding").one()
    task = Task(
        user_id=user.id, subject_id=subject.id, type_id=coding.id,
        title=title, description="", complexity=3,
        predicted_minutes=60, status="pending",
        due_date=due, created_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()
    return task


class TestCalendar:
    def test_anonymous_redirects_to_login(self, client):
        response = client.get("/calendar/", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_renders_current_month(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.get("/calendar/")
        assert response.status_code == 200
        # Header includes Mon-Sun.
        for day in (b"Mon", b"Tue", b"Wed", b"Sun"):
            assert day in response.data

    def test_explicit_month(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.get("/calendar/2026/3")
        assert response.status_code == 200
        assert b"March 2026" in response.data

    def test_invalid_month_404(self, client, make_user, login):
        make_user("alice")
        login("alice")
        for path in ["/calendar/2026/0", "/calendar/2026/13", "/calendar/0/1"]:
            response = client.get(path)
            assert response.status_code == 404

    def test_task_appears_on_due_date(self, client, make_user, make_subject, login):
        user = make_user("alice")
        subj = make_subject(user)
        _add_task_due(user, subj, date(2026, 4, 15), title="Mid-month task")
        login("alice")
        response = client.get("/calendar/2026/4")
        assert response.status_code == 200
        assert b"Mid-month task" in response.data

    def test_other_users_tasks_not_shown(self, client, make_user, make_subject, login):
        alice = make_user("alice")
        bob = make_user("bob")
        alice_subj = make_subject(alice, name="A")
        bob_subj = make_subject(bob, name="B")
        _add_task_due(alice, alice_subj, date(2026, 4, 10), title="Alice task")
        _add_task_due(bob, bob_subj, date(2026, 4, 11), title="Bob task")

        login("alice")
        response = client.get("/calendar/2026/4")
        assert b"Alice task" in response.data
        assert b"Bob task" not in response.data

    def test_navigation_links(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.get("/calendar/2026/6")
        assert b"/calendar/2026/5" in response.data  # prev
        assert b"/calendar/2026/7" in response.data  # next
