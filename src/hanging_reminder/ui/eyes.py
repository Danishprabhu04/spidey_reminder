"""Animated mask eyes for the hanging Spidey.

The body sprite is rendered without eyes; these are painted every frame
on top of it, in sprite-local coordinates (feet at the origin, hanging
along +y; see ``CompanionWindow._sprite_transform``).  Spidey hangs upside
down, so his face's "up" points along +y in the sprite; painting flips y
so the eyes are drawn in an ordinary upright face frame (up = -y).

Expressions come from a handful of eased parameters so moods blend
smoothly instead of popping:

- ``openness``  : 1 = open, 0 = shut (blinks multiply this)
- ``happy``     : 0..1 – lower lid curves up into ^^ crescents
- ``lid_drop``  : 0..1 – upper lid lowers (sleepy)
- ``lid_slant`` : -1..1 – worried (inner corners up) .. focused (inner down)
- ``scale``     : eye size (shocked = bigger)
- ``spiral``    : 0..1 – dizzy spirals
- ``look``      : (x, y) in -1..1 – where the eyes point (face frame)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QTransform

# Geometry relative to the sprite size s (matches _render_character)
HEAD_CY = 0.665
HEAD_R = 0.305
EYE_X = 0.40      # × head radius from the centre line
EYE_Y = -0.02     # × head radius
EYE_W = 0.76      # × head radius
EYE_H = 1.10      # × head radius
EYE_TILT_DEG = 16.0
LOOK_RANGE = 0.14  # × head radius the eyes may shift toward the cursor

EASE_RATE = 10.0   # 1/s
BLINK_MIN_S, BLINK_MAX_S = 2.8, 6.5
BLINK_DURATION_S = 0.16

WHITE = QColor(250, 250, 250)
OUTLINE = QColor(25, 18, 24)


@dataclass
class EyeParams:
    openness: float = 1.0
    happy: float = 0.0
    lid_drop: float = 0.0
    lid_slant: float = 0.0
    scale: float = 1.0
    spiral: float = 0.0
    look: tuple[float, float] = (0.0, 0.0)


# Target expression for every mood
MOOD_EYES = {
    "neutral": EyeParams(),
    "happy": EyeParams(happy=0.55),
    "proud": EyeParams(happy=1.0, scale=1.05),
    "worried": EyeParams(lid_slant=-1.0, lid_drop=0.14, scale=0.95),
    "sleepy": EyeParams(lid_drop=0.62, openness=0.9),
    "dizzy": EyeParams(spiral=1.0),
    "shocked": EyeParams(scale=1.06),
    "focused": EyeParams(lid_slant=0.7, lid_drop=0.15),
}


@dataclass
class Eyes:
    """Eased eye state + blinking; call :meth:`update` then :meth:`paint`."""

    current: EyeParams = field(default_factory=EyeParams)
    target: EyeParams = field(default_factory=EyeParams)
    _blink_t: float = -1.0
    _next_blink: float = field(default_factory=lambda: random.uniform(BLINK_MIN_S, BLINK_MAX_S))
    _spin: float = 0.0

    def set_mood(self, mood: str, look: tuple[float, float] | None = None) -> None:
        base = MOOD_EYES.get(mood, MOOD_EYES["neutral"])
        self.target = EyeParams(**{**base.__dict__, "look": look or self.target.look})

    def set_look(self, look: tuple[float, float]) -> None:
        self.target.look = look

    def update(self, dt: float) -> None:
        k = 1.0 - math.exp(-EASE_RATE * dt)
        c, t = self.current, self.target
        for name in ("openness", "happy", "lid_drop", "lid_slant", "scale", "spiral"):
            value = getattr(c, name)
            setattr(c, name, value + (getattr(t, name) - value) * k)
        c.look = (c.look[0] + (t.look[0] - c.look[0]) * k,
                  c.look[1] + (t.look[1] - c.look[1]) * k)
        self._spin += dt * 9.0

        # Blinking (not while asleep-ish or dizzy)
        if self._blink_t >= 0.0:
            self._blink_t += dt
            if self._blink_t >= BLINK_DURATION_S:
                self._blink_t = -1.0
        else:
            self._next_blink -= dt
            if self._next_blink <= 0.0:
                self._blink_t = 0.0
                self._next_blink = random.uniform(BLINK_MIN_S, BLINK_MAX_S)

    def blink_factor(self) -> float:
        if self._blink_t < 0.0 or self.current.spiral > 0.5:
            return 1.0
        phase = self._blink_t / BLINK_DURATION_S  # 0 -> 1
        return max(0.08, abs(1.0 - 2.0 * phase))

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paint(self, painter: QPainter, s: float) -> None:
        """Paint both eyes for a sprite of size *s* (sprite-local coords)."""
        c = self.current
        r = HEAD_R * s
        painter.save()
        # Face frame: origin at the head centre; after the flip, face-up = -y
        painter.translate(0.0, HEAD_CY * s)
        painter.scale(1.0, -1.0)
        for side in (-1, 1):
            self._paint_eye(painter, side, r, s, c)
        painter.restore()

    def _paint_eye(self, painter: QPainter, side: int, r: float, s: float, c: EyeParams) -> None:
        look_x, look_y = c.look
        # The eye on the far side from where he looks narrows slightly
        narrow = 1.0 - 0.10 * max(0.0, -side * look_x)
        w = EYE_W * r * c.scale * narrow
        h = EYE_H * r * c.scale * max(0.06, c.openness * self.blink_factor())
        ex = side * EYE_X * r + look_x * LOOK_RANGE * r
        ey = -EYE_Y * r + look_y * LOOK_RANGE * r

        painter.save()
        painter.translate(ex, ey)
        painter.rotate(-side * EYE_TILT_DEG)
        eye = QPainterPath()
        eye.addEllipse(QRectF(-w / 2, -h / 2, w, h))
        full_h = EYE_H * r * c.scale

        # Happy: a lower lid bulging up turns the eye into a ^ crescent
        if c.happy > 0.02:
            lid_top = h / 2 - c.happy * h * 0.62
            lid = QPainterPath()
            lid.addEllipse(QRectF(-w * 0.8, lid_top, w * 1.6, full_h * 0.95))
            eye = eye.subtracted(lid)

        # Upper lid: drops when sleepy; slants for worried (inner corner up)
        # or focused (inner corner down).  The inner corner is at x = -side·w.
        if c.lid_drop > 0.02 or abs(c.lid_slant) > 0.02:
            y0 = -h / 2 + h * c.lid_drop
            d = c.lid_slant * h * 0.35
            lid = QPainterPath()
            lid.moveTo(-side * w, y0 + d)
            lid.lineTo(side * w, y0 - d)
            lid.lineTo(side * w, -h * 2)
            lid.lineTo(-side * w, -h * 2)
            lid.closeSubpath()
            eye = eye.subtracted(lid)

        painter.fillPath(eye, QBrush(WHITE))
        painter.setPen(QPen(OUTLINE, max(1.4, s * 0.016)))
        painter.setBrush(QBrush())
        painter.drawPath(eye)

        if c.spiral > 0.05:
            self._paint_spiral(painter, w, h, s, c.spiral, side)
        painter.restore()

    def _paint_spiral(self, painter: QPainter, w: float, h: float, s: float,
                      amount: float, side: int) -> None:
        path = QPainterPath()
        turns, steps = 2.5, 60
        radius = min(w, h) * 0.42
        for i in range(steps + 1):
            f = i / steps
            a = f * turns * 2 * math.pi + self._spin * side
            p = QPointF(math.cos(a) * radius * f, math.sin(a) * radius * f)
            path.moveTo(p) if i == 0 else path.lineTo(p)
        pen = QPen(OUTLINE, max(1.2, s * 0.013))
        color = QColor(OUTLINE)
        color.setAlphaF(min(1.0, amount))
        pen.setColor(color)
        painter.setPen(pen)
        painter.drawPath(path)


def look_vector(local_target: QPointF, s: float, reach: float = 260.0) -> tuple[float, float]:
    """Face-frame look direction toward a point in sprite-local coords."""
    dx = local_target.x()
    dy = local_target.y() - HEAD_CY * s
    dist = math.hypot(dx, dy)
    if dist < 1e-3:
        return (0.0, 0.0)
    strength = min(1.0, dist / reach)
    # face frame is flipped vertically
    return (dx / dist * strength, -dy / dist * strength)


def sprite_head_center(transform: QTransform, s: float) -> QPointF:
    return transform.map(QPointF(0.0, HEAD_CY * s))
