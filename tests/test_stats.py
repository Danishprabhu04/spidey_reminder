"""Tests for streaks and the weekly summary."""

from __future__ import annotations

from datetime import date, timedelta

from hanging_reminder.tasks.stats import streak, week_summary

TODAY = date(2026, 10, 23)


def days_ago(*offsets):
    return [TODAY - timedelta(days=o) for o in offsets]


def test_streak_counts_consecutive_days_ending_today():
    assert streak(days_ago(0, 1, 2, 4), TODAY) == 3


def test_streak_survives_until_today_ends():
    assert streak(days_ago(1, 2), TODAY) == 2


def test_streak_broken_by_gap():
    assert streak(days_ago(2, 3), TODAY) == 0
    assert streak([], TODAY) == 0


def test_week_summary():
    completions = {TODAY: 2, TODAY - timedelta(days=1): 1, TODAY - timedelta(days=9): 5}
    focus = {TODAY: 50.0, TODAY - timedelta(days=3): 25.0}
    s = week_summary(completions, focus, completions.keys(), TODAY)
    assert (s.streak, s.done_today, s.done_week) == (2, 2, 3)
    assert (s.focus_today_min, s.focus_week_min) == (50.0, 75.0)
    assert s.days[-1] == TODAY and len(s.daily_done) == 7 and s.daily_done[-2:] == [1, 2]
