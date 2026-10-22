"""Frameless, transparent, always-on-top desktop overlay for the Spider-Man companion.

The window covers the screen's work area (below the GNOME top bar) so
Spidey can swing anywhere without being clipped.  Everything except
Spidey and his web is click-through: the window's shape mask is rebuilt
every frame around the sprite and the strand.

Spidey hangs UPSIDE DOWN from an elastic web (:class:`ElasticRope`):
- Drag him and the web stretches like a bungee.
- Let go and he flings, bounces and swings freely (no angle limit), then
  springs back up his web to its one fixed anchor under his tray icon.
- Drop him at the top bar to move that anchor (it is saved in the config).
- Tap him (press + release without dragging) to see your pending tasks.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import (
    Qt,
    QElapsedTimer,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRegion,
    QTransform,
)
from PySide6.QtWidgets import QWidget, QApplication

from hanging_reminder.physics import ElasticRope, SimulationEngine
from hanging_reminder.config import AppConfig


# ---------------------------------------------------------------------------
# Window constants / defaults
# ---------------------------------------------------------------------------

DEFAULT_CHARACTER_SIZE = 90          # nominal pixel size (square)

# Layout factors (relative to config.character_size)
CHAR_SCALE = 1.6        # rendered sprite size = character_size * CHAR_SCALE
WEB_LENGTH_FACTOR = 2.2 # web strand length = character_size * WEB_LENGTH_FACTOR
SPRITE_SUPERSAMPLE = 2  # sprite is pre-rendered at this × device pixel ratio

# Idle animation – tiny periodic sideways force (px/s²)
IDLE_SWAY_FORCE = 45.0
IDLE_SWAY_FREQ_1 = 1.05
IDLE_SWAY_FREQ_2 = 2.30

# Interaction
DRAG_THRESHOLD_PX = 6       # movement before a press becomes a drag
TAP_MAX_MS = 350            # longer presses without movement are ignored
EDGE_MARGIN = 12            # keep the feet this far from the work-area edges
PIN_ZONE_PX = 70            # dropping the feet this close to the top re-pins the web

# Rendering
MAX_DT = 0.05               # clamp frame time after stalls (seconds)
WEB_MASK_STEP = 5.0         # sampling distance for the web's shape mask
WEB_MASK_WIDTH = 6          # mask thickness around the strand


class CompanionWindow(QWidget):
    """Transparent full work-area overlay hosting the hanging Spider-Man.

    Layout
    ------
        (anchor on the top bar)
               ,|,          <- elastic web strand (sags when slack)
                |
               \\o/         <- feet gripping the strand (upside down)
              [body]
             ( BIG HEAD )   <- chibi head with big white eyes
    """

    tasks_requested = Signal(QPoint)    # tap on Spidey – global head position
    character_moved = Signal(QPoint)    # every frame – global head position

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, config: AppConfig | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Configuration
        self.config = config or AppConfig()

        # Track session type BEFORE flag setup (needed by _setup_window_flags)
        self._session_type: str = self._detect_session_type()

        # Attributes for transparency
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAutoFillBackground(False)

        # Window flags – frameless + always-on-top, out of the taskbar
        self._setup_window_flags()

        # Layout metrics
        base = max(60, self.config.character_size)
        self._char_px: int = int(base * CHAR_SCALE)
        self._web_length: float = base * WEB_LENGTH_FACTOR

        # Character sprite – upside-down chibi Spidey, drawn programmatically
        self._character_pixmap: QPixmap = self._build_sprite()

        # Physics – elastic web from the top bar
        self._rope = ElasticRope(0.0, 0.0, self._web_length)
        self._simulation = SimulationEngine(dt=1.0 / 120, max_substeps=8)
        self._simulation.add_entity(self._rope)

        # Interaction state
        self._pressed: bool = False
        self._is_dragging: bool = False
        self._press_pos: QPointF = QPointF()
        self._press_ms: int = 0
        self._grab_offset: QPointF = QPointF()
        self._press_clock: QElapsedTimer = QElapsedTimer()

        # Painting / mask bookkeeping
        self._last_dirty: QRect = QRect()
        self._last_mask_key: tuple = ()

        # Render loop – synced to the display refresh rate
        self._frame_clock: QElapsedTimer = QElapsedTimer()
        self._frame_timer: QTimer = QTimer(self)
        self._frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._frame_timer.timeout.connect(self._on_frame)

        # Cover the work area of the primary monitor
        self._reposition_to_monitor()

        # info log
        from hanging_reminder.logging_config import logger
        logger.info("CompanionWindow initialized over %s", self.geometry())

    # ------------------------------------------------------------------
    # Window flag setup – session aware
    # ------------------------------------------------------------------

    def _setup_window_flags(self) -> None:
        """Set Qt window flags for a click-through, always-on-top overlay."""
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setWindowFlags(flags)

    # ------------------------------------------------------------------
    # Session type detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_session_type() -> str:
        """Detect whether Qt is running on X11 (incl. XWayland) or Wayland."""
        import os
        qt_plat = os.environ.get("QT_QPA_PLATFORM", "").lower()
        if "wayland" in qt_plat:
            return "wayland"
        if not qt_plat and os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            return "wayland"
        return "x11"

    # ------------------------------------------------------------------
    # Monitor positioning
    # ------------------------------------------------------------------

    def _reposition_to_monitor(self) -> None:
        """Cover the primary screen's work area; hang Spidey near the top-right."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        if area == screen.geometry():
            # A borderless window exactly the monitor's size is treated as
            # fullscreen by Mutter (hiding the top bar) – stay 1px short.
            area.setHeight(area.height() - 1)
        self.setGeometry(area)

        w, h = float(area.width()), float(area.height())
        self._rope.bounds = (
            EDGE_MARGIN,
            EDGE_MARGIN,
            w - EDGE_MARGIN,
            h - self._char_px - EDGE_MARGIN,
        )

        home_x = self._home_anchor_x()
        self._rope.ax = self._rope.anchor_target_x = home_x
        self._rope.ay = self._rope.anchor_target_y = self._anchor_y()
        self._rope.current_length = self._rope.rest_length
        self._rope.x = home_x
        self._rope.y = self._rope.ay + self._web_length
        self._rope.vx = self._rope.vy = 0.0

        refresh = screen.refreshRate() or 60.0
        self._frame_timer.setInterval(max(6, int(1000.0 / min(refresh, 144.0))))

    def _home_anchor_x(self) -> float:
        """Fixed web anchor under the tray icon, kept on screen."""
        w = float(self.width())
        x = w - float(self.config.anchor_offset_right)
        return min(max(x, EDGE_MARGIN), w - EDGE_MARGIN)

    def _pin_anchor_here(self, x: float) -> None:
        """Move the fixed anchor to *x* and remember it across restarts."""
        self.config.anchor_offset_right = int(round(self.width() - x))
        self.config.save()

    @staticmethod
    def _anchor_y() -> float:
        """Web anchor height: the very top of the work area (under the top bar)."""
        return 1.0

    # ------------------------------------------------------------------
    # Sprite
    # ------------------------------------------------------------------

    def _build_sprite(self) -> QPixmap:
        """Pre-render the character at high resolution for crisp scaling."""
        ratio = max(1.0, self.devicePixelRatioF()) * SPRITE_SUPERSAMPLE
        pixmap = QPixmap(int(self._char_px * ratio), int(self._char_px * ratio))
        pixmap.fill(Qt.GlobalColor.transparent)
        self._render_character(pixmap)
        pixmap.setDevicePixelRatio(ratio)
        return pixmap

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _feet_point(self) -> QPointF:
        return QPointF(self._rope.x, self._rope.y)

    def _sprite_transform(self) -> QTransform:
        """Local sprite coords (feet at origin, hanging along +y) -> window coords."""
        rope = self._rope
        depth = max(-0.15, min(0.15, rope.z))
        stretch = max(-0.10, min(0.15, (rope.stretch_ratio() - 1.0) * 0.15))
        sy = (1.0 + depth) * (1.0 + stretch)
        sx = (1.0 + depth) / math.sqrt(1.0 + stretch)

        t = QTransform()
        t.translate(rope.x, rope.y)
        t.rotateRadians(-rope.tilt)
        t.scale(sx, sy)
        return t

    def _sprite_rect(self) -> QRectF:
        return QRectF(-self._char_px / 2.0, 0.0, self._char_px, self._char_px)

    def _character_center(self) -> QPointF:
        """Center of the character's head (for hit testing and bubbles)."""
        return self._sprite_transform().map(QPointF(0.0, self._char_px * 0.66))

    def head_global_pos(self) -> QPoint:
        return self.mapToGlobal(self._character_center().toPoint())

    def _web_control_point(self, anchor: QPointF, feet: QPointF) -> QPointF:
        """Quadratic control point: the web sags when slack, straight when taut."""
        slack = max(0.0, 1.0 - self._rope.stretch_ratio())
        mid = (anchor + feet) / 2.0
        sag = slack * self._web_length * 0.6
        return QPointF(mid.x() - self._rope.vx * 0.01 * slack, mid.y() + sag)

    def _web_path(self) -> QPainterPath:
        anchor = QPointF(self._rope.ax, self._rope.ay)
        feet = self._feet_point()
        path = QPainterPath(anchor)
        path.quadTo(self._web_control_point(anchor, feet), feet)
        return path

    # ------------------------------------------------------------------
    # Painting – the heart of the visual appearance
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Paint web strand + upside-down hanging character."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Fully transparent background (replace, don't blend)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(event.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # --- Web strand (anchor -> feet) ---
        self._draw_web(painter)

        # --- Character hanging below the feet, rotated with the swing ---
        depth = self._rope.z
        painter.save()
        painter.setTransform(self._sprite_transform())
        painter.setOpacity(1.0 + max(-0.15, min(0.0, depth)))  # dimmer when "behind"
        painter.drawPixmap(self._sprite_rect(), self._character_pixmap,
                           QRectF(self._character_pixmap.rect()))
        painter.restore()

        painter.end()

    def _draw_web(self, painter: QPainter) -> None:
        """Draw the elastic web strand; it thins out as it stretches."""
        anchor = QPointF(self._rope.ax, self._rope.ay)
        width = max(0.9, 1.8 / max(1.0, self._rope.stretch_ratio()))
        painter.setPen(QPen(QColor(245, 245, 245, 225), width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._web_path())

        # Tiny web tuft where the strand meets the top bar
        painter.setPen(QPen(QColor(245, 245, 245, 160), 1))
        for dx in (-4, 4):
            painter.drawLine(anchor, QPointF(anchor.x() + dx, anchor.y() + 7))

    # ------------------------------------------------------------------
    # Character sprite – chibi Spidey, upside down (feet top, head bottom)
    # ------------------------------------------------------------------

    def _render_character(self, pixmap: QPixmap) -> None:
        """Render the upside-down chibi Spider-Man onto the given pixmap.

        Matches the reference art: red boots gripping the web at the top,
        small blue body, arms dangling beside a BIG red head with the
        web-mask pattern and huge white eyes.
        """
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        s = float(pixmap.width())
        cx = s / 2.0

        red = QColor(196, 30, 34)
        red_dark = QColor(150, 18, 24)
        blue = QColor(30, 48, 122)
        blue_dark = QColor(20, 32, 90)
        white = QColor(250, 250, 250)
        outline = QColor(25, 18, 24)
        web_line = QColor(60, 12, 16, 220)

        def limb(rect: QRectF, fill: QColor, radius: float) -> None:
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            painter.fillPath(path, QBrush(fill))
            painter.setPen(QPen(outline, max(1.0, s * 0.012)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        # --- Feet & legs (top, gripping the web) ---
        limb(QRectF(cx - 0.155 * s, 0.015 * s, 0.14 * s, 0.20 * s), blue_dark, 0.05 * s)
        limb(QRectF(cx + 0.015 * s, 0.015 * s, 0.14 * s, 0.20 * s), blue_dark, 0.05 * s)
        # red boots
        limb(QRectF(cx - 0.165 * s, 0.0 * s, 0.16 * s, 0.085 * s), red, 0.04 * s)
        limb(QRectF(cx + 0.005 * s, 0.0 * s, 0.16 * s, 0.085 * s), red, 0.04 * s)

        # --- Torso (small, blue, red chest) ---
        limb(QRectF(cx - 0.155 * s, 0.165 * s, 0.31 * s, 0.27 * s), blue, 0.10 * s)
        # red chest emblem patch
        chest = QPainterPath()
        chest.addRoundedRect(QRectF(cx - 0.105 * s, 0.20 * s, 0.21 * s, 0.17 * s), 0.08 * s, 0.08 * s)
        painter.fillPath(chest, QBrush(red))
        painter.save()
        painter.setClipPath(chest)
        painter.setPen(QPen(web_line, 1))
        for i in range(1, 4):
            painter.drawLine(QPointF(cx - 0.105 * s, 0.20 * s + i * 0.045 * s),
                             QPointF(cx + 0.105 * s, 0.20 * s + i * 0.045 * s))
        painter.restore()

        # --- Arms dangling beside the head ---
        limb(QRectF(cx - 0.225 * s, 0.30 * s, 0.095 * s, 0.24 * s), blue_dark, 0.045 * s)
        limb(QRectF(cx + 0.13 * s, 0.30 * s, 0.095 * s, 0.24 * s), blue_dark, 0.045 * s)
        # red gloves
        glove_r = 0.058 * s
        for gx in (cx - 0.178 * s, cx + 0.178 * s):
            painter.setBrush(QBrush(red))
            painter.setPen(QPen(outline, max(1.0, s * 0.012)))
            painter.drawEllipse(QPointF(gx, 0.565 * s), glove_r, glove_r * 0.92)

        # --- Head (BIG, red, at the bottom) ---
        head_cy = 0.665 * s
        head_r = 0.305 * s
        head_path = QPainterPath()
        head_path.addEllipse(QPointF(cx, head_cy), head_r, head_r)
        painter.fillPath(head_path, QBrush(red))
        painter.setPen(QPen(outline, max(1.2, s * 0.015)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(head_path)

        # --- Web pattern on the mask (clipped to head) ---
        painter.save()
        painter.setClipPath(head_path)
        web_cy = head_cy - head_r * 0.05
        painter.setPen(QPen(web_line, max(1.0, s * 0.010)))
        n_rays = 12
        for i in range(n_rays):
            a = 2.0 * math.pi * i / n_rays + math.pi / n_rays
            painter.drawLine(
                QPointF(cx, web_cy),
                QPointF(cx + head_r * 1.1 * math.cos(a), web_cy + head_r * 1.1 * math.sin(a)),
            )
        for rr in (0.30, 0.58, 0.86, 1.08):
            painter.drawEllipse(QPointF(cx, web_cy), head_r * rr, head_r * rr)
        painter.restore()

        # --- HUGE white eyes (the chibi signature) ---
        for side in (-1, 1):
            eye_cx = cx + side * head_r * 0.40
            eye_cy = head_cy - head_r * 0.02
            painter.save()
            painter.translate(eye_cx, eye_cy)
            painter.rotate(side * 16.0)
            eye_path = QPainterPath()
            # teardrop-ish ellipse: taller than wide, dominating the face
            eye_path.addEllipse(
                QRectF(-head_r * 0.38, -head_r * 0.55, head_r * 0.76, head_r * 1.10)
            )
            painter.fillPath(eye_path, QBrush(white))
            painter.setPen(QPen(outline, max(1.4, s * 0.016)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(eye_path)
            painter.restore()

        painter.end()

    # ------------------------------------------------------------------
    # Mouse event handling – tap vs. elastic drag
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """Remember the press; it becomes a drag once the mouse moves."""
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        if not self._hit_test_character(pos):
            event.ignore()
            return

        self._pressed = True
        self._is_dragging = False
        self._press_pos = pos
        self._press_clock.start()
        self._grab_offset = self._feet_point() - pos
        event.accept()

    def _hit_test_character(self, pos: QPointF) -> bool:
        """Test whether *pos* falls on the (rotated, scaled) sprite."""
        inverse, ok = self._sprite_transform().inverted()
        if not ok:
            return False
        local = inverse.map(pos)
        r = self._sprite_rect().adjusted(6, 0, -6, 0)
        return r.contains(local)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        """Elastic drag – the web stretches while Spidey trails the cursor."""
        if not self._pressed:
            return
        pos = event.position()
        if not self._is_dragging:
            moved = pos - self._press_pos
            if math.hypot(moved.x(), moved.y()) < DRAG_THRESHOLD_PX:
                return
            self._is_dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

        target = pos + self._grab_offset
        self._rope.grab(target.x(), target.y())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        """Release – fling + shoot a new web, or treat as a tap."""
        if not self._pressed or event.button() != Qt.MouseButton.LeftButton:
            return
        self._pressed = False

        from hanging_reminder.logging_config import logger
        if self._is_dragging:
            self._is_dragging = False
            self.unsetCursor()
            self._rope.release()
            if self._rope.y < PIN_ZONE_PX:
                # Dropped at the top bar – pin the web here from now on
                self._pin_anchor_here(self._rope.x)
                logger.info("Web anchor pinned %d px from the right edge",
                            self.config.anchor_offset_right)
            # Spring back up the web to its fixed anchor
            self._rope.shoot_web(self._home_anchor_x(), self._anchor_y())
            logger.info("Released Spidey with v=(%.0f, %.0f)", self._rope.vx, self._rope.vy)
        elif self._press_clock.elapsed() <= TAP_MAX_MS:
            # A tap – a little startled hop, then show the to-do list
            self._rope.vy -= 220.0
            self._rope.vz += 0.6
            logger.info("Spidey tapped – showing tasks")
            self.tasks_requested.emit(self.head_global_pos())
        event.accept()

    # ------------------------------------------------------------------
    # Frame tick – physics, mask, repaint
    # ------------------------------------------------------------------

    def _on_frame(self) -> None:
        """Advance physics by real elapsed time and repaint the dirty area."""
        elapsed = self._frame_clock.restart() / 1000.0 if self._frame_clock.isValid() else 0.0
        if not self._frame_clock.isValid():
            self._frame_clock.start()

        if (
            not self._rope.is_grabbed
            and self.config.idle_animation
            and not self.config.reduced_motion
        ):
            t = time.monotonic()
            self._rope.force_x = IDLE_SWAY_FORCE * (
                math.sin(t * IDLE_SWAY_FREQ_1) + 0.5 * math.sin(t * IDLE_SWAY_FREQ_2)
            )
        else:
            self._rope.force_x = 0.0

        self._simulation.update(min(elapsed, MAX_DT))

        self._update_mask()
        dirty = self._dirty_rect()
        self.update(dirty.united(self._last_dirty))
        self._last_dirty = dirty

        self.character_moved.emit(self.head_global_pos())

    def _dirty_rect(self) -> QRect:
        """Window area covered by the web and the sprite this frame."""
        sprite = self._sprite_transform().mapRect(self._sprite_rect())
        web = self._web_path().boundingRect()
        return sprite.united(web).adjusted(-4, -4, 4, 4).toAlignedRect()

    def _update_mask(self) -> None:
        """Shape the window to Spidey + web so the rest is click-through."""
        key = (
            round(self._rope.x), round(self._rope.y), round(self._rope.ax),
            round(self._rope.ay), round(self._rope.tilt, 2), round(self._rope.z, 2),
        )
        if key == self._last_mask_key:
            return
        self._last_mask_key = key

        sprite = self._sprite_transform().map(QPolygonF(self._sprite_rect()))
        region = QRegion(sprite.toPolygon())

        # The web needs to be inside the shape too, or it won't be painted
        path = self._web_path()
        length = path.length()
        steps = max(1, int(length / WEB_MASK_STEP))
        half = WEB_MASK_WIDTH // 2
        for i in range(steps + 1):
            p = path.pointAtPercent(path.percentAtLength(length * i / steps))
            region += QRect(int(p.x()) - half, int(p.y()) - half,
                            WEB_MASK_WIDTH, WEB_MASK_WIDTH)
        # Web tuft at the anchor
        region += QRect(int(self._rope.ax) - 6, int(self._rope.ay) - 2, 13, 11)

        self.setMask(region)

    # ------------------------------------------------------------------
    # Show / hide
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Cover the work area with the final geometry and start animating."""
        super().showEvent(event)
        self._reposition_to_monitor()
        self._last_mask_key = ()
        self._update_mask()
        self._frame_clock.invalidate()
        self._frame_timer.start()

    def hideEvent(self, event) -> None:  # type: ignore[override]
        """Stop the render loop while hidden – zero CPU when toggled off."""
        super().hideEvent(event)
        self._frame_timer.stop()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._frame_timer.stop()
        event.accept()
