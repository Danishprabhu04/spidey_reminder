"""Streaks and weekly summary – pure functions over repository data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, Iterable, List


def streak(days_with_completions: Iterable[date], today: date) -> int:
    """Consecutive days with at least one completed task, ending today.

    A streak that ended yesterday still counts (today isn't over yet).
    """
    days = set(days_with_completions)
    cursor = today if today in days else today - timedelta(days=1)
    count = 0
    while cursor in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


@dataclass
class WeekSummary:
    streak: int
    done_today: int
    done_week: int
    focus_today_min: float
    focus_week_min: float
    days: List[date] = field(default_factory=list)       # oldest -> today
    daily_done: List[int] = field(default_factory=list)  # aligned with days


def week_summary(completions_by_day: Dict[date, int], focus_by_day: Dict[date, float],
                 completion_days: Iterable[date], today: date) -> WeekSummary:
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    daily = [int(completions_by_day.get(d, 0)) for d in days]
    return WeekSummary(
        streak=streak(completion_days, today),
        done_today=daily[-1],
        done_week=sum(daily),
        focus_today_min=float(focus_by_day.get(today, 0.0)),
        focus_week_min=float(sum(focus_by_day.get(d, 0.0) for d in days)),
        days=days,
        daily_done=daily,
    )


def summary_from_repository(repository, today: date | None = None) -> WeekSummary:
    today = today or date.today()
    return week_summary(
        repository.completions_by_day(7, today),
        repository.focus_minutes_by_day(7, today),
        repository.completion_days(),
        today,
    )
