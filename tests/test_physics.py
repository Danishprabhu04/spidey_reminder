"""Tests for the physics engine modules – runnable without a GUI."""

from __future__ import annotations

import math
import pytest

from hanging_reminder.physics import SimulationEngine, Spring, Pendulum, ElasticRope


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

# ---------------------------------------------------------------------------
# Elastic rope tests
# ---------------------------------------------------------------------------

def _run(rope, seconds, dt=1 / 120):
    for _ in range(int(seconds / dt)):
        rope.integrate(dt)


class TestElasticRope:
    """2-D elastic web the character hangs from."""

    def test_settles_below_anchor(self):
        """From rest the feet hang straight below the anchor."""
        rope = ElasticRope(anchor_x=500, anchor_y=0, rest_length=180)
        rope.vx = 300.0
        _run(rope, 20)
        assert rope.x == pytest.approx(500, abs=2)
        assert rope.y > 180  # rest length plus gravity sag
        assert abs(rope.vx) < 1 and abs(rope.vy) < 1

    def test_stretch_bounces_back(self):
        """A stretched web recoils past the rest point before settling."""
        rope = ElasticRope(anchor_x=0, anchor_y=0, rest_length=180)
        _run(rope, 20)
        rest_y = rope.y
        rope.y += 300
        min_y = rope.y
        for _ in range(240):
            rope.integrate(1 / 120)
            min_y = min(min_y, rope.y)
        assert min_y < rest_y - 20  # overshoot = bounce
        _run(rope, 20)
        assert rope.y == pytest.approx(rest_y, abs=2)

    def test_tilt_is_unclamped(self):
        """A hard sideways fling swings well past the old 0.7 rad limit."""
        rope = ElasticRope(anchor_x=0, anchor_y=0, rest_length=180)
        _run(rope, 5)
        rope.vx = 2500.0
        max_tilt = 0.0
        for _ in range(240):
            rope.integrate(1 / 120)
            max_tilt = max(max_tilt, abs(rope.tilt))
        assert max_tilt > 0.7
        _run(rope, 30)
        assert abs(math.atan2(math.sin(rope.tilt), math.cos(rope.tilt))) < 0.05

    def test_extreme_velocity_stays_finite(self):
        rope = ElasticRope(anchor_x=0, anchor_y=0, rest_length=180)
        rope.vx, rope.vy = 1e7, -1e7
        _run(rope, 2)
        for value in (rope.x, rope.y, rope.vx, rope.vy, rope.tilt, rope.z):
            assert math.isfinite(value)

    def test_grab_follows_target_and_release_keeps_momentum(self):
        rope = ElasticRope(anchor_x=0, anchor_y=0, rest_length=180)
        for _ in range(120):
            rope.grab(400, 300)
            rope.integrate(1 / 120)
        assert rope.x == pytest.approx(400, abs=15)
        assert rope.y == pytest.approx(300, abs=15)
        rope.vx = 800.0
        rope.release()
        assert not rope.is_grabbed
        assert rope.tilt_vel != 0.0 and rope.vz > 0.0

    def test_shoot_web_reels_back_to_rest(self):
        rope = ElasticRope(anchor_x=0, anchor_y=0, rest_length=180)
        rope.x, rope.y = 600, 700
        rope.shoot_web(600, 0)
        assert rope.current_length > 600
        _run(rope, 20)
        assert rope.ax == pytest.approx(600)
        assert rope.x == pytest.approx(600, abs=2)
        assert rope.stretch_ratio() < 1.2

    def test_bounds_keep_body_inside(self):
        rope = ElasticRope(anchor_x=100, anchor_y=0, rest_length=180)
        rope.bounds = (0, 0, 200, 400)
        rope.vx = -3000.0
        for _ in range(240):
            rope.integrate(1 / 120)
            assert 0 <= rope.x <= 200 and 0 <= rope.y <= 400

    def test_rebound_callback_fires_once_per_big_stretch(self):
        rope = ElasticRope(anchor_x=0, anchor_y=0, rest_length=180)
        _run(rope, 10)
        hits = []
        rope.on_rebound = hits.append
        rope.vy = 1500.0  # yank down hard
        _run(rope, 0.6)
        assert len(hits) == 1 and hits[0] >= 1.5

    def test_stiffness_is_per_instance(self):
        soft = ElasticRope(anchor_x=0, anchor_y=0, rest_length=180, stiffness=40)
        hard = ElasticRope(anchor_x=0, anchor_y=0, rest_length=180, stiffness=200)
        _run(soft, 20)
        _run(hard, 20)
        assert soft.y > hard.y  # softer web sags further

    def test_flip_completes_full_turns_then_settles(self):
        rope = ElasticRope(anchor_x=0, anchor_y=0, rest_length=180)
        _run(rope, 10)
        start = rope.tilt
        rope.flip(turns=1.0, duration=0.5)
        _run(rope, 0.6)
        assert abs(rope.tilt - start) >= 2 * math.pi * 0.95
        _run(rope, 20)
        assert abs(math.atan2(math.sin(rope.tilt), math.cos(rope.tilt))) < 0.05
