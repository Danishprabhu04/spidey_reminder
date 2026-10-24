"""Natural-language task entry – pure Python, no dependencies.

``parse_task_text("Call mom tomorrow 5pm !high", now)`` returns the title
("Call mom"), a deadline and a priority.  Recognised phrases are removed
from the title.

Dates
    today, tonight, tomorrow (tmr/tmrw), weekday names (mon … sunday),
    next <weekday>, next week, in N min/hours/days/weeks,
    "oct 30" / "30 oct" / "october 30th", 30/10 or 30/10/2026 (day first)
Times
    5pm, 5:30pm, 17:30, at 5 (1–7 means pm), noon, midnight,
    morning (9:00), afternoon (15:00), evening (18:00)
Priority
    !high !h !! !urgent  ·  !low !l  ·  !normal

A date without a time defaults to 09:00 (today: 18:00, tonight: 20:00).
A time without a date means today, or tomorrow if that time has passed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

DEFAULT_TIME = time(9, 0)
TODAY_DEFAULT_TIME = time(18, 0)
TONIGHT_TIME = time(20, 0)
PM_GUESS_MAX_HOUR = 7  # "at 5" -> 17:00

WEEKDAYS = {
    "mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2, "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4, "sat": 5, "saturday": 5, "sun": 6, "sunday": 6,
}
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
NAMED_TIMES = {
    "noon": time(12, 0), "midnight": time(23, 59), "morning": time(9, 0),
    "afternoon": time(15, 0), "evening": time(18, 0),
}
PRIORITIES = {
    "!!": "high", "!high": "high", "!h": "high", "!urgent": "high",
    "!low": "low", "!l": "low", "!normal": "normal", "!n": "normal",
}

_WD = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_LEAD = r"(?:\b(?:due|by|on|at|for)\s+)?"  # filler words swallowed with a match

_RE_PRIORITY = re.compile(r"(?<!\S)(!!|![a-z]+)(?!\S)", re.I)
_RE_IN = re.compile(
    _LEAD + r"\bin\s+(\d+)\s*(minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)\b", re.I)
_RE_NEXT_WEEK = re.compile(_LEAD + r"\bnext\s+week\b", re.I)
_RE_WEEKDAY = re.compile(_LEAD + rf"\b(next\s+)?({_WD})\b", re.I)
_RE_RELDAY = re.compile(_LEAD + r"\b(today|tonight|tomorrow|tmrw?|tmr)\b", re.I)
_RE_MONTH_DAY = re.compile(_LEAD + rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)
_RE_DAY_MONTH = re.compile(_LEAD + rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\b\.?", re.I)
_RE_NUMERIC = re.compile(_LEAD + r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?\b")
_RE_TIME_AMPM = re.compile(_LEAD + r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_RE_TIME_24 = re.compile(_LEAD + r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_RE_TIME_AT = re.compile(r"\bat\s+(\d{1,2})\b(?!\s*[:/])", re.I)
_RE_NAMED_TIME = re.compile(
    _LEAD + r"\b(?:in\s+the\s+)?(noon|midnight|morning|afternoon|evening)\b", re.I)


@dataclass
class ParsedTask:
    title: str
    deadline: Optional[datetime] = None
    priority: str = "normal"


def _cut(text: str, match: re.Match) -> str:
    return text[: match.start()] + " " + text[match.end():]


def _next_weekday(today: date, weekday: int, strictly_after: bool) -> date:
    days = (weekday - today.weekday()) % 7
    if days == 0 and strictly_after:
        days = 7
    return today + timedelta(days=days)


def _future_date(today: date, month: int, day: int) -> Optional[date]:
    """This year's date, or next year's if it already passed."""
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today:
            return candidate
    return None


def parse_task_text(text: str, now: Optional[datetime] = None) -> ParsedTask:
    now = now or datetime.now()
    today = now.date()
    rest = f" {text} "
    priority = "normal"
    day: Optional[date] = None
    at: Optional[time] = None
    default_time = DEFAULT_TIME
    absolute: Optional[datetime] = None

    # Priority tokens
    for m in reversed(list(_RE_PRIORITY.finditer(rest))):
        token = m.group(1).lower()
        if token in PRIORITIES:
            priority = PRIORITIES[token]
            rest = _cut(rest, m)

    # "in 2 hours" – an exact moment
    m = _RE_IN.search(rest)
    if m:
        amount, unit = int(m.group(1)), m.group(2).lower()
        if unit.startswith("w"):
            delta = timedelta(weeks=amount)
        elif unit.startswith("d"):
            delta = timedelta(days=amount)
        elif unit.startswith("h"):
            delta = timedelta(hours=amount)
        else:
            delta = timedelta(minutes=amount)
        absolute = now + delta
        rest = _cut(rest, m)

    # Dates
    if absolute is None:
        if (m := _RE_NEXT_WEEK.search(rest)):
            day = _next_weekday(today, 0, strictly_after=True)
            rest = _cut(rest, m)
        elif (m := _RE_RELDAY.search(rest)):
            word = m.group(1).lower()
            if word == "today":
                day, default_time = today, TODAY_DEFAULT_TIME
            elif word == "tonight":
                day, default_time = today, TONIGHT_TIME
            else:
                day = today + timedelta(days=1)
            rest = _cut(rest, m)
        elif (m := _RE_WEEKDAY.search(rest)):
            day = _next_weekday(today, WEEKDAYS[m.group(2).lower()],
                                strictly_after=bool(m.group(1)))
            rest = _cut(rest, m)
        elif (m := _RE_MONTH_DAY.search(rest)):
            day = _future_date(today, MONTHS[m.group(1).lower()], int(m.group(2)))
            rest = _cut(rest, m) if day else rest
        elif (m := _RE_DAY_MONTH.search(rest)):
            day = _future_date(today, MONTHS[m.group(2).lower()], int(m.group(1)))
            rest = _cut(rest, m) if day else rest
        elif (m := _RE_NUMERIC.search(rest)):
            d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
            try:
                if y:
                    year = int(y) + (2000 if len(y) == 2 else 0)
                    day = date(year, mo, d)
                else:
                    day = _future_date(today, mo, d)
            except ValueError:
                day = None
            if day:
                rest = _cut(rest, m)

        # Times
        if (m := _RE_TIME_AMPM.search(rest)):
            hour, minute = int(m.group(1)) % 12, int(m.group(2) or 0)
            if m.group(3).lower() == "pm":
                hour += 12
            if hour < 24 and minute < 60:
                at = time(hour, minute)
                rest = _cut(rest, m)
        elif (m := _RE_TIME_24.search(rest)):
            at = time(int(m.group(1)), int(m.group(2)))
            rest = _cut(rest, m)
        elif (m := _RE_TIME_AT.search(rest)):
            hour = int(m.group(1))
            if 1 <= hour <= 23:
                at = time(hour + 12 if hour <= PM_GUESS_MAX_HOUR else hour, 0)
                rest = _cut(rest, m)
        elif (m := _RE_NAMED_TIME.search(rest)):
            at = NAMED_TIMES[m.group(1).lower()]
            rest = _cut(rest, m)

        if day is not None:
            absolute = datetime.combine(day, at or default_time)
        elif at is not None:
            absolute = datetime.combine(today, at)
            if absolute <= now:
                absolute += timedelta(days=1)

    title = re.sub(r"\s+", " ", rest).strip(" ,;-")
    return ParsedTask(title=title or text.strip(), deadline=absolute, priority=priority)


def describe_deadline(deadline: datetime, now: Optional[datetime] = None) -> str:
    """Short human label: "Today 17:00", "Tomorrow 09:00", "Fri 09:00", "30 Oct 09:00"."""
    now = now or datetime.now()
    days = (deadline.date() - now.date()).days
    clock = deadline.strftime("%H:%M")
    if days == 0:
        return f"Today {clock}"
    if days == 1:
        return f"Tomorrow {clock}"
    if days == -1:
        return f"Yesterday {clock}"
    if 1 < days < 7:
        return f"{deadline.strftime('%a')} {clock}"
    label = f"{deadline.day} {deadline.strftime('%b')}"
    if deadline.year != now.year:
        label += f" {deadline.year}"
    return f"{label} {clock}"
