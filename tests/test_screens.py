"""Tests for multi-monitor geometry helpers."""

from __future__ import annotations

from hanging_reminder.ui.screens import overlay_area, shift_between


def test_overlay_avoids_exact_monitor_size():
    assert overlay_area((0, 0, 1920, 1080), (0, 0, 1920, 1080)) == (0, 0, 1920, 1079)
    assert overlay_area((0, 32, 1920, 1048), (0, 0, 1920, 1080)) == (0, 32, 1920, 1048)


def test_points_keep_their_global_position():
    # Left monitor work area origin (0, 32), right monitor (1920, 0)
    dx, dy = shift_between((0, 32), (1920, 0))
    local_on_left = (1900, 300)            # global (1900, 332)
    local_on_right = (local_on_left[0] + dx, local_on_left[1] + dy)
    assert local_on_right == (-20, 332)    # global (1900, 332) – unchanged
