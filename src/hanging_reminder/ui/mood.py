"""Spidey's mood – pure logic, no Qt.

Inputs are fed in from the app (task counts, presence, focus) and the
frame loop (spin speed); :meth:`MoodEngine.evaluate` picks the mood the
eyes should show.  Short-lived moods (dizzy, proud, shocked) expire on
their own.

Priority: dizzy > shocked > proud > focused > sleepy > worried > happy > neutral
"""

from __future__ import annotations

from dataclasses import dataclass

DIZZY_SPIN = 8.0          # rad/s of body spin that starts making him dizzy
DIZZY_AFTER_S = 0.5       # ...when kept up this long
DIZZY_FOR_S = 3.0
PROUD_FOR_S = 10.0
SHOCKED_FOR_S = 0.7
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 6


@dataclass
class MoodInputs:
    pending: int = 0
    overdue: int = 0
    away: bool = False
    focusing: bool = False


class MoodEngine:
    def __init__(self) -> None:
        self.inputs = MoodInputs()
        self._spin_time = 0.0
        self._dizzy_until = 0.0
        self._proud_until = 0.0
        self._shocked_until = 0.0

    # ---- events ----

    def notice_spin(self, now: float, dt: float, spin_speed: float) -> None:
        """Feed the body's angular speed every frame."""
        if abs(spin_speed) > DIZZY_SPIN:
            self._spin_time += dt
            if self._spin_time >= DIZZY_AFTER_S:
                self._dizzy_until = now + DIZZY_FOR_S
        else:
            self._spin_time = 0.0

    def notice_completion(self, now: float) -> None:
        self._proud_until = now + PROUD_FOR_S

    def startle(self, now: float) -> None:
        self._shocked_until = now + SHOCKED_FOR_S

    # ---- evaluation ----

    def evaluate(self, now: float, hour: int) -> str:
        i = self.inputs
        if now < self._dizzy_until:
            return "dizzy"
        if now < self._shocked_until:
            return "shocked"
        if now < self._proud_until:
            return "proud"
        if i.focusing:
            return "focused"
        if i.away or hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR:
            return "sleepy"
        if i.overdue > 0:
            return "worried"
        if i.pending == 0:
            return "happy"
        return "neutral"
