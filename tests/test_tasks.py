"""Tests for the task management modules – SQLite-backed repository."""

from __future__ import annotations

import os
import tempfile
import pytest

from hanging_reminder.tasks.repository import TaskRepository
from hanging_reminder.tasks.models import Task


# Use a temporary database for each test
@pytest.fixture(autouse=True)
def isolated_db():
    """Provide an isolated temp DB for each test."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "tasks.db")
    # Override the repo path per test by creating a fresh repo
    repo = TaskRepository(db_path=db_path)
    yield repo
    # Cleanup is handled by the temp dir


class TestTaskRepository:
    """SQLite-backed task repository tests."""

    def test_save_and_get_pending(self, isolated_db):
        """Save a task and retrieve it as pending."""
        t = Task(title="Test task", priority="high")
        tid = isolated_db.save(t)
        assert t.id == tid

        pending = isolated_db.get_pending()
        assert len(pending) == 1
        assert pending[0].title == "Test task"
        assert pending[0].priority == "high"
        assert pending[0].completed is False

    def test_complete_removes_task(self, isolated_db):
        """Completing a task takes it off the list and records it in history."""
        tid = isolated_db.save(Task(title="My task"))
        isolated_db.save(Task(title="Other task"))

        completion_id = isolated_db.complete(tid)
        assert completion_id is not None
        assert [t.title for t in isolated_db.get_pending()] == ["Other task"]
        assert isolated_db.get(tid) is None
        assert isolated_db.count_pending() == 1
        assert isolated_db.complete(tid) is None  # already gone

    def test_undo_complete_restores_task(self, isolated_db):
        from datetime import datetime, timedelta
        due = datetime.now() + timedelta(days=1)
        tid = isolated_db.save(Task(title="Oops", priority="high", deadline=due))
        completion_id = isolated_db.complete(tid)

        new_id = isolated_db.undo_complete(completion_id)
        task = isolated_db.get(new_id)
        assert (task.title, task.priority, task.deadline) == ("Oops", "high", due)
        assert task.reminded_at is None  # future deadline – alert still pending
        assert isolated_db.completions_by_day(1) == {datetime.now().date(): 0}
        assert isolated_db.undo_complete(completion_id) is None

    def test_count_pending(self, isolated_db):
        """Count pending tasks."""
        assert isolated_db.count_pending() == 0

        for _ in range(3):
            isolated_db.save(Task(title=f"Task {_}"))

        assert isolated_db.count_pending() == 3

    def test_delete_task(self, isolated_db):
        """Delete a task permanently."""
        t = Task(title="To delete")
        tid = isolated_db.save(t)

        isolated_db.delete(tid)
        pending = isolated_db.get_pending()
        assert len(pending) == 0

    def test_persistence_across_restarts(self, isolated_db, tmpdir):
        """Tasks survive repository close/reopen."""
        t = Task(title="Persistent task")
        isolated_db.save(t)

        # Close and reopen (simulating app restart)
        isolated_db.close()
        # Reopen – note: the fixture creates a new repo each time,
        # so we test the underlying DB file survives
        new_repo = TaskRepository(db_path=isolated_db._db_path)
        pending = new_repo.get_pending()
        assert len(pending) == 1
        assert pending[0].title == "Persistent task"
        new_repo.close()


class TestTaskModel:
    """Task data model tests."""

    def test_task_creation(self):
        """Basic task creation with all fields."""
        t = Task(
            id=1,
            title="Sample task",
            description="A description",
            priority="normal",
            deadline=None,
            completed=False,
        )
        assert t.title == "Sample task"
        assert t.description == "A description"
        assert t.priority == "normal"
        assert t.id == 1
        assert t.completed is False
        assert t.is_overdue is False  # no deadline

    def test_task_overdue(self):
        """Task is overdue only when pending and past its deadline."""
        from datetime import datetime, timedelta
        past = Task(id=1, title="Late", deadline=datetime.now() - timedelta(minutes=1))
        future = Task(id=2, title="Later", deadline=datetime.now() + timedelta(hours=1))
        done = Task(id=3, title="Done", completed=True,
                    deadline=datetime.now() - timedelta(days=1))
        assert past.is_overdue is True
        assert future.is_overdue is False
        assert done.is_overdue is False
        assert Task(title="No deadline").is_overdue is False

    def test_task_priority_property(self):
        """Priority display property."""
        t = Task(id=1, title="High task", priority="high")
        assert t.display_priority == "HIGH"

        t2 = Task(id=2, title="Low task", priority="low")
        assert t2.display_priority == "LOW"

    def test_task_status_label(self):
        """Status label when not completed."""
        from datetime import datetime, timezone
        t = Task(id=1, title="New task")
        label = t.status_label
        assert "Pending" in label

        t.completed = True
        t.completed_at = datetime.now(timezone.utc)
        label = t.status_label
        assert "Completed" in label


class TestRepositoryPhase2:
    """Edit, reminders, stats and migration support."""

    def test_migrates_old_schema(self, tmp_path):
        import sqlite3
        db = tmp_path / "old.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
            " description TEXT DEFAULT '', priority TEXT DEFAULT 'normal', deadline TEXT,"
            " completed INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " completed_at TEXT)"
        )
        conn.execute(
            "INSERT INTO tasks (title, created_at, updated_at)"
            " VALUES ('old', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO tasks (title, completed, created_at, updated_at, completed_at)"
            " VALUES ('finished', 1, '2026-01-01T00:00:00', '2026-01-02T00:00:00',"
            " '2026-01-02T10:00:00')"
        )
        conn.commit()
        conn.close()

        repo = TaskRepository(str(db))
        tasks = repo.get_pending()
        assert [t.title for t in tasks] == ["old"]
        assert tasks[0].snoozed_until is None and tasks[0].reminded_at is None
        # Completed rows from the old list moved into the history
        from datetime import date
        assert repo.completion_days() == [date(2026, 1, 2)]

    def test_deadline_round_trip_and_update(self, isolated_db):
        from datetime import datetime
        due = datetime(2026, 11, 2, 17, 30)
        tid = isolated_db.save(Task(title="Report", deadline=due))
        task = isolated_db.get(tid)
        assert task.deadline == due

        task.title, task.priority, task.deadline = "Final report", "high", None
        isolated_db.update(task)
        task = isolated_db.get(tid)
        assert (task.title, task.priority, task.deadline) == ("Final report", "high", None)

    def test_due_unreminded_and_snooze(self, isolated_db):
        from datetime import datetime, timedelta
        now = datetime(2026, 10, 23, 12, 0)
        due_id = isolated_db.save(Task(title="Due", deadline=now - timedelta(minutes=5)))
        isolated_db.save(Task(title="Later", deadline=now + timedelta(hours=2)))

        assert [t.id for t in isolated_db.get_due_unreminded(now)] == [due_id]
        isolated_db.mark_reminded(due_id, now)
        assert isolated_db.get_due_unreminded(now) == []

        isolated_db.snooze(due_id, now + timedelta(minutes=10))
        assert isolated_db.get(due_id).is_snoozed(now)
        assert isolated_db.get_snooze_expired(now) == []
        expired = isolated_db.get_snooze_expired(now + timedelta(minutes=11))
        assert [t.id for t in expired] == [due_id]

    def test_editing_deadline_rearms_reminder(self, isolated_db):
        from datetime import datetime, timedelta
        now = datetime(2026, 10, 23, 12, 0)
        tid = isolated_db.save(Task(title="Call", deadline=now))
        isolated_db.mark_reminded(tid, now)
        task = isolated_db.get(tid)
        task.deadline = now + timedelta(hours=1)
        isolated_db.update(task)
        assert isolated_db.get(tid).reminded_at is None

    def test_completions_and_focus_by_day(self, isolated_db):
        from datetime import date, datetime
        for title in ("a", "b"):
            isolated_db.complete(isolated_db.save(Task(title=title)))
        today = date.today()
        counts = isolated_db.completions_by_day(7)
        assert len(counts) == 7 and counts[today] == 2
        assert isolated_db.completion_days() == [today]

        start = datetime.combine(today, datetime.min.time()).replace(hour=9)
        isolated_db.add_focus_session(None, start, start.replace(minute=25), True)
        assert isolated_db.focus_minutes_by_day(7)[today] == 25.0

    def test_count_overdue(self, isolated_db):
        from datetime import datetime, timedelta
        isolated_db.save(Task(title="late", deadline=datetime.now() - timedelta(hours=1)))
        isolated_db.save(Task(title="fine", deadline=datetime.now() + timedelta(hours=1)))
        assert isolated_db.count_overdue() == 1
