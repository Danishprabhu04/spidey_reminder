"""Task data model for the Spider-Man Hanging Reminder."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Task:
    """Represents a single task in the companion's to-do list."""

    id: int = -1  # -1 indicates a new, unsaved task; repository assigns actual id
    title: str = ""
    description: str = ""
    priority: str = "normal"       # "low", "normal", "high"
    deadline: Optional[datetime] = None
    completed: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # Derived property for UI display
    @property
    def display_priority(self) -> str:
        return self.priority.upper()

    @property
    def age_days(self) -> int:
        """Number of days since task creation."""
        delta = datetime.now(timezone.utc) - self.created_at.replace(tzinfo=timezone.utc)
        return delta.days

    # Human-readable status strings
    @property
    def status_label(self) -> str:
        if self.completed:
            return f"Completed {self.completed_at.strftime('%Y-%m-%d') if self.completed_at else ''}"
        return f"Pending {self.age_days}d old"

    @property
    def is_overdue(self) -> bool:
        """True if task is pending and past its deadline."""
        if self.completed or self.deadline is None:
            return False
        return datetime.now(timezone.utc) > self.deadline