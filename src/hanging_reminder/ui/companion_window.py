"""Frameless, transparent, always-on-top desktop window for the Spider-Man companion.

The window hangs from the TOP EDGE of the screen (below the navbar):
a thin web strand descends from the top-center anchor point, and a
chibi-style Spider-Man hangs UPSIDE DOWN from it, swinging with real
pendulum physics around the anchor.

Handles:
- Translucent background with RGBA rendering.
- Pendulum swing around the web anchor (fixed timestep, ~60 FPS).
- Mouse drag/grab/release interactions.
- Idle sway so the character always feels alive.
- Todo button (opens/raises the mission list).
- Wayland/X11 session detection for appropriate window flags.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import (
    Qt,
    QPoint,
    QPointF,
    QRectF,
    QTimer,
    Signal,
    Property,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget, QApplication, QPushButton

from hanging_reminder.physics import Spring, Pendulum
from hanging_reminder.config import AppConfig


# ---------------------------------------------------------------------------
# Window constants / defaults
# ---------------------------------------------------------------------------

DEFAULT_CHARACTER_SIZE = 90          # nominal pixel size (square)
DEFAULT_ANCHOR_CORNER = "top-left"   # top-left, top-center, top-right

# Layout factors (relative to config.character_size)
CHAR_SCALE = 1.6        # rendered sprite size = character_size * CHAR_SCALE
WEB_LENGTH_FACTOR = 2.2 # web strand length = character_size * WEB_LENGTH_FACTOR
WINDOW_WIDTH_FACTOR = 2.2

# Idle animation
IDLE_SWAY_AMPLITUDE = 0.035   # radians (~2°)
IDLE_SWAY_FREQ_1 = 1.05       # Hz-ish
IDLE_SWAY_FREQ_2 = 2.30

# Drag constants
GRAVITY_COMPENSATION = 0.1


class CompanionWindow(QWidget):
    """Frameless transparent top-level widget hosting the hanging Spider-Man.

    Layout
    ------
        (top-center anchor)
               ,|,          <- web strand (slight sag)
                |
               \\o/         <- feet gripping the strand (upside down)
              [body]
             ( BIG HEAD )   <- chibi head with big white eyes
    """

    todo_toggle_requested = Signal()

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
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        # Window flags – frameless + always-on-top
        self._setup_window_flags()

        # Layout metrics
        base = max(60, self.config.character_size)
        self._char_px: int = int(base * CHAR_SCALE)
        self._web_length: float = base * WEB_LENGTH_FACTOR
        self.resize(int(base * WINDOW_WIDTH_FACTOR), int(self._web_length + self._char_px))

        # Internal state
        self._position: QPoint = QPoint(20, 20)
        self._is_dragging: bool = False
        self._grab_offset: QPoint = QPoint(-1, -1)
        self._previous_global_pos: QPoint = QPoint(0, 0)
        self._click_count: int = 0
        self._click_timer: QTimer = QTimer(self)
        self._click_timer.timeout.connect(self._reset_click_count)

        # Physics engines – pendulum swings around the top anchor
        self._spring = Spring(
            rest_length=self._web_length,
            stiffness=self.config.spring_stiffness,
            damping=self.config.damping,
        )
        self._pendulum = Pendulum(
            length=max(self._web_length / 100.0, 0.5),
            gravity=self.config.gravity,
            damping=self.config.damping,
            max_angle=self.config.max_angle,
        )

        # Character sprite – upside-down chibi Spidey, drawn programmatically
        self._character_pixmap: QPixmap = QPixmap(self._char_px, self._char_px)
        self._character_pixmap.fill(Qt.GlobalColor.transparent)
        self._render_character(self._character_pixmap)

        # Render loop – ~60 FPS
        self._hover_timer: QTimer = QTimer(self)
        self._hover_timer.setInterval(16)
        self._hover_timer.timeout.connect(self._on_physics_tick)
        self._hover_timer.start()

        # Todo button (mission list) – overlays top-right corner
        self._speech_bubble = None  # lazy-created speech bubble
        self._todo_button: QPushButton = QPushButton(self)
        self._todo_button.setText("\U0001F4DD")  # memo emoji
        self._todo_button.setToolTip("Mission list – click to write / view your todos")
        self._todo_button.setFixedSize(34, 34)
        self._todo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._todo_button.setStyleSheet(
            "QPushButton { background-color: rgba(28, 32, 42, 200);"
            " color: white; border: 1px solid rgba(255,255,255,60);"
            " border-radius: 17px; font-size: 15px; }"
            "QPushButton:hover { background-color: rgba(210, 40, 40, 220); }"
        )
        self._todo_button.clicked.connect(self.todo_toggle_requested.emit)
        self._position_todo_button()

        # Position the window on the primary monitor
        self._reposition_to_monitor()

        # info log
        from hanging_reminder.logging_config import logger
        logger.info("CompanionWindow initialized at %s", self._position)

    # ------------------------------------------------------------------
    # Window flag setup – session aware
    # ------------------------------------------------------------------

    def _setup_window_flags(self) -> None:
        """Set Qt window flags based on the detected session type."""
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        # On X11, bypass the compositor handler so the transparent window
        # composites correctly without being obscured by other windows.
        if self._session_type == "x11" and hasattr(Qt.WindowType, "X11BypassCompositorHandler"):
            flags |= Qt.WindowType.X11BypassCompositorHandler

        self.setWindowFlags(flags)

    # ------------------------------------------------------------------
    # Session type detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_session_type() -> str:
        """Detect whether we're running under X11 or Wayland."""
        try:
            import os
            qt_plat = os.environ.get("QT_QPA_PLATFORM", "")
            if "wayland" in qt_plat.lower():
                return "wayland"
        except Exception:
            pass
        return "x11"

    # ------------------------------------------------------------------
    # Monitor positioning
    # ------------------------------------------------------------------

    def _reposition_to_monitor(self) -> None:
        """Place the window hanging from the top-RIGHT corner of the screen."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        inset = 8  # small gap from the very right edge
        self._position = QPoint(
            geometry.right() - self.width() + inset, geometry.top()
        )
        self.move(self._position)

    def _position_todo_button(self) -> None:
        self._todo_button.move(self.width() - 42, 8)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._position_todo_button()

    # ------------------------------------------------------------------
    # Painting – the heart of the visual appearance
    # ------------------------------------------------------------------

    def _anchor_point(self) -> QPointF:
        """Web anchor: top-center of the window (at the navbar)."""
        return QPointF(self.width() / 2.0, 2.0)

    def _effective_angle(self) -> float:
        """Pendulum angle + subtle idle sway so Spidey is always alive."""
        theta = self._pendulum.angle
        if (
            not self._is_dragging
            and self.config.idle_animation
            and not self.config.reduced_motion
        ):
            t = time.monotonic()
            theta += IDLE_SWAY_AMPLITUDE * (
                math.sin(t * IDLE_SWAY_FREQ_1) + 0.5 * math.sin(t * IDLE_SWAY_FREQ_2)
            )
        return theta

    def _feet_point(self, theta: float | None = None) -> QPointF:
        """Character's feet (web attachment) position for the given angle."""
        if theta is None:
            theta = self._effective_angle()
        anchor = self._anchor_point()
        return QPointF(
            anchor.x() + math.sin(theta) * self._web_length,
            anchor.y() + math.cos(theta) * self._web_length,
        )

    def _character_center(self) -> QPointF:
        """Approximate center of the character sprite (for hit testing)."""
        theta = self._effective_angle()
        feet = self._feet_point(theta)
        d = self._char_px * 0.55
        return QPointF(
            feet.x() + math.sin(theta) * d,
            feet.y() + math.cos(theta) * d,
        )

    def paintEvent(self, event) -> None:  # type: ignore[override]
        """Paint web strand + upside-down hanging character."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Fully transparent background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))

        theta = self._effective_angle()
        feet = self._feet_point(theta)

        # --- Web strand (anchor -> feet, slight sag) ---
        self._draw_web(painter, self._anchor_point(), feet)

        # --- Character hanging below the feet, rotated with the swing ---
        painter.save()
        painter.translate(feet)
        painter.rotate(math.degrees(theta))
        painter.drawPixmap(
            int(-self._character_pixmap.width() / 2),
            0,
            self._character_pixmap,
        )
        painter.restore()

        painter.end()

    def _draw_web(self, painter: QPainter, anchor: QPointF, feet: QPointF) -> None:
        """Draw the web strand with a slight natural sag."""
        path = QPainterPath()
        path.moveTo(anchor)
        mid_x = (anchor.x() + feet.x()) / 2.0
        mid_y = (anchor.y() + feet.y()) / 2.0
        # Sag opposite to the swing for a lively feel
        path.quadTo(QPointF(mid_x, mid_y), feet)
        painter.setPen(QPen(QColor(245, 245, 245, 220), 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Tiny web tuft where the strand meets the navbar
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
    # Mouse event handling – drag / grab
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """Handle mouse press – initiate drag or show speech bubble."""
        from hanging_reminder.logging_config import logger

        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.position().toPoint()

        if self._hit_test_character(pos):
            logger.info("Mouse press on character at %s", pos)
            self._start_drag(pos)
        else:
            logger.info("Mouse press on background at %s", pos)
            self._on_background_click(pos)

        event.accept()

    def _hit_test_character(self, pos: QPoint) -> bool:
        """Test whether *pos* falls within the character's interaction region."""
        center = self._character_center()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        distance = math.hypot(dx, dy)
        return distance <= self._char_px * 0.55

    def _start_drag(self, pos: QPoint) -> None:
        """Initiate a drag gesture from the given window-local position."""
        self._is_dragging = True
        self._grab_offset = pos
        self._click_count = 0
        self._click_timer.stop()
        self._previous_global_pos = self.mapToGlobal(pos)

        from hanging_reminder.logging_config import logger
        logger.info("Drag started, grab_offset=%s", self._grab_offset)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        """Handle mouse drag movement – the whole window follows the cursor."""
        if not self._is_dragging:
            return

        global_pos = event.globalPosition().toPoint()
        delta = global_pos - self._previous_global_pos

        new_pos = self.pos() + delta
        new_pos = self._clamp_to_screen(new_pos)
        self.move(new_pos)
        self._position = new_pos

        # Feed drag velocity into the pendulum (fling feel)
        self._pendulum.angular_velocity += delta.x() * 0.0006

        self._previous_global_pos = global_pos
        event.accept()

    def _clamp_to_screen(self, pos: QPoint) -> QPoint:
        """Keep the top of the window attached to the screen top (hanging)."""
        screen = QApplication.screenAt(pos)
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return pos
        geom = screen.availableGeometry()

        margin = 10
        x = max(geom.left() + margin - self.width() // 2,
                min(pos.x(), geom.right() - margin - self.width() // 2))
        y = geom.top()  # always hang from the very top
        return QPoint(x, y)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        """Handle mouse release – fling into a natural swing."""
        if not self._is_dragging:
            return

        self._is_dragging = False
        self._click_timer.start(300)

        global_pos = event.globalPosition().toPoint()
        velocity = global_pos - self._previous_global_pos

        # Convert horizontal fling into pendulum angular velocity
        release_omega = max(-3.0, min(3.0, velocity.x() * 0.02))
        self._pendulum.angular_velocity = release_omega

        from hanging_reminder.logging_config import logger
        logger.info("Mouse release, release_omega=%.3f", release_omega)

        self._grab_offset = QPoint(-1, -1)

    # ------------------------------------------------------------------
    # Click handling – speech bubble
    # ------------------------------------------------------------------

    def _on_background_click(self, pos: QPoint) -> None:
        """Show the speech bubble on background clicks."""
        from hanging_reminder.ui.speech_bubble import SpeechBubble

        if self._speech_bubble is None:
            self._speech_bubble = SpeechBubble(parent=self)

        char_screen = self.mapToGlobal(
            QPoint(int(self._character_center().x()), int(self._character_center().y()))
        )
        self._speech_bubble.update_anchor(char_screen)
        self._speech_bubble.show_message()

        QTimer.singleShot(
            self.config.speech_bubble_duration,
            self._speech_bubble.hide_message,
        )

    def _reset_click_count(self) -> None:
        self._click_count = 0

    # ------------------------------------------------------------------
    # Physics tick (~60 FPS)
    # ------------------------------------------------------------------

    def _on_physics_tick(self) -> None:
        """One tick – integrate pendulum physics and repaint."""
        if not self._is_dragging:
            self._pendulum.integrate(1.0 / 60)
            self._spring.integrate(1.0 / 60)

            # Gentle settling toward vertical when energy is low
            if (
                abs(self._pendulum.angular_velocity) < self._settle_threshold()
                and abs(self._pendulum.angle) < self._settle_threshold() * 2
            ):
                self._pendulum.angle *= 0.97
                self._pendulum.angular_velocity *= 0.95

        self.update()

    def _settle_threshold(self) -> float:
        return math.radians(3.0)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Snap to the top-right corner with the final geometry on show."""
        super().showEvent(event)
        self._reposition_to_monitor()
        self._position_todo_button()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        event.accept()
