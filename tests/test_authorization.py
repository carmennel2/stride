"""Cross-user isolation tests.

The authorisation contract is: every query that touches user data is
scoped by user_id, and ID-based lookups use first_or_404() so attempts
to access another user's row return 404, not 403, leaking nothing.
"""
from __future__ import annotations

from datetime import date, timedelta

from stride.extensions import db
from stride.models import Subject, Task, TaskType


def _add_task(user, subject, **kw):
    coding = TaskType.query.filter_by(name="Coding").one()
    task = Task(
        user_id=user.id,
        subject_id=subject.id,
        type_id=coding.id,
        title=kw.get("title", "T"),
        description="",
        complexity=3,
        predicted_minutes=60,
        status="pending",
        due_date=date.today() + timedelta(days=1),
    )
    db.session.add(task)
    db.session.commit()
    return task


class TestSubjectIsolation:
    def test_user_cannot_see_other_users_subjects(self, client, make_user, make_subject, login):
        alice = make_user("alice")
        bob = make_user("bob")
        make_subject(alice, name="Maths")
        make_subject(bob, name="Biology")

        login("alice")
        response = client.get("/subjects/")
        assert b"Maths" in response.data
        assert b"Biology" not in response.data

    def test_user_cannot_edit_other_users_subject(self, client, make_user, make_subject, login):
        alice = make_user("alice")
        bob = make_user("bob")
        alice_maths = make_subject(alice, name="Maths")

        login("bob")
        response = client.get(f"/subjects/{alice_maths.id}/edit")
        assert response.status_code == 404

    def test_user_cannot_delete_other_users_subject(self, client, make_user, make_subject, login):
        alice = make_user("alice")
        bob = make_user("bob")
        alice_maths = make_subject(alice, name="Maths")

        login("bob")
        response = client.post(f"/subjects/{alice_maths.id}/delete")
        assert response.status_code == 404
        assert Subject.query.get(alice_maths.id) is not None, \
            "alice's subject must still exist"

    def test_per_user_subject_name_uniqueness(self, client, make_user, make_subject, login, db):
        """Two users can both have a 'Maths' subject."""
        alice = make_user("alice")
        bob = make_user("bob")
        make_subject(alice, name="Maths")

        login("bob")
        response = client.post(
            "/subjects/new",
            data={"name": "Maths", "color": "#10b981", "submit": "x"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert Subject.query.filter_by(user_id=bob.id, name="Maths").count() == 1

    def test_same_user_cannot_duplicate_subject_name(self, client, make_user, make_subject, login):
        alice = make_user("alice")
        make_subject(alice, name="Maths")
        login("alice")
        response = client.post(
            "/subjects/new",
            data={"name": "Maths", "color": "#10b981", "submit": "x"},
        )
        assert b"already have a subject with that name" in response.data


class TestTaskIsolation:
    def test_user_cannot_view_other_users_task(self, client, make_user, make_subject, login):
        alice = make_user("alice")
        bob = make_user("bob")
        alice_subj = make_subject(alice)
        alice_task = _add_task(alice, alice_subj, title="Alice's task")

        login("bob")
        response = client.get(f"/tasks/{alice_task.id}")
        assert response.status_code == 404

    def test_user_cannot_edit_other_users_task(self, client, make_user, make_subject, login):
        alice = make_user("alice")
        bob = make_user("bob")
        alice_subj = make_subject(alice)
        alice_task = _add_task(alice, alice_subj)

        login("bob")
        response = client.get(f"/tasks/{alice_task.id}/edit")
        assert response.status_code == 404

    def test_user_cannot_change_other_users_task_status(
        self, client, make_user, make_subject, login
    ):
        alice = make_user("alice")
        bob = make_user("bob")
        alice_subj = make_subject(alice)
        alice_task = _add_task(alice, alice_subj)

        login("bob")
        response = client.post(
            f"/tasks/{alice_task.id}/status",
            data={"status": "done"},
        )
        assert response.status_code == 404

        # Confirm alice's task hasn't been touched.
        refreshed = Task.query.get(alice_task.id)
        assert refreshed.status == "pending"

    def test_forged_subject_id_in_new_task_is_rejected(
        self, client, make_user, make_subject, login, db
    ):
        """A user cannot create a task referencing another user's subject."""
        alice = make_user("alice")
        bob = make_user("bob")
        alice_subj = make_subject(alice, name="Maths")
        # Bob needs at least one of his own subjects to get past the no-subjects redirect.
        make_subject(bob, name="Bob's subject")

        login("bob")
        coding = TaskType.query.filter_by(name="Coding").one()
        response = client.post("/tasks/new", data={
            "title": "Forged",
            "description": "",
            "subject_id": str(alice_subj.id),  # not bob's!
            "type_id": str(coding.id),
            "complexity": "3",
            "target_words": "",
            "target_pages": "",
            "due_date": (date.today() + timedelta(days=1)).isoformat(),
            "submit": "x",
        })
        # The form's validate_subject_id rejects unknown choices before they hit the FK.
        # Either 200 with the form re-rendered (rejected) or no task created.
        assert Task.query.filter_by(title="Forged").count() == 0


class TestAnonymousAccess:
    def test_dashboard_redirects_to_login(self, client):
        response = client.get("/dashboard/", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_subjects_redirects_to_login(self, client):
        response = client.get("/subjects/", follow_redirects=False)
        assert response.status_code == 302

    def test_tasks_redirects_to_login(self, client):
        response = client.get("/tasks/", follow_redirects=False)
        assert response.status_code == 302

    def test_planner_redirects_to_login(self, client):
        response = client.get("/planner/", follow_redirects=False)
        assert response.status_code == 302

    def test_insights_redirects_to_login(self, client):
        response = client.get("/insights/", follow_redirects=False)
        assert response.status_code == 302
