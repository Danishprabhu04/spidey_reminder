"""SQLite-backed task repository with transaction support.

Persists tasks across application restarts.  All write operations are
wrapped in transactions so that failures do not lose in-memory state
silently.  Datetimes are stored as naive local ISO-8601 strings.

Completing a task removes it from ``tasks``; a copy goes into the
``completions`` history (for streaks/stats and Undo).
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .models import Task


# Columns added after the first release – migrated in on open
_MIGRATED_COLUMNS = {
    "snoozed_until": "TEXT",
    "reminded_at": "TEXT",
}

_TASK_COLUMNS = (
    "id, title, description, priority, deadline, completed, "
    "created_at, updated_at, completed_at, snoozed_until, reminded_at"
)

_PRIORITY_ORDER = (
    "CASE priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 WHEN 'low' THEN 3 ELSE 4 END"
)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def _row_to_task(row: tuple) -> Task:
    return Task(
        id=row[0],
        title=row[1],
        description=row[2] or "",
        priority=row[3] or "normal",
        deadline=_dt(row[4]),
        completed=bool(row[5]),
        created_at=_dt(row[6]) or datetime.now(),
        updated_at=_dt(row[7]) or datetime.now(),
        completed_at=_dt(row[8]),
        snoozed_until=_dt(row[9]),
        reminded_at=_dt(row[10]),
    )


class TaskRepository:
    """SQLite-backed task repository.

    Creates a local database at ``~/.local/share/spidey-sense/tasks.db``
    by default.  The schema is idempotent – calling ``initialise`` more
    than once is safe.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            from hanging_reminder import paths
            db_path = str(paths.data_dir() / "tasks.db")

        self._db_path: str = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create the tables if missing and migrate older databases."""
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                priority TEXT DEFAULT 'normal',
                deadline TEXT,
                completed INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        existing = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        for column, sql_type in _MIGRATED_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {column} {sql_type}")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                priority TEXT DEFAULT 'normal',
                deadline TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT NOT NULL
            )
            """
        )
        # Older versions kept completed tasks in the list – move them to history
        conn.execute(
            """
            INSERT INTO completions (task_id, title, description, priority, deadline,
                                     created_at, completed_at)
            SELECT id, title, description, priority, deadline, created_at,
                   COALESCE(completed_at, updated_at)
              FROM tasks WHERE completed = 1
            """
        )
        conn.execute("DELETE FROM tasks WHERE completed = 1")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS focus_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                minutes REAL NOT NULL,
                completed INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _conn_open(self) -> sqlite3.Connection:
        """Ensure a connection is open and return it."""
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            # Enable WAL mode for better concurrent read performance
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _conn_close(self) -> None:
        """Close the connection if we opened it ourselves."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _query(self, where: str, order: str, params: tuple = ()) -> List[Task]:
        conn = self._conn_open()
        rows = conn.execute(
            f"SELECT {_TASK_COLUMNS} FROM tasks WHERE {where} ORDER BY {order}", params
        ).fetchall()
        return [_row_to_task(row) for row in rows]

    # ---- save ----

    def save(self, task: Task) -> int:
        """Save a new task.  Returns the assigned database rowid.

        If a task with the same title already exists (case-insensitive),
        the existing row is updated instead.
        """
        conn = self._conn_open()
        try:
            # Check for existing task with same title
            row = conn.execute(
                "SELECT id FROM tasks WHERE LOWER(title) = LOWER(?) AND completed = 0",
                (task.title,),
            ).fetchone()

            now_iso = datetime.now().isoformat()

            if row:
                # Update existing incomplete task
                conn.execute(
                    """
                    UPDATE tasks
                       SET title = ?, description = ?, priority = ?, deadline = ?,
                           updated_at = ?, reminded_at = NULL
                     WHERE id = ?
                    """,
                    (task.title, task.description, task.priority, _iso(task.deadline),
                     now_iso, row[0]),
                )
                task.id = row[0]
            else:
                # Insert new task
                result = conn.execute(
                    """
                    INSERT INTO tasks (title, description, priority, deadline,
                                       completed, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 0, ?, ?)""",
                    (task.title, task.description, task.priority, _iso(task.deadline),
                     now_iso, now_iso),
                )
                task.id = result.lastrowid

            conn.commit()
            return task.id
        except sqlite3.Error as exc:
            # Log but don't crash – the in-memory state is still valid
            import sys
            print(f"[TaskRepository] DB error: {exc}", file=sys.stderr)
            raise

    # ---- update ----

    def update(self, task: Task) -> None:
        """Write an edited task (title, notes, priority, deadline) by id.

        Changing the deadline re-arms its due-time reminder.
        """
        conn = self._conn_open()
        old = conn.execute("SELECT deadline FROM tasks WHERE id = ?", (task.id,)).fetchone()
        if old is None:
            return
        rearm = old[0] != _iso(task.deadline)
        conn.execute(
            f"""
            UPDATE tasks
               SET title = ?, description = ?, priority = ?, deadline = ?, updated_at = ?
                   {", reminded_at = NULL, snoozed_until = NULL" if rearm else ""}
             WHERE id = ?
            """,
            (task.title, task.description, task.priority, _iso(task.deadline),
             datetime.now().isoformat(), task.id),
        )
        conn.commit()

    # ---- queries ----

    def get(self, task_id: int) -> Optional[Task]:
        tasks = self._query("id = ?", "id", (task_id,))
        return tasks[0] if tasks else None

    def get_pending(self) -> List[Task]:
        """Return all non-completed tasks, ordered by priority then creation."""
        return self._query("completed = 0", f"{_PRIORITY_ORDER}, created_at ASC")

    def get_due_unreminded(self, now: datetime) -> List[Task]:
        """Pending tasks whose deadline has passed and that weren't announced yet."""
        return [
            t for t in self._query(
                "completed = 0 AND deadline IS NOT NULL AND reminded_at IS NULL",
                "deadline ASC",
            )
            if t.deadline <= now
        ]

    def get_snooze_expired(self, now: datetime) -> List[Task]:
        """Pending tasks whose snooze has just run out."""
        return [
            t for t in self._query(
                "completed = 0 AND snoozed_until IS NOT NULL", "snoozed_until ASC"
            )
            if t.snoozed_until <= now
        ]

    # ---- complete (removes the task, keeps history) ----

    def complete(self, task_id: int, when: Optional[datetime] = None) -> Optional[int]:
        """Finish a task: delete it and record it in the history.

        Returns the history id (for :meth:`undo_complete`), or None if the
        task doesn't exist.
        """
        task = self.get(task_id)
        if task is None:
            return None
        conn = self._conn_open()
        cursor = conn.execute(
            """
            INSERT INTO completions (task_id, title, description, priority, deadline,
                                     created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (task.id, task.title, task.description, task.priority, _iso(task.deadline),
             _iso(task.created_at), _iso(when or datetime.now())),
        )
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cursor.lastrowid

    def undo_complete(self, completion_id: int) -> Optional[int]:
        """Bring a just-completed task back. Returns its (new) task id."""
        conn = self._conn_open()
        row = conn.execute(
            "SELECT title, description, priority, deadline, created_at FROM completions WHERE id = ?",
            (completion_id,),
        ).fetchone()
        if row is None:
            return None
        now_iso = datetime.now().isoformat()
        cursor = conn.execute(
            """
            INSERT INTO tasks (title, description, priority, deadline, completed,
                               created_at, updated_at, reminded_at)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """,
            # Don't re-fire a due alert that was already shown
            (row[0], row[1], row[2], row[3], row[4], now_iso,
             now_iso if row[3] and row[3] <= now_iso else None),
        )
        conn.execute("DELETE FROM completions WHERE id = ?", (completion_id,))
        conn.commit()
        return cursor.lastrowid

    # ---- reminders ----

    def snooze(self, task_id: int, until: datetime) -> None:
        """Silence a task's reminders until *until*."""
        conn = self._conn_open()
        conn.execute(
            "UPDATE tasks SET snoozed_until = ?, updated_at = ? WHERE id = ?",
            (_iso(until), datetime.now().isoformat(), task_id),
        )
        conn.commit()

    def mark_reminded(self, task_id: int, when: Optional[datetime] = None) -> None:
        """Record that the due-time alert was shown (clears any snooze)."""
        conn = self._conn_open()
        conn.execute(
            "UPDATE tasks SET reminded_at = ?, snoozed_until = NULL WHERE id = ?",
            (_iso(when or datetime.now()), task_id),
        )
        conn.commit()

    # ---- delete ----

    def delete(self, task_id: int) -> None:
        """Permanently delete a task from the database."""
        conn = self._conn_open()
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()

    # ---- count pending ----

    def count_pending(self) -> int:
        """Return the number of pending tasks."""
        conn = self._conn_open()
        row = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE completed = 0"
        ).fetchone()
        return row[0]

    def count_overdue(self, now: Optional[datetime] = None) -> int:
        """Number of pending tasks past their deadline."""
        now = now or datetime.now()
        return sum(1 for t in self.get_pending() if t.deadline is not None and t.deadline < now)

    # ---- stats ----

    def completions_by_day(self, days: int, today: Optional[date] = None) -> Dict[date, int]:
        """Completed-task counts for each of the last *days* days (incl. today)."""
        today = today or date.today()
        start = today - timedelta(days=days - 1)
        counts = {start + timedelta(days=i): 0 for i in range(days)}
        conn = self._conn_open()
        rows = conn.execute(
            "SELECT substr(completed_at, 1, 10), COUNT(*) FROM completions "
            "WHERE completed_at >= ? GROUP BY 1",
            (start.isoformat(),),
        ).fetchall()
        for day_iso, count in rows:
            day = date.fromisoformat(day_iso)
            if day in counts:
                counts[day] = count
        return counts

    def completion_days(self) -> List[date]:
        """Every distinct day on which at least one task was completed."""
        conn = self._conn_open()
        rows = conn.execute(
            "SELECT DISTINCT substr(completed_at, 1, 10) FROM completions"
        ).fetchall()
        return sorted(date.fromisoformat(r[0]) for r in rows)

    # ---- focus sessions ----

    def add_focus_session(self, task_id: Optional[int], started_at: datetime,
                          ended_at: datetime, completed: bool) -> None:
        minutes = max(0.0, (ended_at - started_at).total_seconds() / 60.0)
        conn = self._conn_open()
        conn.execute(
            "INSERT INTO focus_sessions (task_id, started_at, ended_at, minutes, completed) "
            "VALUES (?, ?, ?, ?, ?)",
            (task_id, started_at.isoformat(), ended_at.isoformat(), minutes, int(completed)),
        )
        conn.commit()

    def focus_minutes_by_day(self, days: int, today: Optional[date] = None) -> Dict[date, float]:
        today = today or date.today()
        start = today - timedelta(days=days - 1)
        totals = {start + timedelta(days=i): 0.0 for i in range(days)}
        conn = self._conn_open()
        rows = conn.execute(
            "SELECT substr(started_at, 1, 10), SUM(minutes) FROM focus_sessions "
            "WHERE started_at >= ? GROUP BY 1",
            (start.isoformat(),),
        ).fetchall()
        for day_iso, minutes in rows:
            day = date.fromisoformat(day_iso)
            if day in totals:
                totals[day] = float(minutes)
        return totals

    # ---- close ----

    def close(self) -> None:
        """Close the database connection."""
        self._conn_close()
