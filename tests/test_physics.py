"""Tests for the physics engine modules – runnable without a GUI."""

from __future__ import annotations

import math
import pytest

from hanging_reminder.physics import SimulationEngine, Spring, Pendulum


# ---------------------------------------------------------------------------
# Spring tests
# ---------------------------------------------------------------------------

class TestSpring:
    """Hooke's law spring with damping."""

    def test_basic_integration(self):
        """Spring displacement decreases with damping."""
        s = Spring(rest_length=1.0, stiffness=150.0, damping=0.2)
        s.set_displacement(0.5, 0.0)
        s.integrate(1 / 120)
        # Displacement should have decreased (energy loss)
        assert s._displacement < 0.5

    def test_stiffness_effect(self):
        """Stiffer spring returns to rest faster."""
        soft = Spring(rest_length=1.0, stiffness=20.0, damping=0.2)
        hard = Spring(rest_length=1.0, stiffness=300.0, damping=0.2)

        soft.set_displacement(0.5, 0.0)
        hard.set_displacement(0.5, 0.0)

        for _ in range(10):
            soft.integrate(1 / 120)
            hard.integrate(1 / 120)

        # The softer spring should have larger displacement after same steps
        assert soft._displacement > hard._displacement

    def test_velocity_persistence(self):
        """Initial velocity is carried forward."""
        s = Spring(rest_length=1.0, stiffness=150.0, damping=0.2)
        s.set_displacement(0.0, 1.0)  # start with velocity
        s.integrate(1 / 120)
        assert s._velocity != 0.0


# ---------------------------------------------------------------------------
# Pendulum tests
# ---------------------------------------------------------------------------

class TestPendulum:
    """Physical simple pendulum."""

    def test_gravity_perturbation(self):
        """Gravity causes the pendulum to swing from vertical."""
        p = Pendulum(length=3.0, gravity=9.81, damping=0.0)
        # Start with some angle
        p.angle = math.radians(10)  # 10 degrees
        p.angular_velocity = 0.0
        p.integrate(1 / 120)
        # Angle should change due to gravity (no damping means it keeps oscillating)
        assert p.angle != math.radians(10)

    def test_damping_reduces_oscillation(self):
        """Higher damping reduces angular velocity faster."""
        low = Pendulum(length=3.0, gravity=9.81, damping=0.01)
        high = Pendulum(length=3.0, gravity=9.81, damping=0.5)

        low.angle = math.radians(10)
        low.angular_velocity = 0.0
        high.angle = math.radians(10)
        high.angular_velocity = 0.0

        # Run for enough steps to see damping effect (~2 seconds)
        steps = 240  # 240 * (1/120) = 2.0 seconds
        for _ in range(steps):
            low.integrate(1 / 120)
            high.integrate(1 / 120)

        # After 2 seconds, high damping should result in significantly smaller angle
        # The exact ratio depends on the physics, but high damping should be notably lower
        assert abs(high.angle) < abs(low.angle), (
            f"High damping ({abs(high.angle):.4f}) should reduce angle more than "
            f"low damping ({abs(low.angle):.4f})"
        )

    def test_max_angle_clamp(self):
        """Angle is clamped to max_angle."""
        p = Pendulum(length=1.0, gravity=9.81, damping=0.1, max_angle=math.radians(5))
        p.angle = math.radians(999)  # wildly out of range
        p.integrate(1 / 120)
        assert p.angle <= math.radians(5)
        assert p.angle >= -math.radians(5)


# ---------------------------------------------------------------------------
# Simulation engine tests
# ---------------------------------------------------------------------------

class TestSimulationEngine:
    """Fixed-timestep simulation driver."""

    def test_fixed_timestep(self):
        """Physics advances at constant rate regardless of caller elapsed time."""
        sim = SimulationEngine(dt=1.0 / 120)
        s = Spring(rest_length=1.0, stiffness=150.0, damping=0.2)
        sim.add_entity(s)

        # Call with various elapsed times – should always advance by whole sub-steps
        sim.update(1.0 / 60)   # 2 sub-steps
        sim.update(1.0 / 200)  # 0 sub-steps, residual accumulation
        sim.update(3.0 / 120)  # 3 sub-steps

        # Should not have crashed or accumulated unbounded residuals
        assert sim._accumulator >= 0

    def test_large_elapsed_time_clamp(self):
        """Large elapsed values after stalls don't cause explosive jumps."""
        sim = SimulationEngine(dt=1.0 / 120, max_substeps=3)
        s = Spring(rest_length=1.0, stiffness=150.0, damping=0.2)
        sim.add_entity(s)

        # Simulate a long stall (200ms = 25 sub-steps, but max_substeps=3)
        sim.update(0.200)

        # Spring state should be finite – no wild jumps
        assert math.isfinite(s._displacement)
        assert math.isfinite(s._velocity)

    def test_interpolant_bounded(self):
        """get_interpolant returns value in [0,1]."""
        sim = SimulationEngine(dt=1.0 / 120)
        result = sim.get_interpolant(0.5)
        assert 0.0 <= result <= 1.0