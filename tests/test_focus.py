"""Tests for the focus-timer state machine (fake clock, no event loop)."""

from __future__ import annotations

from datetime import datetime, timedelta

from hanging_reminder.focus.session import BREAK, FOCUSING, IDLE, FocusSession, format_mmss


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 23, 10, 0)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


def make():
    clock = FakeClock()
    session = FocusSession(clock=clock, auto_poll=False)
    events = []
    session.finished.connect(lambda s: events.append(("finished", s)))
    session.stopped.connect(lambda: events.append(("stopped",)))
    return clock, session, events


def test_focus_counts_down_and_finishes():
    clock, s, events = make()
    s.start_focus(25, task_id=7, title="Write report")
    assert s.state == FOCUSING and s.remaining_s() == 25 * 60 and s.progress() == 1.0
    clock.advance(minutes=10)
    s.poll()
    assert s.remaining_s() == 15 * 60 and abs(s.progress() - 0.6) < 1e-9
    clock.advance(minutes=15)
    s.poll()
    assert s.state == IDLE and events == [("finished", FOCUSING)]
    assert s.task_id == 7 and s.started_at == datetime(2026, 10, 23, 10, 0)


def test_break_then_back_to_idle():
    clock, s, events = make()
    s.start_break(5)
    assert s.state == BREAK
    clock.advance(minutes=5)
    s.poll()
    assert s.state == IDLE
    assert events == [("stopped",), ("finished", BREAK)]


def test_stop_early():
    clock, s, events = make()
    s.start_focus(25)
    clock.advance(minutes=3)
    s.stop()
    assert s.state == IDLE and not s.running and events == [("stopped",)]
    s.stop()  # idempotent
    assert events == [("stopped",)]


def test_format():
    assert format_mmss(1499) == "24:59" and format_mmss(5) == "00:05"
