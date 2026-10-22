"""Spring model based on Hooke's law with viscous damping.

The spring exerts a restoring force F = -k * x - c * v where:
  k = stiffness (spring constant)
  c = damping coefficient
  x = displacement from rest length
  v = relative velocity
"""

from __future__ import annotations

from typing import Any


class Spring:
    """1D Hookean spring with damping.

    Attributes
    ----------
    rest_length : float
        Natural length of the spring at which no force is exerted.
    stiffness : float
        Spring constant k (higher = stiffer).
    damping : float
        Viscous damping coefficient c (0 <= c < 1 for underdamped).
    """

    def __init__(self, rest_length: float = 1.0, stiffness: float = 150.0, damping: float = 0.2) -> None:
        self.rest_length: float = rest_length
        self.stiffness: float = stiffness
        self.damping: float = damping

        # Internal state – displacement and velocity from the perspective
        # of the two connected bodies (set by the caller in integrate()).
        self._displacement: float = 0.0
        self._velocity: float = 0.0

    # ------------------------------------------------------------------
    # Physics integration – fixed timestep
    # ------------------------------------------------------------------

    def integrate(self, dt: float) -> None:
        """Advance the spring one fixed timestep.

        The spring force is Hooke's law + viscous damping:
            F = -stiffness * displacement - damping * velocity

        This updates the internal displacement/velocity assuming a unit mass
        (acceleration = force).  The caller (e.g. a pendulum with attached
        spring) applies the resulting force/torque appropriately.
        """
        # Compute acceleration from spring force (unit mass => a = F)
        acceleration = -self.stiffness * self._displacement - self.damping * self._velocity

        # Semi-implicit Euler: update velocity then position
        self._velocity += acceleration * dt
        self._displacement += self._velocity * dt

        # Light damping is already in the force; add explicit numerical
        # damping to prevent slow energy drift
        self._velocity *= 0.999  # negligible per-step loss

    # ------------------------------------------------------------------
    # Public API – set displacement from external forces
    # ------------------------------------------------------------------

    def set_displacement(self, displacement: float, velocity: float = 0.0) -> None:
        """Set the spring's current displacement and optional velocity.

        Useful when initializing or resetting the spring after a user
        interaction (e.g. releasing a dragged character).
        """
        self._displacement = displacement
        self._velocity = velocity

    # ------------------------------------------------------------------
    # Serialisation / inspection
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<Spring stiffness={self.stiffness} damping={self.damping} disp={self._displacement:.3f}>"