"""Decides which reminders to show and when – no Qt, injectable clock.

:meth:`ReminderPlanner.tick` is called every ~30 s with the current time
and whether the user is available (present, not fullscreen, not DND).
It returns the reminders to present right now:

- ``due``      – tasks whose deadline passed (or whose snooze ran out).
                 While the user is unavailable they simply stay pending in
                 the database and are delivered together on return.
- ``nag``      – "N missions pending" every ``reminder_interval`` seconds.
- ``morning``  – today's missions, once a day, the first time the user is
                 around after ``MORNING_FROM``.
- ``eod``      – end-of-day summary once a day after ``end_of_day_time``.

The caller marks due tasks as reminded once actually shown
(:meth:`ReminderPlanner.delivered`), and persists the config afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Optional

from hanging_reminder.tasks.models import Task

MORNING_FROM = time(5, 0)
MORNING_UNTIL = time(12, 0)
FIRST_NAG_DELAY_S = 20


@dataclass
class Reminder:
    kind: str                      # "due" | "nag" | "morning" | "eod"
    tasks: List[Task] = field(default_factory=list)
    pending: int = 0
    done_today: int = 0


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


class ReminderPlanner:
    def __init__(self, repository, config, start: Optional[datetime] = None) -> None:
        self._repo = repository
        self._config = config
        start = start or datetime.now()
        # First nag shortly after startup, then every reminder_interval
        self._last_nag = start.timestamp() - int(config.reminder_interval) + FIRST_NAG_DELAY_S

    def tick(self, now: datetime, available: bool) -> List[Reminder]:
        if not available or self._config.dnd_active(now):
            return []
        out: List[Reminder] = []

        due = self._due_tasks(now)
        if due:
            out.append(Reminder("due", tasks=due))

        today = now.date().isoformat()
        if (
            self._config.morning_brief
            and self._config.last_brief_date != today
            and MORNING_FROM <= now.time() < MORNING_UNTIL
        ):
            self._config.last_brief_date = today
            pending = self._repo.get_pending()
            out.append(Reminder("morning", tasks=pending, pending=len(pending)))
            self._last_nag = now.timestamp()  # the brief counts as a nudge

        if (
            self._config.last_eod_date != today
            and now.time() >= _parse_hhmm(self._config.end_of_day_time)
        ):
            self._config.last_eod_date = today
            pending = self._repo.get_pending()
            done = self._repo.completions_by_day(1, now.date()).get(now.date(), 0)
            out.append(Reminder("eod", tasks=pending, pending=len(pending), done_today=done))
            self._last_nag = now.timestamp()

        if not out and now.timestamp() - self._last_nag >= int(self._config.reminder_interval):
            self._last_nag = now.timestamp()
            pending = self._repo.count_pending()
            if pending:
                out.append(Reminder("nag", pending=pending))
        return out

    def _due_tasks(self, now: datetime) -> List[Task]:
        seen, tasks = set(), []
        candidates = self._repo.get_due_unreminded(now) + self._repo.get_snooze_expired(now)
        for task in candidates:
            if task.id in seen or task.is_snoozed(now):
                continue
            seen.add(task.id)
            tasks.append(task)
        return tasks

    def delivered(self, reminder: Reminder, now: datetime) -> None:
        """Mark due tasks as announced so they aren't repeated."""
        if reminder.kind == "due":
            for task in reminder.tasks:
                self._repo.mark_reminded(task.id, now)
