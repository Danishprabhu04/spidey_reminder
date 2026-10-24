"""Tests for mood selection, idle behaviours and particles (no GUI loop)."""

from __future__ import annotations

import random

import pytest

from hanging_reminder.ui.behaviors import MAX_GAP_S, MIN_GAP_S, IdleBehaviors
from hanging_reminder.ui.mood import DIZZY_FOR_S, PROUD_FOR_S, MoodEngine


class TestMood:
    def test_baseline_moods(self):
        m = MoodEngine()
        m.inputs.pending = 3
        assert m.evaluate(0.0, hour=14) == "neutral"
        m.inputs.pending = 0
        assert m.evaluate(0.0, hour=14) == "happy"
        m.inputs.overdue = 1
        assert m.evaluate(0.0, hour=14) == "worried"
        assert m.evaluate(0.0, hour=23) == "sleepy"
        m.inputs.away = True
        assert m.evaluate(0.0, hour=14) == "sleepy"
        m.inputs.focusing = True
        assert m.evaluate(0.0, hour=14) == "focused"

    def test_dizzy_needs_sustained_spin_and_wears_off(self):
        m = MoodEngine()
        m.inputs.pending = 1
        now = 0.0
        for _ in range(20):  # 0.33 s of spinning – not enough yet
            now += 1 / 60
            m.notice_spin(now, 1 / 60, 12.0)
        assert m.evaluate(now, 14) == "neutral"
        for _ in range(20):
            now += 1 / 60
            m.notice_spin(now, 1 / 60, 12.0)
        assert m.evaluate(now, 14) == "dizzy"
        assert m.evaluate(now + DIZZY_FOR_S + 0.1, 14) == "neutral"

    def test_proud_beats_worried_then_expires(self):
        m = MoodEngine()
        m.inputs.overdue = 2
        m.notice_completion(100.0)
        assert m.evaluate(101.0, 14) == "proud"
        assert m.evaluate(100.0 + PROUD_FOR_S + 1, 14) == "worried"

    def test_startle_is_brief(self):
        m = MoodEngine()
        m.inputs.pending = 1
        m.startle(5.0)
        assert m.evaluate(5.2, 14) == "shocked"
        assert m.evaluate(6.0, 14) == "neutral"


class TestIdleBehaviors:
    def test_waits_between_moves(self):
        b = IdleBehaviors(random.Random(1))
        assert MIN_GAP_S <= b.next_at <= MAX_GAP_S
        assert b.tick(b.next_at - 1, allowed=True, sleepy=False) is None
        action = b.tick(b.next_at, allowed=True, sleepy=False)
        assert action in ("swing", "yo_yo", "look_around")

    def test_disallowed_slot_is_skipped_and_rescheduled(self):
        b = IdleBehaviors(random.Random(2))
        due = b.next_at
        assert b.tick(due, allowed=False, sleepy=False) is None
        assert b.next_at > due

    def test_sleepy_dozes(self):
        b = IdleBehaviors(random.Random(3))
        assert b.tick(b.next_at, allowed=True, sleepy=True) == "doze"

    @pytest.mark.parametrize("home", [30.0, 960.0, 1890.0])
    def test_swing_target_stays_on_screen(self, home):
        b = IdleBehaviors(random.Random(4))
        for _ in range(50):
            x = b.swing_offset(home, 1920.0, 12.0)
            assert 12.0 <= x <= 1908.0


def test_particles_fall_and_expire():
    from PySide6.QtWidgets import QApplication  # QColor needs no app, but be safe
    from hanging_reminder.ui.particles import ParticleSystem

    QApplication.instance() or QApplication([])
    ps = ParticleSystem(random.Random(5))
    ps.burst(100, 100, count=20)
    assert ps.alive and not ps.bounding_rect().isEmpty()
    for _ in range(150):
        ps.update(1 / 60)
    assert not ps.alive
