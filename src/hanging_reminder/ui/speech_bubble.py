"""Speech bubble widget that appears beside the Spider-Man character.

Features:
- Rounded rectangle with a pointer directed at the character.
- Subtle opacity/scale entrance and exit animations (QPropertyAnimation).
- Text adapts to the current task state (no tasks, some tasks, many tasks).
- Task-list mode (``show_tasks``): pending missions with priority dots and
  an "Open mission list" link.
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
    QTimer,
    Property,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget, QApplication


MIN_WIDTH = 120
MAX_WIDTH = 320
BUBBLE_PADDING = 12
BORDER_RADIUS = 14
STRIPE_HEIGHT = 5

BG_COLOR = QColor(30, 34, 44, 245)
ACCENT_COLOR = QColor(210, 40, 40)
TEXT_COLOR = QColor(235, 235, 235)
LINK_COLOR = QColor(255, 120, 120)
MUTED_TEXT_COLOR = QColor(170, 175, 185)

# Task-list mode
TASKS_WIDTH = 270
TASKS_MAX_ROWS = 5
TITLE_HEIGHT = 24
ROW_HEIGHT = 21
FOOTER_HEIGHT = 26
PRIORITY_COLORS = {
    "high": QColor(230, 130, 30),
    "normal": QColor(220, 50, 50),
    "low": QColor(30, 180, 80),
}


class SpeechBubble(QWidget):
    """Frameless transparent speech bubble with pointer aimed at the character."""

    open_panel_requested = Signal()
    dismissed = Signal()  # the user clicked the bubble

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
        self._tasks: list | None = None  # (title, priority) rows in task-list mode
        self._tasks_title: str | None = None
        self._animating_in: bool = False
        self._animating_out: bool = False
        self._exit_connected: bool = False

        # Position tracking – updated by the companion window
        self._anchor_pos: QPoint = QPoint(0, 0)

        # Auto-hide – restarted on every show so older taps can't hide early
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_message)

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
        self._tasks = None
        self._hide_timer.stop()

        if message is not None:
            self._message = message
        elif self._message == "":
            self._message = "Hey! Any unfinished missions?"

        self._animate_in()

    def show_tasks(self, tasks: list, duration_ms: int = 10000, title: str | None = None) -> None:
        """Show pending tasks as a list with an "Open mission list" link."""
        self._tasks = [(t.title, t.priority or "normal") for t in tasks]
        self._tasks_title = title
        self._animate_in()
        self._hide_timer.start(duration_ms)

    def _animate_in(self) -> None:
        self._animating_out = False
        self._animating_in = True
        self._fade_anim.stop()
        self._scale_anim.stop()
        self._fade_anim.setStartValue(self._opacity)
        self._fade_anim.setEndValue(1.0)
        self._scale_anim.setStartValue(0.8)
        self._scale_anim.setEndValue(1.0)
        self._anim_group.start()

        self._reposition()
        self.update()
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
        if char_screen_pos == self._anchor_pos:
            return
        self._anchor_pos = char_screen_pos
        if self.isVisible():
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

        bubble_w, bubble_h = self._bubble_size()

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

    def _bubble_size(self) -> tuple[int, int]:
        if self._tasks is None:
            return min(MAX_WIDTH, max(MIN_WIDTH, len(self._message) * 7 + 48)), 58 + BUBBLE_PADDING * 2
        rows = max(1, min(len(self._tasks), TASKS_MAX_ROWS))
        if len(self._tasks) > TASKS_MAX_ROWS:
            rows += 1  # "+N more"
        height = BUBBLE_PADDING * 2 + STRIPE_HEIGHT + TITLE_HEIGHT + rows * ROW_HEIGHT
        if self._tasks:
            height += FOOTER_HEIGHT
        return TASKS_WIDTH, height

    def _footer_rect(self) -> QRectF:
        return QRectF(
            BUBBLE_PADDING,
            self.height() - BUBBLE_PADDING - FOOTER_HEIGHT,
            self.width() - BUBBLE_PADDING * 2,
            FOOTER_HEIGHT,
        )

    # -------------------------------------------------------------------------
    # Mouse – footer opens the mission list, anywhere else dismisses
    # -------------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self._tasks and self._footer_rect().contains(event.position()):
            self.open_panel_requested.emit()
        self.hide_message()
        self.dismissed.emit()
        event.accept()

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

        if self._tasks is not None:
            self._paint_tasks(painter, w, h)
            painter.end()
            return

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

    def _paint_tasks(self, painter: QPainter, w: float, h: float) -> None:
        """Title, one row per pending task, then the footer link."""
        x = BUBBLE_PADDING
        y = BUBBLE_PADDING + STRIPE_HEIGHT
        inner_w = w - BUBBLE_PADDING * 2

        title_font = QFont("Sans", 11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QPen(TEXT_COLOR))
        if not self._tasks:
            title = "All clear! No missions \U0001F578"
        else:
            title = self._tasks_title or "Your missions, boss!"
        painter.drawText(QRectF(x, y, inner_w, TITLE_HEIGHT),
                         int(Qt.AlignmentFlag.AlignVCenter), title)
        y += TITLE_HEIGHT

        row_font = QFont("Sans", 10)
        painter.setFont(row_font)
        metrics = QFontMetrics(row_font)
        for title, priority in self._tasks[:TASKS_MAX_ROWS]:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(PRIORITY_COLORS.get(priority, ACCENT_COLOR)))
            painter.drawEllipse(QRectF(x + 2, y + ROW_HEIGHT / 2 - 4, 8, 8))
            painter.setPen(QPen(TEXT_COLOR))
            text = metrics.elidedText(title, Qt.TextElideMode.ElideRight, int(inner_w - 18))
            painter.drawText(QRectF(x + 18, y, inner_w - 18, ROW_HEIGHT),
                             int(Qt.AlignmentFlag.AlignVCenter), text)
            y += ROW_HEIGHT

        extra = len(self._tasks) - TASKS_MAX_ROWS
        if extra > 0:
            painter.setPen(QPen(MUTED_TEXT_COLOR))
            painter.drawText(QRectF(x + 18, y, inner_w - 18, ROW_HEIGHT),
                             int(Qt.AlignmentFlag.AlignVCenter), f"+{extra} more")

        if self._tasks:
            link_font = QFont("Sans", 10)
            link_font.setBold(True)
            painter.setFont(link_font)
            painter.setPen(QPen(LINK_COLOR))
            painter.drawText(self._footer_rect(),
                             int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                             "Open mission list \u2192")

    # -------------------------------------------------------------------------
    # Animation event handlers
    # -------------------------------------------------------------------------

    def _on_exit_animation_finished(self) -> None:
        # The fade animation is shared with the entrance – only hide on exit
        if not self._animating_out:
            return
        self.hide()
        self._animating_out = False
