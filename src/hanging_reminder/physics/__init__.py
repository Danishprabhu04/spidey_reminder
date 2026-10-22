"""Physics engine for Spider-Man Hanging Reminder.

Exposes :class:`SimulationEngine`, :class:`Spring`, and :class:`Pendulum`
for use by the UI and interaction layers.
"""

from __future__ import annotations

from .simulation import SimulationEngine
from .spring import Spring
from .pendulum import Pendulum

__all__ = ["SimulationEngine", "Spring", "Pendulum"]