"""Pendulum physical model for swinging character dynamics.

Implements a simple physical pendulum with gravity, damping, and semi-
implicit Euler integration.  The model is deliberately lightweight and
decoupled from Qt so it can be tested without a GUI event loop.

The pendulum angle is stored in radians, positive = swinging right,
negative = swinging left.  Angle is clamped to +/- pi/4 (45 deg) to
prevent extreme excursions.
"""

from __future__ import annotations

import math

from typing import Any


GRAVITY: float = 9.81  # m/s² – default, overridden per-instance


class Pendulum:
    """Physical simple pendulum.

    Attributes
    ----------
    length : float
        Distance from pivot to centre of mass (metres).
    gravity : float
        Acceleration due to gravity (m/s²).
    damping : float
        Fraction of angular velocity lost per second (0 = undamped).
    max_angle : float
        Hard clamp to prevent unbounded rotation (radians).
    """

    def __init__(
        self,
        length: float = 3.0,
        gravity: float = GRAVITY,
        damping: float = 0.1,
        max_angle: float = math.pi / 4,
    ) -> None:
        self.length: float = length
        self.gravity: float = gravity
        self.damping: float = damping
        self.max_angle: float = max_angle

        # Angular state
        self.angle: float = 0.0          # current angle (radians)
        self.angular_velocity: float = 0.0  # rad/s

    # ------------------------------------------------------------------
    # Physics integration – fixed timestep
    # ------------------------------------------------------------------

    def integrate(self, dt: float, release_velocity: float = 0.0) -> None:
        """Advance the pendulum one fixed timestep.

        Parameters
        ----------
        dt : float
            Timestep in seconds (typically 1/120).
        release_velocity : float
            Initial angular velocity injected when the user releases the
            character after dragging (sign and magnitude contribute to the
            swing impulse).
        """
        # On the very first integration after a release, inject the
        # supplied velocity.  We detect "first step" by checking whether
        # the angular velocity is still at its initial zero value.
        if self.angular_velocity == 0.0 and release_velocity != 0.0:
            self.angular_velocity = release_velocity

        # Angular acceleration from gravity + damping
        # alpha = - (g / l) * sin(theta) - c * omega
        alpha = -(self.gravity / self.length) * math.sin(self.angle) - self.damping * self.angular_velocity

        # Normal incremental update
        self.angular_velocity += alpha * dt

        # Apply damping factor (energy loss per timestep)
        self.angular_velocity *= 1.0 - self.damping * dt

        # Update angle
        self.angle += self.angular_velocity * dt

        # Clamp to maximum excursion so the character never swings past
        # 45 degrees from vertical in idle or drag states.
        self.angle = max(-self.max_angle, min(self.max_angle, self.angle))

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<Pendulum angle={self.angle:.3f} omega={self.angular_velocity:.3f}>"