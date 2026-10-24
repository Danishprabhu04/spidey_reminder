"""Local web dashboard server – http://127.0.0.1:47823 while Spidey runs.

A stdlib ``ThreadingHTTPServer`` on a daemon thread serves the static page
and a small JSON API.  Every API call is handed to the Qt main thread
(:class:`MainThreadDispatcher`) and the HTTP thread waits for the answer,
so the API code never touches Qt or SQLite from another thread.

Only this computer can use it:

- it listens on 127.0.0.1 only;
- the ``Host`` header must be 127.0.0.1/localhost on our port, so a web
  page can't reach it through DNS rebinding;
- every ``/api/*`` request needs the per-launch ``X-Spidey-Token`` that is
  baked into the served page – other websites can't read the page (no
  CORS headers are ever sent) and so can't learn the token.
"""

from __future__ import annotations

import json
import secrets
import threading
from concurrent.futures import Future, TimeoutError as FutureTimeout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.parse import parse_qsl, urlsplit

from PySide6.QtCore import QObject, Qt, Signal

from hanging_reminder import paths
from hanging_reminder.logging_config import logger

DEFAULT_PORT = 47823
PORT_ATTEMPTS = 10
MAX_BODY = 16 * 1024
CALL_TIMEOUT_S = 10
TOKEN_PLACEHOLDER = "__SPIDEY_TOKEN__"

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
    "/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
PAGE_CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")

Handler = Callable[[str, str, Dict[str, str], dict], tuple]


class MainThreadDispatcher(QObject):
    """Runs a callable on the thread that owns this object (the GUI thread)."""

    _call = Signal(object, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._call.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def submit(self, fn: Callable[[], object]) -> Future:
        future: Future = Future()
        self._call.emit(fn, future)
        return future

    @staticmethod
    def _run(fn, future: Future) -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(fn())
        except BaseException as exc:  # handed back to the HTTP thread
            future.set_exception(exc)


class DashboardServer:
    def __init__(self, handler: Handler, dispatcher: Optional[MainThreadDispatcher] = None,
                 static_dir: Optional[Path] = None, port: int = DEFAULT_PORT,
                 favicon: Optional[Path] = None) -> None:
        self._handler = handler
        self._dispatcher = dispatcher
        self._static_dir = static_dir or paths.resource_path("dashboard", "static")
        self._favicon = favicon
        self._preferred_port = port
        self.token = secrets.token_urlsafe(24)
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1] if self._httpd else 0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/" if self._httpd else ""

    def start(self) -> bool:
        request_handler = _make_request_handler(self)
        candidates = [self._preferred_port + i for i in range(PORT_ATTEMPTS)] if self._preferred_port else []
        for port in candidates + [0]:
            try:
                self._httpd = ThreadingHTTPServer(("127.0.0.1", port), request_handler)
                break
            except OSError:
                continue
        if self._httpd is None:
            logger.warning("Web dashboard could not start (no free port)")
            return False
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="spidey-dashboard",
                                        daemon=True)
        self._thread.start()
        if self._preferred_port:  # not for throwaway (port 0) servers
            try:
                (paths.runtime_dir() / "dashboard.port").write_text(str(self.port), encoding="utf-8")
            except OSError:
                pass
        logger.info("Web dashboard at %s", self.url)
        return True

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None

    # ---- used by the request handler (HTTP threads) ----

    def allowed_hosts(self) -> set:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def call_api(self, method: str, path: str, query: Dict[str, str], body: dict) -> tuple:
        def run():
            return self._handler(method, path, query, body)
        if self._dispatcher is None:
            return run()
        return self._dispatcher.submit(run).result(timeout=CALL_TIMEOUT_S)

    def static_file(self, path: str) -> Optional[tuple]:
        if path == "/favicon.png" and self._favicon is not None and self._favicon.exists():
            return self._favicon.read_bytes(), "image/png"
        entry = STATIC_FILES.get(path)
        if entry is None:
            return None
        name, content_type = entry
        data = (self._static_dir / name).read_bytes()
        if name == "index.html":
            data = data.replace(TOKEN_PLACEHOLDER.encode(), self.token.encode())
        return data, content_type


def _make_request_handler(server: DashboardServer):
    class RequestHandler(BaseHTTPRequestHandler):
        server_version = "SpideySense"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args) -> None:  # keep the app log quiet
            pass

        # ---- helpers ----

        def _send(self, status: int, data: bytes, content_type: str,
                  extra: Optional[Dict[str, str]] = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            for key, value in {**SECURITY_HEADERS, **(extra or {})}.items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

        def _host_ok(self) -> bool:
            return (self.headers.get("Host") or "").lower() in server.allowed_hosts()

        def _handle(self) -> None:
            if not self._host_ok():
                self._json(403, {"error": "Forbidden host"})
                return
            url = urlsplit(self.path)
            if not url.path.startswith("/api/"):
                if self.command not in ("GET", "HEAD"):
                    self._json(405, {"error": "Method not allowed"})
                    return
                found = server.static_file(url.path)
                if found is None:
                    self._json(404, {"error": "Not found"})
                    return
                data, content_type = found
                extra = {"Content-Security-Policy": PAGE_CSP} if content_type.startswith("text/html") else None
                self._send(200, data, content_type, extra)
                return

            if not secrets.compare_digest(self.headers.get("X-Spidey-Token", ""), server.token):
                self._json(403, {"error": "Missing or wrong token"})
                return
            body: dict = {}
            if self.command in ("POST", "PATCH"):
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = -1
                if length < 0 or length > MAX_BODY:
                    self._json(413, {"error": "Request too large"})
                    return
                raw = self.rfile.read(length) if length else b""
                if raw:
                    if "application/json" not in (self.headers.get("Content-Type") or ""):
                        self._json(415, {"error": "Send JSON"})
                        return
                    try:
                        body = json.loads(raw)
                    except ValueError:
                        self._json(400, {"error": "Invalid JSON"})
                        return
                    if not isinstance(body, dict):
                        self._json(400, {"error": "Send a JSON object"})
                        return
            query = dict(parse_qsl(url.query))
            try:
                status, payload = server.call_api(self.command, url.path, query, body)
            except FutureTimeout:
                self._json(503, {"error": "Spidey is busy, try again"})
                return
            except Exception:
                logger.exception("Dashboard API error on %s %s", self.command, url.path)
                self._json(500, {"error": "Something went wrong"})
                return
            self._json(status, payload)

        do_GET = do_HEAD = do_POST = do_PATCH = do_DELETE = _handle

        def do_OPTIONS(self) -> None:  # no CORS preflight approval, ever
            self._json(405, {"error": "Method not allowed"})

    return RequestHandler
