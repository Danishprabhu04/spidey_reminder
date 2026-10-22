"""SQLite-backed task repository with transaction support.

Persists tasks across application restarts.  All write operations are
wrapped in transactions so that failures do not lose in-memory state
silently.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import Task


class TaskRepository:
    """SQLite-backed task repository.

    Creates a local database at ``~/.local/share/spidey-sense/tasks.db``
    by default.  The schema is idempotent – calling ``initialise`` more
    than once is safe.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            base = Path.home() / ".local" / "share" / "spidey-sense"
            base.mkdir(parents=True, exist_ok=True)
            db_path = str(base / "tasks.db")

        self._db_path: str = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create the tasks table if it does not already exist."""
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
                           updated_at = ?
                     WHERE id = ?
                    """,
                    (task.title, task.description, task.priority, task.deadline, now_iso, row[0]),
                )
                task.id = row[0]
            else:
                # Insert new task
                result = conn.execute(
                    """
                    INSERT INTO tasks (title, description, priority, deadline,
                                       completed, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 0, ?, ?)""",
                    (task.title, task.description, task.priority, task.deadline,
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

    # ---- get pending ----

    def get_pending(self) -> List[Task]:
        """Return all non-completed tasks, ordered by priority then creation."""
        conn = self._conn_open()
        rows = conn.execute(
            """
            SELECT id, title, description, priority, deadline, created_at
            FROM tasks
            WHERE completed = 0
            ORDER BY
                CASE priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
                created_at ASC
            """
        ).fetchall()

        tasks: List[Task] = []
        for row in rows:
            created = datetime.fromisoformat(row[5]) if row[5] else datetime.now()
            tasks.append(Task(
                id=row[0],
                title=row[1],
                description=row[2] or "",
                priority=row[3] or "normal",
                deadline=datetime.fromisoformat(row[4]) if row[4] else None,
                created_at=created,
            ))
        return tasks

    # ---- get completed ----

    def get_completed(self) -> List[Task]:
        """Return all completed tasks, most recently completed first."""
        conn = self._conn_open()
        rows = conn.execute(
            """
            SELECT id, title, description, priority, deadline, created_at, completed_at
            FROM tasks
            WHERE completed = 1
            ORDER BY completed_at DESC
            """
        ).fetchall()

        tasks: List[Task] = []
        for row in rows:
            created = datetime.fromisoformat(row[5]) if row[5] else datetime.now()
            tasks.append(Task(
                id=row[0],
                title=row[1],
                description=row[2] or "",
                priority=row[3] or "normal",
                deadline=datetime.fromisoformat(row[4]) if row[4] else None,
                completed=True,
                created_at=created,
                completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
            ))
        return tasks

    # ---- toggle complete ----

    def toggle_complete(self, task_id: int) -> None:
        """Toggle a task's completion status.

        If the task becomes completed, ``completed_at`` is set to the
        current timestamp.  If it was already completed, it is marked
        incomplete and ``completed_at`` is cleared.
        """
        conn = self._conn_open()
        now_iso = datetime.now().isoformat()

        # Check current state
        row = conn.execute(
            "SELECT completed, completed_at FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            return  # silently ignore missing task

        currently_completed = row[0] == 1
        if currently_completed:
            # Mark as incomplete
            conn.execute(
                """
                UPDATE tasks
                   SET completed = 0,
                       updated_at = ?,
                       completed_at = NULL
                 WHERE id = ?
                """,
                (now_iso, task_id),
            )
        else:
            # Mark as complete
            conn.execute(
                """
                UPDATE tasks
                   SET completed = 1,
                       updated_at = ?,
                       completed_at = ?
                 WHERE id = ?
                """,
                (now_iso, now_iso, task_id),
            )

        conn.commit()

    # ---- delete ----

    def delete(self, task_id: int) -> None:
        """Permanently delete a task from the database."""
        conn = self._conn_open()
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()

    # ---- clear completed ----

    def clear_completed(self) -> int:
        """Remove all completed tasks.  Returns number of rows deleted."""
        conn = self._conn_open()
        cursor = conn.execute("DELETE FROM tasks WHERE completed = 1")
        conn.commit()
        return cursor.rowcount

    # ---- count pending ----

    def count_pending(self) -> int:
        """Return the number of pending (non-completed) tasks."""
        conn = self._conn_open()
        row = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE completed = 0"
        ).fetchone()
        return row[0]

    # ---- close ----

    def close(self) -> None:
        """Close the database connection."""
        self._conn_close()