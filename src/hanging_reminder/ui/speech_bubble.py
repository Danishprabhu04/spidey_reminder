"""Speech bubble widget that appears beside the Spider-Man character.

Features:
- Rounded rectangle with a pointer directed at the character.
- Subtle opacity/scale entrance and exit animations (QPropertyAnimation).
- Text adapts to the current task state (no tasks, some tasks, many tasks).
- Does not steal focus or block desktop interaction.
- Always-on-top relative to the companion window, but with Qt.WindowType.Tool
  so it stays out of the taskbar.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Qt,
    QPoint,
    QRectF,
    QSize,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QEasingCurve,
    Property,
)
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget, QApplication


MIN_WIDTH = 120
MAX_WIDTH = 320
BUBBLE_PADDING = 12
BORDER_RADIUS = 14
STRIPE_HEIGHT = 5

BG_COLOR = QColor(30, 34, 44, 245)
ACCENT_COLOR = QColor(210, 40, 40)
TEXT_COLOR = QColor(235, 235, 235)


class SpeechBubble(QWidget):
    """Frameless transparent speech bubble with pointer aimed at the character."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Window flags – tool so bubble stays out of the taskbar
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # ---------------------------------------------------------
        # IMPORTANT: pose state must exist BEFORE the QPropertyAnimation
        # objects are constructed – the animation ctor reads the property
        # via the meta-object immediately (this caused the previous
        # "property metacall ReadProperty" AttributeError noise).
        # ---------------------------------------------------------
        self._opacity: float = 0.0
        self._scale: float = 1.0

        # Animations for entrance/exit
        self._fade_anim = QPropertyAnimation(self, b"opacity")
        self._fade_anim.setDuration(260)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._scale_anim = QPropertyAnimation(self, b"scale")
        self._scale_anim.setDuration(300)
        self._scale_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        self._anim_group = QSequentialAnimationGroup()
        self._anim_group.addAnimation(self._scale_anim)
        self._anim_group.addAnimation(self._fade_anim)

        # Message state
        self._message: str = ""
        self._animating_in: bool = False
        self._animating_out: bool = False
        self._exit_connected: bool = False

        # Position tracking – updated by the companion window
        self._anchor_pos: QPoint = QPoint(0, 0)

    # -------------------------------------------------------------------------
    # Qt properties – animated by QPropertyAnimation
    # -------------------------------------------------------------------------

    def set_opacity(self, v: float) -> None:
        self._opacity = float(v)
        self.update()

    def get_opacity(self) -> float:
        return self._opacity

    opacity = Property(float, fget=get_opacity, fset=set_opacity)

    def set_scale(self, v: float) -> None:
        self._scale = float(v)
        self.update()

    def get_scale(self) -> float:
        return self._scale

    scale = Property(float, fget=get_scale, fset=set_scale)

    # -------------------------------------------------------------------------
    # Public API – message & animation control
    # -------------------------------------------------------------------------

    def show_message(self, message: str | None = None) -> None:
        """Display a message in the bubble with an entrance animation."""
        self._animating_out = False

        if message is not None:
            self._message = message
        elif self._message == "":
            self._message = "Hey! Any unfinished missions?"

        self._animating_in = True
        self._fade_anim.stop()
        self._scale_anim.stop()
        self._fade_anim.setStartValue(self._opacity)
        self._fade_anim.setEndValue(1.0)
        self._scale_anim.setStartValue(0.8)
        self._scale_anim.setEndValue(1.0)
        self._anim_group.start()

        self._reposition()
        self.show()
        self.raise_()

    def hide_message(self) -> None:
        """Initiate the exit animation."""
        if self._animating_out or not self.isVisible():
            return
        self._animating_out = True
        self._fade_anim.stop()
        self._scale_anim.stop()
        self._fade_anim.setStartValue(self._opacity)
        self._fade_anim.setEndValue(0.0)
        self._scale_anim.setStartValue(self._scale)
        self._scale_anim.setEndValue(0.85)
        if not self._exit_connected:
            self._fade_anim.finished.connect(self._on_exit_animation_finished)
            self._exit_connected = True
        self._fade_anim.start()

    # -------------------------------------------------------------------------
    # Positioning – called by the companion window with character screen pos
    # -------------------------------------------------------------------------

    def update_anchor(self, char_screen_pos: QPoint) -> None:
        """Set the character screen position for pointer direction."""
        self._anchor_pos = char_screen_pos
        self._reposition()

    # -------------------------------------------------------------------------
    # Geometry helpers
    # -------------------------------------------------------------------------

    def minimumSizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(MIN_WIDTH, 60)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(MAX_WIDTH, 90)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._reposition()

    def _reposition(self) -> None:
        """Position the bubble near the character, flipping sides at edges."""
        if self.parent() is None:
            return

        cx, cy = self._anchor_pos.x(), self._anchor_pos.y()

        bubble_w = min(MAX_WIDTH, max(MIN_WIDTH, len(self._message) * 7 + 48))
        bubble_h = 58 + BUBBLE_PADDING * 2

        screen = QApplication.screenAt(QPoint(cx, cy))
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.availableGeometry()

        bx = cx + 24
        by = cy - bubble_h / 2

        if bx + bubble_w > geom.right():
            bx = cx - bubble_w - 24
        if bx < geom.left():
            bx = geom.left() + 8

        if by < geom.top():
            by = geom.top() + 8
        if by + bubble_h > geom.bottom():
            by = geom.bottom() - bubble_h - 8

        self.setGeometry(int(bx), int(by), int(bubble_w), int(bubble_h))

    # -------------------------------------------------------------------------
    # Painting – rounded rect + pointer
    # -------------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        s = self._scale
        cx = self.width() / 2
        cy = self.height() / 2

        painter.translate(cx, cy)
        painter.scale(s, s)
        painter.translate(-cx, -cy)
        painter.setOpacity(self._opacity)

        w, h = float(self.width()), float(self.height())

        # Background rounded rect
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), BORDER_RADIUS, BORDER_RADIUS)
        painter.setBrush(QBrush(BG_COLOR))
        painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
        painter.drawPath(path)

        # Accent stripe at top
        stripe = QPainterPath()
        stripe.addRoundedRect(QRectF(0, 0, w, STRIPE_HEIGHT + BORDER_RADIUS), BORDER_RADIUS, BORDER_RADIUS)
        painter.setBrush(QBrush(ACCENT_COLOR))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(stripe)

        # Pointer triangle at bottom-left (aimed roughly at the character)
        pointer = QPainterPath()
        px = 28.0
        pointer.moveTo(px - 9, h - 1)
        pointer.lineTo(px + 9, h - 1)
        pointer.lineTo(px, h + 9)
        pointer.closeSubpath()
        painter.setBrush(QBrush(BG_COLOR))
        painter.drawPath(pointer)

        # Message text
        font = QFont("Sans", 11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(TEXT_COLOR))
        text_rect = QRectF(
            BUBBLE_PADDING,
            BUBBLE_PADDING + STRIPE_HEIGHT,
            w - BUBBLE_PADDING * 2,
            h - BUBBLE_PADDING * 2 - STRIPE_HEIGHT,
        )
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap),
            self._message,
        )
        painter.end()

    # -------------------------------------------------------------------------
    # Animation event handlers
    # -------------------------------------------------------------------------

    def _on_exit_animation_finished(self) -> None:
        self.hide()
        self._animating_out = False
