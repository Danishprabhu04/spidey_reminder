"""Autonomous idle moves – Spidey wanders a little on his own.

:class:`IdleBehaviors` only decides *when* and *what*; the companion
window performs the move through its existing web physics
(``swing_to``, ``yo_yo``, ``look_around``, ``doze``) and always returns
to the fixed anchor.
"""

from __future__ import annotations

import random
from typing import Optional

MIN_GAP_S = 300.0
MAX_GAP_S = 720.0
ACTIONS = ("swing", "yo_yo", "look_around")


class IdleBehaviors:
    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self._rng = rng or random.Random()
        self.next_at: float = 0.0
        self.schedule(0.0)

    def schedule(self, now: float) -> None:
        self.next_at = now + self._rng.uniform(MIN_GAP_S, MAX_GAP_S)

    def tick(self, now: float, allowed: bool, sleepy: bool) -> Optional[str]:
        """Return the action to perform now, or None.

        *allowed* folds in everything that should keep him still (dragging,
        reduced motion, focus mode, user away, …).  A skipped slot is simply
        rescheduled.
        """
        if now < self.next_at:
            return None
        self.schedule(now)
        if not allowed:
            return None
        if sleepy:
            return "doze"
        return self._rng.choice(ACTIONS)

    def swing_offset(self, home_x: float, width: float, margin: float) -> float:
        """A temporary anchor 150–400px from home, kept on screen."""
        distance = self._rng.uniform(150.0, 400.0)
        direction = self._rng.choice((-1.0, 1.0))
        target = home_x + direction * distance
        if not margin <= target <= width - margin:
            target = home_x - direction * distance
        return min(max(target, margin), width - margin)

