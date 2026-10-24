"""Screen geometry helpers for moving Spidey between monitors (pure)."""

from __future__ import annotations

from typing import Tuple

Rect = Tuple[int, int, int, int]  # x, y, width, height


def overlay_area(available: Rect, full: Rect) -> Rect:
    """Work area the overlay covers on one screen.

    A borderless window exactly the monitor's size is treated as fullscreen
    by Mutter (which hides the top bar), so stay 1px short in that case.
    """
    x, y, w, h = available
    if available == full:
        h -= 1
    return x, y, w, h


def shift_between(old_origin: Tuple[int, int], new_origin: Tuple[int, int]) -> Tuple[int, int]:
    """Offset to add to window-local points when the window moves origins."""
    return old_origin[0] - new_origin[0], old_origin[1] - new_origin[1]
