"""Fixed-timestep physics simulation engine.

Provides the core simulation loop with fixed timestep steps and render
interpolation. All physics entities integrate using this engine so that
animation is independent of wall-clock frame rate.
"""

from __future__ import annotations

from typing import List


class SimulationEngine:
    """Fixed-timestep simulation driver.

    Uses a time accumulator pattern so that physics advances at a constant
    rate (1/120 s) regardless of how often the GUI timer fires.  Rendering
    receives interpolated state between the last and current simulation steps.
    """

    def __init__(self, dt: float = 1.0 / 120, max_substeps: int = 5) -> None:
        self.dt: float = dt
        self.max_substeps: int = max_substeps
        self._accumulator: float = 0.0
        self._entities: List[PhysicsEntity] = []

    # ------------------------------------------------------------------
    # Entity management
    # ------------------------------------------------------------------

    def add_entity(self, entity: PhysicsEntity) -> None:
        """Register a physics entity with the simulation."""
        self._entities.append(entity)

    def remove_entity(self, entity: PhysicsEntity) -> None:
        """Unregister a physics entity."""
        self._entities.remove(entity)

    # ------------------------------------------------------------------
    # Main update – called from the GUI timer with elapsed real time
    # ------------------------------------------------------------------

    def update(self, elapsed_real: float) -> None:
        """Advance simulation by *elapsed_real* seconds.

        The method accumulates real time and performs fixed-step sub-steps.
        Large elapsed values are clamped to prevent explosive jumps after
        window stalls or system scheduling delays.
        """
        # Clamp so a long stall doesn't produce infinite acceleration
        MAX_STEP = 0.25  # 250 ms maximum sub-step
        elapsed_real = min(elapsed_real, MAX_STEP)

        self._accumulator += elapsed_real

        # Perform whole sub-steps
        substeps = 0
        while self._accumulator >= self.dt and substeps < self.max_substeps:
            self._step(self.dt)
            self._accumulator -= self.dt
            substeps += 1

        # If we have a small residual (< dt) just carry it forward
        # If we have a large residual (e.g. after clamping), we could
        # perform a partial step, but we simply carry the remainder.

    # ------------------------------------------------------------------
    # Internal fixed-step integration
    # ------------------------------------------------------------------

    def _step(self, dt: float) -> None:
        """Integrate all entities by *dt* seconds."""
        for entity in self._entities:
            entity.integrate(dt)

    # ------------------------------------------------------------------
    # Interpolation – called after _update so renderables can fetch
    # last/current state pairs
    # ------------------------------------------------------------------

    def get_interpolant(self, t: float) -> float:
        """Return interpolation parameter in [0,1] given accumulator *t*.

        t is the accumulator value *after* the update (i.e. the residual).
        """
        return self._accumulator / self.dt if self.dt > 0 else 0.0


class PhysicsEntity:
    """Base class for objects participating in the simulation.

    Subclasses must implement ``integrate(dt)``.
    """

    def integrate(self, dt: float) -> None:
        """Update internal state by *dt* seconds.

        Called once per fixed timestep from ``SimulationEngine._step``.
        """
        raise NotImplementedError("Subclasses must implement integrate(dt)")  # pragma: no cover