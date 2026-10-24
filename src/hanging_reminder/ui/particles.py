"""Tiny particle system for celebrations (web confetti) and sleepy "z"s.

Coordinates are window-local pixels.  :meth:`ParticleSystem.bounding_rect`
lets the overlay extend its repaint area and click-through shape mask
while particles are alive.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

GRAVITY = 900.0
DRAG = 1.2
CONFETTI_COLORS = (QColor(210, 34, 40), QColor(40, 70, 170), QColor(250, 250, 250))


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float          # seconds remaining
    max_life: float
    color: QColor
    kind: str = "web"    # "web" | "dot" | "z"
    angle: float = 0.0
    spin: float = 0.0
    size: float = 7.0
    gravity: float = GRAVITY


class ParticleSystem:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.particles: list[Particle] = []
        self._rng = rng or random.Random()

    @property
    def alive(self) -> bool:
        return bool(self.particles)

    def burst(self, x: float, y: float, count: int = 36, speed: float = 520.0) -> None:
        """Confetti explosion from (x, y), biased upwards."""
        r = self._rng
        for _ in range(count):
            a = r.uniform(-math.pi, 0.0)  # upper half
            v = r.uniform(0.35, 1.0) * speed
            life = r.uniform(1.1, 1.9)
            self.particles.append(Particle(
                x, y, math.cos(a) * v, math.sin(a) * v - 150.0, life, life,
                r.choice(CONFETTI_COLORS), r.choice(("web", "web", "dot")),
                r.uniform(0, math.tau), r.uniform(-9, 9), r.uniform(5.0, 9.0),
            ))

    def float_z(self, x: float, y: float) -> None:
        """One sleepy "z" drifting up and away."""
        r = self._rng
        self.particles.append(Particle(
            x, y, r.uniform(10, 30), -45.0, 2.2, 2.2, QColor(245, 245, 245),
            "z", 0.0, 0.0, r.uniform(11, 16), gravity=0.0,
        ))

    def update(self, dt: float) -> None:
        kept = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0.0:
                continue
            p.vy += p.gravity * dt
            damp = math.exp(-DRAG * dt)
            p.vx *= damp
            p.vy *= damp
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.angle += p.spin * dt
            kept.append(p)
        self.particles = kept

    def bounding_rect(self) -> QRectF:
        if not self.particles:
            return QRectF()
        xs = [p.x for p in self.particles]
        ys = [p.y for p in self.particles]
        pad = 20.0
        return QRectF(min(xs) - pad, min(ys) - pad,
                      max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)

    def paint(self, painter: QPainter) -> None:
        for p in self.particles:
            fade = min(1.0, p.life / (p.max_life * 0.4))
            color = QColor(p.color)
            color.setAlphaF(fade)
            painter.save()
            painter.translate(p.x, p.y)
            painter.rotate(math.degrees(p.angle))
            if p.kind == "z":
                font = QFont("Sans", int(p.size))
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QPen(color))
                painter.drawText(QRectF(-10, -10, 20, 20), int(Qt.AlignmentFlag.AlignCenter), "z")
            elif p.kind == "dot":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(QPointF(0, 0), p.size * 0.35, p.size * 0.35)
            else:  # little web star
                painter.setPen(QPen(color, 1.6))
                for i in range(3):
                    a = i * math.pi / 3
                    dx, dy = math.cos(a) * p.size, math.sin(a) * p.size
                    painter.drawLine(QPointF(-dx, -dy), QPointF(dx, dy))
            painter.restore()
