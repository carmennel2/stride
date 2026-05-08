"""Tests for the planner's task-distribution algorithm."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from stride.extensions import db
from stride.models import StudySession, Task, TaskType
from stride.planner.routes import _build_plan


def _add_pending_task(user, subject, predicted_minutes: int, days_until_due: int):
    coding = TaskType.query.filter_by(name="Coding").one()
    task = Task(
        user_id=user.id,
        subject_id=subject.id,
        type_id=coding.id,
        title=f"Task due in {days_until_due}",
        description="",
        complexity=3,
        predicted_minutes=predicted_minutes,
        status="pending",
        due_date=date.today() + timedelta(days=days_until_due),
        created_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()
    return task


class TestPlanShape:
    def test_returns_horizon_plus_one_days(self, make_user):
        user = make_user("alice")
        plan = _build_plan(user.id, date.today(), horizon_days=14)
        # today + 14 future days
        assert len(plan["days"]) == 15

    def test_each_day_has_date_minutes_slots(self, make_user):
        user = make_user("alice")
        plan = _build_plan(user.id, date.today(), horizon_days=2)
        for day in plan["days"]:
            assert "date" in day
            assert "total_minutes" in day
            assert "slots" in day

    def test_no_open_tasks_zero_total(self, make_user):
        user = make_user("alice")
        plan = _build_plan(user.id, date.today(), horizon_days=14)
        assert plan["summary"]["total_minutes"] == 0
        assert plan["summary"]["open_task_count"] == 0


class TestDistribution:
    def test_distributes_evenly_across_due_window(self, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        # 300 minutes due in 4 days → spread across today + 4 = 5 days = 60/day
        _add_pending_task(user, subj, predicted_minutes=300, days_until_due=4)

        plan = _build_plan(user.id, date.today(), horizon_days=14)
        for i in range(5):
            assert plan["days"][i]["total_minutes"] == 60, (
                f"day {i} should have 60 min, got {plan['days'][i]['total_minutes']}"
            )
        for i in range(5, 15):
            assert plan["days"][i]["total_minutes"] == 0

    def test_total_minutes_match_predicted(self, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        _add_pending_task(user, subj, predicted_minutes=300, days_until_due=4)
        plan = _build_plan(user.id, date.today(), horizon_days=14)
        assert plan["summary"]["total_minutes"] == 300

    def test_logged_sessions_subtract_from_remaining(self, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        task = _add_pending_task(user, subj, predicted_minutes=300, days_until_due=4)
        # 100 of the 300 already logged
        db.session.add(StudySession(
            user_id=user.id, task_id=task.id,
            started_at=datetime.utcnow() - timedelta(hours=2),
            ended_at=datetime.utcnow() - timedelta(hours=2) + timedelta(minutes=100),
            duration_minutes=100, note="",
        ))
        db.session.commit()
        plan = _build_plan(user.id, date.today(), horizon_days=14)
        # 200 remaining over 5 days = 40/day
        assert plan["days"][0]["total_minutes"] == 40
        assert plan["summary"]["total_minutes"] == 200

    def test_overdue_task_collapses_to_today(self, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        # Due 3 days ago — should all schedule for today.
        _add_pending_task(user, subj, predicted_minutes=120, days_until_due=-3)
        plan = _build_plan(user.id, date.today(), horizon_days=14)
        assert plan["days"][0]["total_minutes"] == 120
        for i in range(1, 15):
            assert plan["days"][i]["total_minutes"] == 0

    def test_done_tasks_excluded(self, make_user, make_subject):
        user = make_user("alice")
        subj = make_subject(user)
        task = _add_pending_task(user, subj, predicted_minutes=60, days_until_due=2)
        task.status = "done"
        db.session.commit()
        plan = _build_plan(user.id, date.today(), horizon_days=14)
        assert plan["summary"]["total_minutes"] == 0
        assert plan["summary"]["open_task_count"] == 0

    def test_fully_logged_task_not_scheduled(self, make_user, make_subject):
        """Task whose sessions already exceed predicted_minutes shouldn't show up."""
        user = make_user("alice")
        subj = make_subject(user)
        task = _add_pending_task(user, subj, predicted_minutes=60, days_until_due=2)
        db.session.add(StudySession(
            user_id=user.id, task_id=task.id,
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow() + timedelta(minutes=80),
            duration_minutes=80, note="",
        ))
        db.session.commit()
        plan = _build_plan(user.id, date.today(), horizon_days=14)
        assert plan["summary"]["total_minutes"] == 0
        assert plan["summary"]["open_task_count"] == 0
