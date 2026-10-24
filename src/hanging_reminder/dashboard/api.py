"""JSON API behind the web dashboard – routing only, no networking.

:meth:`DashboardApi.handle` runs on the Qt main thread (the server hands
requests over, see :mod:`server`), so it can call straight into the app:
completing a task from the browser celebrates on screen exactly like a
tick in the mission panel.

The *app* is the :class:`~hanging_reminder.app.HangingReminderApp` – or any
object with the same small surface (tests use a fake):
``repository``, ``focus``, ``config``, ``can_undo``, ``add_parsed_task``,
``complete_tasks``, ``snooze_tasks``, ``undo_completion``,
``tasks_changed_externally``, ``start_focus``, ``stop_focus``.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from hanging_reminder import __version__
from hanging_reminder.tasks.models import Task
from hanging_reminder.tasks.nlp import describe_deadline, parse_task_text
from hanging_reminder.tasks.stats import summary_from_repository

Response = Tuple[int, Dict[str, Any]]

PRIORITIES = ("low", "normal", "high")
MAX_TITLE = 200
MAX_NOTES = 2000
_TASK_PATH = re.compile(r"^/api/tasks/(\d+)(?:/(complete|snooze))?$")


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat(timespec="minutes") if value is not None else None


def task_json(task: Task, now: datetime) -> Dict[str, Any]:
    due_in = (task.deadline - now).total_seconds() if task.deadline else None
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.description,
        "priority": task.priority,
        "deadline": _iso(task.deadline),
        "deadline_label": describe_deadline(task.deadline, now) if task.deadline else "",
        "overdue": due_in is not None and due_in < 0,
        "due_soon": due_in is not None and 0 <= due_in < 2 * 3600,
        "snoozed_until": _iso(task.snoozed_until) if task.is_snoozed(now) else None,
        "created_at": _iso(task.created_at),
    }


def _text(body: Dict[str, Any], key: str, limit: int, required: bool = False) -> Optional[str]:
    value = body.get(key)
    if value is None:
        if required:
            raise ApiError(400, f"'{key}' is required")
        return None
    if not isinstance(value, str):
        raise ApiError(400, f"'{key}' must be text")
    value = value.strip()
    if required and not value:
        raise ApiError(400, f"'{key}' can't be empty")
    return value[:limit]


class DashboardApi:
    def __init__(self, app, clock=datetime.now) -> None:
        self._app = app
        self._clock = clock

    def handle(self, method: str, path: str, query: Dict[str, str],
               body: Dict[str, Any]) -> Response:
        try:
            return self._route(method, path, query, body)
        except ApiError as exc:
            return exc.status, {"error": str(exc)}

    # ------------------------------------------------------------------

    def _route(self, method: str, path: str, query: Dict[str, str],
               body: Dict[str, Any]) -> Response:
        repo = self._app.repository
        if path == "/api/state" and method == "GET":
            return 200, self._state()
        if path == "/api/tasks":
            if method == "GET":
                return 200, self._tasks()
            if method == "POST":
                return self._add(body)
        if path == "/api/parse" and method == "GET":
            return 200, self._parse(query.get("text", ""))
        if path == "/api/undo" and method == "POST":
            restored = self._app.undo_completion()
            return 200, {"restored": restored, **self._tasks()}
        if path == "/api/stats" and method == "GET":
            return 200, self._stats()
        if path == "/api/focus" and method == "GET":
            return 200, self._focus()
        if path == "/api/focus/start" and method == "POST":
            task_id = body.get("task_id")
            if task_id is not None and (not isinstance(task_id, int) or repo.get(task_id) is None):
                raise ApiError(404, "No such task")
            self._app.start_focus(task_id)
            return 200, self._focus()
        if path == "/api/focus/stop" and method == "POST":
            self._app.stop_focus()
            return 200, self._focus()

        match = _TASK_PATH.match(path)
        if match:
            task_id, action = int(match.group(1)), match.group(2)
            if repo.get(task_id) is None:
                raise ApiError(404, "No such task")
            if action == "complete" and method == "POST":
                self._app.complete_tasks([task_id])
                return 200, self._tasks()
            if action == "snooze" and method == "POST":
                minutes = body.get("minutes", 10)
                if not isinstance(minutes, int) or not (-1 <= minutes <= 7 * 24 * 60) or minutes == 0:
                    raise ApiError(400, "'minutes' must be 1–10080, or -1 for tomorrow 9:00")
                self._app.snooze_tasks([task_id], minutes)
                return 200, self._tasks()
            if action is None and method == "PATCH":
                return self._edit(task_id, body)
            if action is None and method == "DELETE":
                repo.delete(task_id)
                self._app.tasks_changed_externally()
                return 200, self._tasks()
        raise ApiError(404 if method in ("GET", "POST", "PATCH", "DELETE") else 405, "Not found")

    # ------------------------------------------------------------------

    def _state(self) -> Dict[str, Any]:
        return {"version": __version__, **self._tasks(), "stats": self._stats(),
                "focus": self._focus()}

    def _tasks(self) -> Dict[str, Any]:
        now = self._clock()
        tasks = self._app.repository.get_pending()
        return {"tasks": [task_json(t, now) for t in tasks], "can_undo": bool(self._app.can_undo)}

    def _parse(self, text: str) -> Dict[str, Any]:
        now = self._clock()
        parsed = parse_task_text(text[:MAX_TITLE], now)
        return {
            "title": parsed.title,
            "priority": parsed.priority,
            "deadline": _iso(parsed.deadline),
            "deadline_label": describe_deadline(parsed.deadline, now) if parsed.deadline else "",
        }

    def _add(self, body: Dict[str, Any]) -> Response:
        text = _text(body, "text", MAX_TITLE, required=True)
        parsed = parse_task_text(text, self._clock())
        if not parsed.title:
            raise ApiError(400, "The task needs a title")
        task_id = self._app.add_parsed_task(parsed)
        return 201, {"id": task_id, **self._tasks()}

    def _edit(self, task_id: int, body: Dict[str, Any]) -> Response:
        repo = self._app.repository
        task = repo.get(task_id)
        title = _text(body, "title", MAX_TITLE)
        if title is not None:
            if not title:
                raise ApiError(400, "'title' can't be empty")
            task.title = title
        notes = _text(body, "notes", MAX_NOTES)
        if notes is not None:
            task.description = notes
        if "priority" in body:
            if body["priority"] not in PRIORITIES:
                raise ApiError(400, "'priority' must be low, normal or high")
            task.priority = body["priority"]
        if "deadline" in body:
            value = body["deadline"]
            if value is None or value == "":
                task.deadline = None
            elif isinstance(value, str):
                try:
                    task.deadline = datetime.fromisoformat(value).replace(tzinfo=None)
                except ValueError:
                    raise ApiError(400, "'deadline' must be an ISO date-time") from None
            else:
                raise ApiError(400, "'deadline' must be an ISO date-time or null")
        repo.update(task)
        self._app.tasks_changed_externally()
        return 200, self._tasks()

    def _stats(self) -> Dict[str, Any]:
        summary = summary_from_repository(self._app.repository, self._clock().date())
        return {
            "streak": summary.streak,
            "done_today": summary.done_today,
            "done_week": summary.done_week,
            "focus_today_min": round(summary.focus_today_min),
            "focus_week_min": round(summary.focus_week_min),
            "days": [d.isoformat() for d in summary.days],
            "daily_done": summary.daily_done,
        }

    def _focus(self) -> Dict[str, Any]:
        focus = self._app.focus
        return {
            "state": focus.state,
            "remaining_s": focus.remaining_s(),
            "progress": round(focus.progress(), 4),
            "task_id": focus.task_id if focus.running else None,
            "task_title": focus.task_title if focus.running else "",
            "focus_minutes": int(self._app.config.focus_minutes),
        }
