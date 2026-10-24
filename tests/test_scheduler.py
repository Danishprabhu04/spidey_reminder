"""Tests for the reminder planner and presence logic (fake clock, temp DB)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from hanging_reminder.config import AppConfig
from hanging_reminder.reminders.scheduler import ReminderPlanner
from hanging_reminder.system.presence import presence_state
from hanging_reminder.tasks.models import Task
from hanging_reminder.tasks.repository import TaskRepository

START = datetime(2026, 10, 23, 14, 0)  # afternoon: no morning brief, before EOD


@pytest.fixture
def repo(tmp_path):
    return TaskRepository(str(tmp_path / "tasks.db"))


@pytest.fixture
def config(tmp_path):
    c = AppConfig()
    c.config_path = str(tmp_path / "config.json")
    c.reminder_interval = 600
    c.end_of_day_time = "17:30"
    return c


def kinds(reminders):
    return [r.kind for r in reminders]


def test_due_alert_once_then_marked(repo, config):
    planner = ReminderPlanner(repo, config, START)
    tid = repo.save(Task(title="Call", deadline=START + timedelta(minutes=5)))
    assert "due" not in kinds(planner.tick(START, True))
    now = START + timedelta(minutes=6)
    out = planner.tick(now, True)
    due = [r for r in out if r.kind == "due"][0]
    assert [t.id for t in due.tasks] == [tid]
    planner.delivered(due, now)
    assert "due" not in kinds(planner.tick(now + timedelta(seconds=30), True))


def test_due_alerts_wait_while_away_and_come_together(repo, config):
    planner = ReminderPlanner(repo, config, START)
    repo.save(Task(title="A", deadline=START + timedelta(minutes=1)))
    repo.save(Task(title="B", deadline=START + timedelta(minutes=2)))
    assert planner.tick(START + timedelta(minutes=3), available=False) == []
    out = planner.tick(START + timedelta(minutes=20), available=True)
    due = [r for r in out if r.kind == "due"][0]
    assert sorted(t.title for t in due.tasks) == ["A", "B"]


def test_snooze_defers_then_realerts(repo, config):
    planner = ReminderPlanner(repo, config, START)
    tid = repo.save(Task(title="Pay", deadline=START))
    now = START + timedelta(minutes=1)
    due = [r for r in planner.tick(now, True) if r.kind == "due"][0]
    planner.delivered(due, now)
    repo.snooze(tid, now + timedelta(minutes=10))
    assert "due" not in kinds(planner.tick(now + timedelta(minutes=5), True))
    again = planner.tick(now + timedelta(minutes=11), True)
    assert [t.id for r in again if r.kind == "due" for t in r.tasks] == [tid]


def test_snoozed_before_due_is_not_alerted(repo, config):
    planner = ReminderPlanner(repo, config, START)
    tid = repo.save(Task(title="Gym", deadline=START + timedelta(minutes=1)))
    repo.snooze(tid, START + timedelta(hours=1))
    assert "due" not in kinds(planner.tick(START + timedelta(minutes=2), True))


def test_dnd_silences_everything(repo, config):
    planner = ReminderPlanner(repo, config, START)
    repo.save(Task(title="X", deadline=START))
    config.dnd_until = (START + timedelta(hours=1)).isoformat()
    assert planner.tick(START + timedelta(minutes=1), True) == []


def test_nag_interval(repo, config):
    planner = ReminderPlanner(repo, config, START)
    repo.save(Task(title="Open task"))
    assert kinds(planner.tick(START + timedelta(seconds=5), True)) == []
    first = planner.tick(START + timedelta(seconds=25), True)
    assert kinds(first) == ["nag"] and first[0].pending == 1
    assert planner.tick(START + timedelta(minutes=5), True) == []
    assert kinds(planner.tick(START + timedelta(minutes=11), True)) == ["nag"]


def test_no_nag_without_pending(repo, config):
    planner = ReminderPlanner(repo, config, START)
    assert planner.tick(START + timedelta(minutes=1), True) == []


def test_morning_brief_once_per_day(repo, config):
    morning = datetime(2026, 10, 23, 8, 30)
    planner = ReminderPlanner(repo, config, morning)
    repo.save(Task(title="Plan"))
    assert kinds(planner.tick(morning, False)) == []          # not here yet
    assert "morning" in kinds(planner.tick(morning + timedelta(minutes=5), True))
    assert "morning" not in kinds(planner.tick(morning + timedelta(minutes=10), True))
    assert config.last_brief_date == "2026-10-23"


def test_morning_brief_can_be_disabled(repo, config):
    config.morning_brief = False
    planner = ReminderPlanner(repo, config, datetime(2026, 10, 23, 8, 0))
    assert "morning" not in kinds(planner.tick(datetime(2026, 10, 23, 8, 1), True))


def test_end_of_day_summary(repo, config):
    planner = ReminderPlanner(repo, config, START)
    repo.save(Task(title="Still open"))
    done = repo.save(Task(title="Done"))
    repo.complete(done)
    assert "eod" not in kinds(planner.tick(datetime(2026, 10, 23, 17, 29), True))
    out = planner.tick(datetime(2026, 10, 23, 17, 31), True)
    eod = [r for r in out if r.kind == "eod"][0]
    assert eod.pending == 1
    assert "eod" not in kinds(planner.tick(datetime(2026, 10, 23, 18, 0), True))


@pytest.mark.parametrize("idle_ms,locked,fullscreen,away,busy", [
    (1000, False, False, False, False),
    (400_000, False, False, True, False),
    (0, True, False, True, False),
    (0, False, True, False, True),
])
def test_presence_state(idle_ms, locked, fullscreen, away, busy):
    state = presence_state(idle_ms, locked, fullscreen, away_after_ms=300_000)
    assert (state.away, state.busy) == (away, busy)
    assert state.available == (not away and not busy)
