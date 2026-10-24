"""Tests for natural-language task entry."""

from __future__ import annotations

from datetime import datetime

import pytest

from hanging_reminder.tasks.nlp import describe_deadline, parse_task_text

# Friday 23 Oct 2026, 10:00
NOW = datetime(2026, 10, 23, 10, 0)


@pytest.mark.parametrize("text,title,deadline,priority", [
    ("Buy milk", "Buy milk", None, "normal"),
    ("Call mom tomorrow 5pm !high", "Call mom", datetime(2026, 10, 24, 17, 0), "high"),
    ("Pay rent today", "Pay rent", datetime(2026, 10, 23, 18, 0), "normal"),
    ("Movie tonight", "Movie", datetime(2026, 10, 23, 20, 0), "normal"),
    ("Gym tmrw at 7", "Gym", datetime(2026, 10, 24, 19, 0), "normal"),
    ("Standup at 9:30am", "Standup", datetime(2026, 10, 24, 9, 30), "normal"),
    ("Review PR 17:30", "Review PR", datetime(2026, 10, 23, 17, 30), "normal"),
    ("Water plants in 20 min", "Water plants", datetime(2026, 10, 23, 10, 20), "normal"),
    ("Backup laptop in 2 hours !low", "Backup laptop", datetime(2026, 10, 23, 12, 0), "low"),
    ("Renew passport in 3 days", "Renew passport", datetime(2026, 10, 26, 10, 0), "normal"),
    ("Team lunch on monday at noon", "Team lunch", datetime(2026, 10, 26, 12, 0), "normal"),
    ("Demo friday 3pm", "Demo", datetime(2026, 10, 23, 15, 0), "normal"),
    ("Demo next friday", "Demo", datetime(2026, 10, 30, 9, 0), "normal"),
    ("Plan sprint next week", "Plan sprint", datetime(2026, 10, 26, 9, 0), "normal"),
    ("Submit report by oct 30", "Submit report", datetime(2026, 10, 30, 9, 0), "normal"),
    ("Birthday gift 2nd november", "Birthday gift", datetime(2026, 11, 2, 9, 0), "normal"),
    ("Tax filing 31/7", "Tax filing", datetime(2027, 7, 31, 9, 0), "normal"),
    ("Exam 15/12/2026 at 10am", "Exam", datetime(2026, 12, 15, 10, 0), "normal"),
    ("Call bank in the morning", "Call bank", datetime(2026, 10, 24, 9, 0), "normal"),
    ("Fix bug !!", "Fix bug", None, "high"),
    ("Buy 2 apples", "Buy 2 apples", None, "normal"),
    ("Read chapter 5", "Read chapter 5", None, "normal"),
    ("Say hi!", "Say hi!", None, "normal"),
    ("Dentist feb 30", "Dentist feb 30", None, "normal"),
    ("Ship v2 SAT evening", "Ship v2", datetime(2026, 10, 24, 18, 0), "normal"),
])
def test_parse(text, title, deadline, priority):
    parsed = parse_task_text(text, NOW)
    assert (parsed.title, parsed.deadline, parsed.priority) == (title, deadline, priority)


def test_title_never_empty():
    assert parse_task_text("tomorrow", NOW).title == "tomorrow"


@pytest.mark.parametrize("deadline,label", [
    (datetime(2026, 10, 23, 17, 0), "Today 17:00"),
    (datetime(2026, 10, 24, 9, 0), "Tomorrow 09:00"),
    (datetime(2026, 10, 27, 9, 0), "Tue 09:00"),
    (datetime(2026, 11, 30, 9, 0), "30 Nov 09:00"),
    (datetime(2027, 1, 5, 9, 0), "5 Jan 2027 09:00"),
])
def test_describe_deadline(deadline, label):
    assert describe_deadline(deadline, NOW) == label
