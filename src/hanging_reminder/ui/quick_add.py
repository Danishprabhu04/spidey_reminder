"""Quick-add box that pops up beside Spidey.

Opened by double-tapping Spidey, the GNOME shortcut
(``hanging-reminder --quick-add``) or the tray menu.  The text is parsed
live (:func:`parse_task_text`) and a chip previews the due date and
priority.  Enter saves, Esc closes.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QVBoxLayout, QWidget

from hanging_reminder.tasks.nlp import ParsedTask, describe_deadline, parse_task_text

WIDTH = 330
RADIUS = 12
BG = QColor(30, 34, 44, 248)
ACCENT = QColor(220, 50, 50)
PRIORITY_COLORS = {"high": "#e6821e", "normal": "#dc3232", "low": "#1eb450"}


def preview_html(text: str) -> str:
    """Rich-text chip describing what *text* parses to (due date · priority)."""
    if not text.strip():
        return "Try: <i>tomorrow 5pm</i>, <i>in 2 hours</i>, <i>fri</i>, <i>!high</i>"
    parsed = parse_task_text(text, datetime.now())
    parts = []
    if parsed.deadline:
        parts.append(f"\U0001F4C5 {describe_deadline(parsed.deadline)}")
    colour = PRIORITY_COLORS.get(parsed.priority, "#dc3232")
    parts.append(f"<span style='color:{colour}'>●</span> {parsed.priority.title()}")
    return " &nbsp;·&nbsp; ".join(parts)


class QuickAddBox(QWidget):
    submitted = Signal(object)  # ParsedTask

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # macOS hides an inactive app's Tool windows; Spidey is never the active app
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("New mission… e.g. Call mom tomorrow 5pm !high")
        self._edit.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,16); color: #ececec;"
            " border: 1px solid #555b68; border-radius: 6px; padding: 6px 8px;"
            " font-size: 13px; }"
            "QLineEdit:focus { border-color: #dc3232; }"
        )
        self._edit.textChanged.connect(self._update_preview)
        self._edit.returnPressed.connect(self._submit)

        self._preview = QLabel()
        self._preview.setStyleSheet("color: #9aa0ab; font-size: 11px;")
        self._preview.setTextFormat(Qt.TextFormat.RichText)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 10)
        layout.setSpacing(6)
        layout.addWidget(self._edit)
        layout.addWidget(self._preview)
        self.setFixedWidth(WIDTH)
        self._update_preview("")

    # ------------------------------------------------------------------

    def open_at(self, char_screen_pos: QPoint) -> None:
        """Show beside Spidey's head and take keyboard focus."""
        self._edit.clear()
        self.adjustSize()
        screen = QApplication.screenAt(char_screen_pos) or QApplication.primaryScreen()
        geom = screen.availableGeometry()
        x = char_screen_pos.x() + 60
        if x + self.width() > geom.right():
            x = char_screen_pos.x() - 60 - self.width()
        y = char_screen_pos.y() - self.height() // 2
        x = max(geom.left() + 8, min(x, geom.right() - self.width() - 8))
        y = max(geom.top() + 8, min(y, geom.bottom() - self.height() - 8))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self._edit.setFocus(Qt.FocusReason.PopupFocusReason)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------

    def _update_preview(self, text: str) -> None:
        self._preview.setText(preview_html(text))

    def _submit(self) -> None:
        text = self._edit.text().strip()
        if not text:
            self.hide()
            return
        parsed: ParsedTask = parse_task_text(text, datetime.now())
        self.submitted.emit(parsed)
        self.hide()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
        painter.fillPath(path, QBrush(BG))
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawPath(path)
        painter.setClipPath(path)
        painter.fillRect(0, 0, self.width(), 4, ACCENT)
        painter.end()
