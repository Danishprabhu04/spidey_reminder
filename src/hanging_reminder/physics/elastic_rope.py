"""2-D elastic web (bungee) model for the free-swinging character.

The character's feet hang from an anchor point by an elastic web.  All
quantities are in screen pixels and seconds so the UI can use the state
directly.  The model is decoupled from Qt so it can be tested headless.

State
-----
- ``x, y`` / ``vx, vy``   : feet position / velocity (end of the web).
- ``tilt`` / ``tilt_vel`` : body rotation (radians, 0 = hanging straight
  down, positive = swung right).  Follows the web direction through an
  under-damped angular spring and is NOT clamped, so a hard fling can
  spin the character all the way around.
- ``z`` / ``vz``          : depth wobble (front/back), a damped spring the
  renderer maps to scale/shading.

Interaction
-----------
- ``grab(tx, ty)`` pulls the feet toward a target with a stiff
  mouse-joint spring (elastic follow instead of teleporting).
- ``release()`` drops the joint; the body keeps its momentum.
- ``shoot_web(ax, ay)`` re-attaches the web at a new anchor.  The new web
  starts at the current distance and reels back to its rest length, so
  the character is yanked up with a springy yo-yo bounce.
"""

from __future__ import annotations

import math


# Body / web
GRAVITY = 1800.0           # px/s²
WEB_STIFFNESS = 72.0       # pull per px of stretch (unit mass)
WEB_SLACK_STIFFNESS = 0.12 # fraction of stiffness pushing back when compressed
LINEAR_DAMPING = 0.9       # 1/s – velocity loss
AIR_DRAG = 0.0004          # quadratic drag coefficient
MAX_SPEED = 4000.0         # px/s – keeps the integration stable

# Reeling the web back to its rest length after a web shot
REEL_RATE = 3.5            # 1/s – exponential approach
ANCHOR_RATE = 22.0         # 1/s – anchor slide speed (~150 ms)

# Mouse joint
GRAB_STIFFNESS = 2500.0
GRAB_DAMPING = 85.0

# Body rotation
TILT_STIFFNESS = 60.0
TILT_DAMPING = 4.0
TILT_FLING_KICK = 0.004    # rad/s per px/s of sideways release speed

# Depth wobble (front / back)
DEPTH_STIFFNESS = 40.0
DEPTH_DAMPING = 3.0
DEPTH_FLING_KICK = 0.0004
DEPTH_SWING_COUPLING = 0.00035

# Wall bounce
RESTITUTION = 0.45


def _wrap(angle: float) -> float:
    """Wrap *angle* into (-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


class ElasticRope:
    """Unit-mass body hanging from an anchor by an elastic web."""

    def __init__(self, anchor_x: float, anchor_y: float, rest_length: float) -> None:
        self.rest_length: float = rest_length
        self.current_length: float = rest_length  # reels toward rest_length

        self.ax: float = anchor_x
        self.ay: float = anchor_y
        self.anchor_target_x: float = anchor_x
        self.anchor_target_y: float = anchor_y

        sag = GRAVITY / WEB_STIFFNESS
        self.x: float = anchor_x
        self.y: float = anchor_y + rest_length + sag
        self.vx: float = 0.0
        self.vy: float = 0.0

        self.tilt: float = 0.0
        self.tilt_vel: float = 0.0
        self.z: float = 0.0
        self.vz: float = 0.0

        # Extra acceleration (e.g. idle sway) applied every step
        self.force_x: float = 0.0
        self.force_y: float = 0.0

        # Optional (left, top, right, bottom) box the feet bounce inside
        self.bounds: tuple[float, float, float, float] | None = None

        self._grabbing: bool = False
        self._grab_x: float = 0.0
        self._grab_y: float = 0.0

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    @property
    def is_grabbed(self) -> bool:
        return self._grabbing

    def grab(self, target_x: float, target_y: float) -> None:
        """Pull the feet toward (target_x, target_y) until released."""
        self._grabbing = True
        self._grab_x, self._grab_y = self._clamp_point(target_x, target_y)

    def release(self) -> None:
        """Let go – the body keeps its velocity and gets a spin/depth kick."""
        if not self._grabbing:
            return
        self._grabbing = False
        self.tilt_vel += self.vx * TILT_FLING_KICK
        self.vz += math.hypot(self.vx, self.vy) * DEPTH_FLING_KICK

    def shoot_web(self, anchor_x: float, anchor_y: float) -> None:
        """Re-attach the web at a new anchor and reel back to rest length."""
        self.anchor_target_x = anchor_x
        self.anchor_target_y = anchor_y
        self.current_length = max(
            self.rest_length, math.hypot(self.x - anchor_x, self.y - anchor_y)
        )

    def stretch_ratio(self) -> float:
        """Current web length relative to its rest length (1.0 = relaxed)."""
        length = math.hypot(self.x - self.ax, self.y - self.ay)
        return length / self.rest_length if self.rest_length > 0 else 1.0

    def kinetic_energy(self) -> float:
        return 0.5 * (self.vx * self.vx + self.vy * self.vy)

    # ------------------------------------------------------------------
    # Integration – fixed timestep, semi-implicit Euler
    # ------------------------------------------------------------------

    def integrate(self, dt: float) -> None:
        """Advance the simulation by *dt* seconds."""
        # Anchor slides toward its target, web reels toward rest length
        k_anchor = 1.0 - math.exp(-ANCHOR_RATE * dt)
        self.ax += (self.anchor_target_x - self.ax) * k_anchor
        self.ay += (self.anchor_target_y - self.ay) * k_anchor
        self.current_length += (self.rest_length - self.current_length) * (
            1.0 - math.exp(-REEL_RATE * dt)
        )

        ax_acc = self.force_x
        ay_acc = GRAVITY + self.force_y

        # Web force along the strand
        dx = self.x - self.ax
        dy = self.y - self.ay
        dist = math.hypot(dx, dy)
        if dist > 1e-6:
            stretch = dist - self.current_length
            k = WEB_STIFFNESS if stretch > 0 else WEB_STIFFNESS * WEB_SLACK_STIFFNESS
            pull = -k * stretch / dist
            ax_acc += pull * dx
            ay_acc += pull * dy

        # Mouse joint
        if self._grabbing:
            ax_acc += GRAB_STIFFNESS * (self._grab_x - self.x) - GRAB_DAMPING * self.vx
            ay_acc += GRAB_STIFFNESS * (self._grab_y - self.y) - GRAB_DAMPING * self.vy

        # Damping + quadratic air drag
        speed = math.hypot(self.vx, self.vy)
        drag = LINEAR_DAMPING + AIR_DRAG * speed
        ax_acc -= drag * self.vx
        ay_acc -= drag * self.vy

        prev_vx = self.vx
        self.vx += ax_acc * dt
        self.vy += ay_acc * dt

        speed = math.hypot(self.vx, self.vy)
        if speed > MAX_SPEED:
            scale = MAX_SPEED / speed
            self.vx *= scale
            self.vy *= scale

        self.x += self.vx * dt
        self.y += self.vy * dt
        self._bounce_off_bounds()

        # Body rotation follows the web direction (unclamped)
        if dist > 1e-6:
            target = math.atan2(self.x - self.ax, self.y - self.ay)
            error = _wrap(target - self.tilt)
            tilt_acc = TILT_STIFFNESS * error - TILT_DAMPING * self.tilt_vel
            self.tilt_vel += tilt_acc * dt
            self.tilt += self.tilt_vel * dt
            if abs(self.tilt_vel) < 0.05 and abs(self.tilt) > math.pi:
                self.tilt = _wrap(self.tilt)

        # Depth wobble, nudged by sideways swing acceleration
        self.vz += (self.vx - prev_vx) * DEPTH_SWING_COUPLING
        z_acc = -DEPTH_STIFFNESS * self.z - DEPTH_DAMPING * self.vz
        self.vz += z_acc * dt
        self.z += self.vz * dt

    # ------------------------------------------------------------------
    # Bounds
    # ------------------------------------------------------------------

    def _clamp_point(self, px: float, py: float) -> tuple[float, float]:
        if self.bounds is None:
            return px, py
        left, top, right, bottom = self.bounds
        return min(max(px, left), right), min(max(py, top), bottom)

    def _bounce_off_bounds(self) -> None:
        if self.bounds is None:
            return
        left, top, right, bottom = self.bounds
        if self.x < left:
            self.x, self.vx = left, abs(self.vx) * RESTITUTION
        elif self.x > right:
            self.x, self.vx = right, -abs(self.vx) * RESTITUTION
        if self.y < top:
            self.y, self.vy = top, abs(self.vy) * RESTITUTION
        elif self.y > bottom:
            self.y, self.vy = bottom, -abs(self.vy) * RESTITUTION

    def __repr__(self) -> str:
        return (
            f"<ElasticRope feet=({self.x:.1f},{self.y:.1f}) "
            f"v=({self.vx:.1f},{self.vy:.1f}) tilt={self.tilt:.3f} z={self.z:.3f}>"
        )
