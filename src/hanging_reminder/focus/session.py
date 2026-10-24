"""Pomodoro-style focus timer: idle -> focusing -> break -> idle.

The clock is injectable so tests can drive it; in the app a 1 s QTimer
calls :meth:`FocusSession.poll`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

IDLE, FOCUSING, BREAK = "idle", "focusing", "break"


class FocusSession(QObject):
    #: (state, remaining_seconds, total_seconds) – every poll while running
    ticked = Signal(str, int, int)
    #: state that just ended normally ("focusing" or "break")
    finished = Signal(str)
    #: the session went back to idle (finished break or stopped)
    stopped = Signal()

    def __init__(self, clock: Callable[[], datetime] = datetime.now,
                 parent: QObject | None = None, auto_poll: bool = True) -> None:
        super().__init__(parent)
        self._clock = clock
        self.state: str = IDLE
        self.task_id: Optional[int] = None
        self.task_title: str = ""
        self.started_at: Optional[datetime] = None
        self._ends_at: Optional[datetime] = None
        self._total_s: int = 0
        self._timer: Optional[QTimer] = None
        if auto_poll:
            self._timer = QTimer(self, interval=1000, timeout=self.poll)

    # ---- control ----

    def start_focus(self, minutes: int, task_id: Optional[int] = None, title: str = "") -> None:
        self.task_id, self.task_title = task_id, title
        self._begin(FOCUSING, minutes)

    def start_break(self, minutes: int) -> None:
        self._begin(BREAK, minutes)

    def stop(self) -> None:
        if self.state == IDLE:
            return
        self.state = IDLE
        self._ends_at = None
        if self._timer is not None:
            self._timer.stop()
        self.stopped.emit()

    def _begin(self, state: str, minutes: int) -> None:
        self.state = state
        self.started_at = self._clock()
        self._total_s = int(minutes * 60)
        self._ends_at = self.started_at + timedelta(seconds=self._total_s)
        if self._timer is not None:
            self._timer.start()
        self.poll()

    # ---- queries ----

    def now(self) -> datetime:
        return self._clock()

    @property
    def running(self) -> bool:
        return self.state != IDLE

    def remaining_s(self) -> int:
        if self._ends_at is None:
            return 0
        return max(0, int(round((self._ends_at - self._clock()).total_seconds())))

    def progress(self) -> float:
        """Fraction of the current phase still remaining (1 -> 0)."""
        return self.remaining_s() / self._total_s if self._total_s else 0.0

    # ---- tick ----

    def poll(self) -> None:
        if self.state == IDLE:
            return
        remaining = self.remaining_s()
        self.ticked.emit(self.state, remaining, self._total_s)
        if remaining > 0:
            return
        ended = self.state
        if ended == BREAK:
            self.stop()
        else:
            self.state = IDLE  # the app decides whether a break follows
            if self._timer is not None:
                self._timer.stop()
        self.finished.emit(ended)


def format_mmss(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
