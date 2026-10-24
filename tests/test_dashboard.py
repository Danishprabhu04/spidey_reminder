"""Web dashboard: JSON API routing and the local server's safety checks."""

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import pytest

from hanging_reminder.config import AppConfig
from hanging_reminder.dashboard.api import DashboardApi
from hanging_reminder.dashboard.server import DashboardServer, MainThreadDispatcher
from hanging_reminder.focus.session import FocusSession
from hanging_reminder.tasks.models import Task
from hanging_reminder.tasks.repository import TaskRepository

NOW = datetime(2026, 10, 24, 10, 0)


class FakeApp:
    """The slice of HangingReminderApp the dashboard API uses."""

    def __init__(self, repo):
        self.repository = repo
        self.config = AppConfig()
        self.focus = FocusSession(clock=lambda: NOW, auto_poll=False)
        self._undo = []
        self.changes = 0

    @property
    def can_undo(self):
        return bool(self._undo)

    def add_parsed_task(self, parsed):
        return self.repository.save(Task(title=parsed.title, deadline=parsed.deadline,
                                         priority=parsed.priority))

    def complete_tasks(self, ids):
        self._undo = [self.repository.complete(i) for i in ids]

    def undo_completion(self):
        ids, self._undo = self._undo, []
        return len([self.repository.undo_complete(c) for c in ids])

    def snooze_tasks(self, ids, minutes):
        for task_id in ids:
            self.repository.snooze(task_id, NOW + timedelta(minutes=max(minutes, 1)))

    def tasks_changed_externally(self):
        self.changes += 1

    def start_focus(self, task_id=None):
        task = self.repository.get(task_id) if task_id is not None else None
        self.focus.start_focus(25, task_id, task.title if task else "")

    def stop_focus(self):
        self.focus.stop()


@pytest.fixture
def app(tmp_path):
    repo = TaskRepository(str(tmp_path / "tasks.db"))
    yield FakeApp(repo)
    repo.close()


@pytest.fixture
def api(app):
    return DashboardApi(app, clock=lambda: NOW)


def call(api, method, path, body=None, query=None):
    return api.handle(method, path, query or {}, body or {})


def test_add_parses_natural_language(api):
    status, data = call(api, "POST", "/api/tasks", {"text": "call mom tomorrow 5pm !high"})
    assert status == 201
    [task] = data["tasks"]
    assert task["title"] == "call mom"
    assert task["priority"] == "high"
    assert task["deadline"] == "2026-10-25T17:00"


def test_add_rejects_empty_and_non_text(api):
    assert call(api, "POST", "/api/tasks", {"text": "  "})[0] == 400
    assert call(api, "POST", "/api/tasks", {"text": 42})[0] == 400
    assert call(api, "POST", "/api/tasks", {})[0] == 400


def test_parse_preview(api):
    status, data = call(api, "GET", "/api/parse", query={"text": "gym in 2 hours !low"})
    assert status == 200
    assert data["title"] == "gym"
    assert data["priority"] == "low"
    assert data["deadline"] == "2026-10-24T12:00"


def test_complete_removes_and_undo_restores(api, app):
    task_id = app.repository.save(Task(title="write report"))
    status, data = call(api, "POST", f"/api/tasks/{task_id}/complete")
    assert status == 200 and data["tasks"] == [] and data["can_undo"]
    status, data = call(api, "POST", "/api/undo")
    assert data["restored"] == 1
    assert [t["title"] for t in data["tasks"]] == ["write report"]


def test_edit_validates_fields(api, app):
    task_id = app.repository.save(Task(title="old"))
    status, data = call(api, "PATCH", f"/api/tasks/{task_id}",
                        {"title": "new", "priority": "high", "deadline": "2026-10-24T09:00"})
    assert status == 200
    [task] = data["tasks"]
    assert task["title"] == "new" and task["priority"] == "high" and task["overdue"]
    assert app.changes == 1
    assert call(api, "PATCH", f"/api/tasks/{task_id}", {"priority": "urgent"})[0] == 400
    assert call(api, "PATCH", f"/api/tasks/{task_id}", {"deadline": "soon"})[0] == 400
    assert call(api, "PATCH", f"/api/tasks/{task_id}", {"title": ""})[0] == 400
    status, data = call(api, "PATCH", f"/api/tasks/{task_id}", {"deadline": None})
    assert data["tasks"][0]["deadline"] is None


def test_snooze_and_delete(api, app):
    task_id = app.repository.save(Task(title="nap"))
    assert call(api, "POST", f"/api/tasks/{task_id}/snooze", {"minutes": 0})[0] == 400
    status, data = call(api, "POST", f"/api/tasks/{task_id}/snooze", {"minutes": 60})
    assert data["tasks"][0]["snoozed_until"] == "2026-10-24T11:00"
    status, data = call(api, "DELETE", f"/api/tasks/{task_id}")
    assert data["tasks"] == []


def test_unknown_task_and_route(api):
    assert call(api, "POST", "/api/tasks/999/complete")[0] == 404
    assert call(api, "GET", "/api/nope")[0] == 404


def test_focus_start_stop(api, app):
    task_id = app.repository.save(Task(title="deep work"))
    status, data = call(api, "POST", "/api/focus/start", {"task_id": task_id})
    assert data["state"] == "focusing" and data["task_title"] == "deep work"
    assert data["remaining_s"] == 25 * 60
    status, data = call(api, "POST", "/api/focus/stop")
    assert data["state"] == "idle"


def test_state_bundles_everything(api, app):
    app.repository.save(Task(title="a"))
    status, data = call(api, "GET", "/api/state")
    assert status == 200
    assert {"version", "tasks", "stats", "focus", "can_undo"} <= set(data)
    assert len(data["stats"]["days"]) == 7


# ---------------------------------------------------------------------------
# Server (real sockets on 127.0.0.1)
# ---------------------------------------------------------------------------

@pytest.fixture
def server(api, qtbot):
    srv = DashboardServer(api.handle, MainThreadDispatcher(), port=0)
    assert srv.start()
    srv.qtbot = qtbot
    yield srv
    srv.stop()


def http(server, *args, **kwargs):
    """Make the request from a worker thread while the Qt loop serves the API."""
    import threading

    result = {}
    worker = threading.Thread(target=lambda: result.update(r=_http(server, *args, **kwargs)))
    worker.start()
    server.qtbot.waitUntil(lambda: not worker.is_alive(), timeout=5000)
    return result["r"]


def _http(server, method, path, body=None, token=True, host=None, content_type="application/json"):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(server.url.rstrip("/") + path, data=data, method=method)
    if token:
        request.add_header("X-Spidey-Token", server.token)
    if data is not None:
        request.add_header("Content-Type", content_type)
    if host:
        request.add_header("Host", host)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as err:
        return err.code, err.read(), err.headers


def test_server_serves_page_with_token_and_csp(server):
    status, body, headers = http(server, "GET", "/", token=False)
    assert status == 200
    assert server.token.encode() in body
    assert b"__SPIDEY_TOKEN__" not in body
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "Access-Control-Allow-Origin" not in headers


def test_server_requires_token(server):
    assert http(server, "GET", "/api/tasks", token=False)[0] == 403
    status, body, _ = http(server, "GET", "/api/tasks")
    assert status == 200 and json.loads(body)["tasks"] == []


def test_server_rejects_foreign_host(server):
    """DNS rebinding: evil.com resolving to 127.0.0.1 must not get in."""
    assert http(server, "GET", "/", token=False, host="evil.com")[0] == 403
    assert http(server, "GET", "/api/tasks", host=f"evil.com:{server.port}")[0] == 403


def test_server_rejects_non_json_and_preflight(server):
    assert http(server, "POST", "/api/tasks", {"text": "x"}, content_type="text/plain")[0] == 415
    assert http(server, "OPTIONS", "/api/tasks")[0] == 405


def test_server_round_trip(server):
    status, body, _ = http(server, "POST", "/api/tasks", {"text": "buy milk"})
    assert status == 201
    assert json.loads(body)["tasks"][0]["title"] == "buy milk"


def test_dispatcher_runs_on_main_thread(qtbot, app):
    import threading

    main_thread = threading.get_ident()
    seen = {}

    def handler(method, path, query, body):
        seen["thread"] = threading.get_ident()
        return 200, {"ok": True}

    dispatcher = MainThreadDispatcher()
    srv = DashboardServer(handler, dispatcher, port=0)
    srv.start()
    result = {}
    worker = threading.Thread(target=lambda: result.update(r=_http(srv, "GET", "/api/x")))
    worker.start()
    qtbot.waitUntil(lambda: not worker.is_alive(), timeout=5000)
    srv.stop()
    assert result["r"][0] == 200
    assert seen["thread"] == main_thread
