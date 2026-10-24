"""Modern, dark-themed task panel that floats beside the Spider-Man companion.

Features
--------
- Header: "Your Missions" with stats toggle and close button.
- Pending task count display.
- Quick task creation with natural language ("call mom tomorrow 5pm !high")
  and a live preview of the parsed due date / priority.
- Task list with checkboxes, priority dots and due-date hints (overdue rows
  glow red, due within 2 hours amber).
- Double-click a row to edit it; right-click for Edit / Focus / Snooze / Delete.
- Stats strip: streak, done today / this week, focus minutes, 7-day bars.
- Ticking a task completes it: it's struck through for a moment and then
  removed (the app records it for stats and offers Undo).
- Collapsible details for a selected task.
- Dark theme with red/blue accents inspired by the character.
- Scrollable when there are many tasks.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from PySide6.QtCore import (
    Qt,
    QRect,
    QSize,
    QModelIndex,
    QTimer,
    QPoint,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QApplication,
    QAbstractItemView,
    QSizePolicy,
    QFrame,
    QMenu,
)

from hanging_reminder.tasks.nlp import describe_deadline, parse_task_text
from hanging_reminder.tasks.models import Task
from hanging_reminder.tasks.stats import summary_from_repository
from hanging_reminder.ui.quick_add import preview_html
from hanging_reminder.ui.stats_view import StatsView


# ---------------------------------------------------------------------------
# Colours – dark theme with red/blue Spider‑Man accents
# ---------------------------------------------------------------------------

PANEL_BG = QColor(42, 42, 42)          # charcoal dark
PANEL_ACcent = QColor(220, 50, 50)     # red accent
PANEL_BLUE = QColor(50, 100, 200)      # blue accent
PANEL_TEXT = QColor(220, 220, 220)     # light text
PANEL_DISABLED = QColor(100, 100, 100) # muted
PANEL_ORANGE = QColor(230, 130, 30)    # priority "high"
PANEL_GREEN = QColor(30, 180, 80)      # priority "low" / completed

ROW_HEIGHT = 32
PANEL_WIDTH = 280
PANEL_RADIUS = 14
STRIPE_HEIGHT = 5
MAX_VISIBLE_ROWS = 8
COMPLETE_DELAY_MS = 600  # strike-through shown before a ticked task disappears
DUE_SOON = timedelta(hours=2)
OVERDUE_RED = QColor(255, 95, 95)
OVERDUE_GLOW = "rgba(220, 50, 50, 45)"
SNOOZE_CHOICES = (("10 minutes", timedelta(minutes=10)), ("1 hour", timedelta(hours=1)))


# ---------------------------------------------------------------------------
# Task model wrapper for the QStandardItem model
# ---------------------------------------------------------------------------

class _TaskModelItem(QWidget):
    """A single task row: checkbox, priority dot, title and due-date hint."""

    def __init__(self, task: "tasks.models.Task", on_toggle=None, parent=None) -> None:
        super().__init__(parent)
        self.task = task
        self._on_toggle = on_toggle
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(8)

        # Checkbox
        self._check = QCheckBox()
        self._check.setChecked(task.completed)
        self._check.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check.toggled.connect(self._on_checkbox_toggled)
        layout.addWidget(self._check)

        # Priority dot
        colour = {
            "high": PANEL_ORANGE,
            "normal": PANEL_ACcent,
            "low": PANEL_GREEN,
        }.get(task.priority or "normal", PANEL_ACcent)
        dot = QLabel("\u25CF")
        dot.setStyleSheet(f"color: {colour.name()}; font-size: 10px;")
        dot.setToolTip(f"{task.display_priority} priority")
        layout.addWidget(dot)

        # Title (struck through once completed)
        self._title = QLabel(task.title)
        self._title.setToolTip(task.title)
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._apply_title_style(task.completed)
        layout.addWidget(self._title, 1)

        # Due date hint – red + glow when overdue, amber when due soon
        if task.deadline:
            now = datetime.now()
            due = QLabel(describe_deadline(task.deadline, now))
            if task.is_overdue:
                due_colour = OVERDUE_RED
                self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                self.setStyleSheet(f"_TaskModelItem {{ background: {OVERDUE_GLOW};"
                                   " border-radius: 6px; }")
            elif not task.completed and task.deadline - now <= DUE_SOON:
                due_colour = PANEL_ORANGE
            else:
                due_colour = PANEL_DISABLED
            due.setStyleSheet(f"color: {due_colour.name()}; font-size: 10px;")
            due.setToolTip(f"Due: {task.deadline.strftime('%a %d %b %Y, %H:%M')}")
            layout.addWidget(due)
        if task.is_snoozed():
            snooze = QLabel("\U0001F4A4")
            snooze.setToolTip(f"Snoozed until {task.snoozed_until.strftime('%H:%M')}")
            layout.addWidget(snooze)

        self.setFixedHeight(ROW_HEIGHT)

    def _apply_title_style(self, completed: bool) -> None:
        colour = PANEL_DISABLED if completed else PANEL_TEXT
        strike = "text-decoration: line-through;" if completed else ""
        self._title.setStyleSheet(f"color: {colour.name()}; font-size: 12px; {strike}")

    def _on_checkbox_toggled(self, checked: bool) -> None:
        """Handle checkbox toggle – sync task completion."""
        self.task.completed = checked
        self._apply_title_style(checked)
        if self._on_toggle is not None:
            self._on_toggle(self.task.id, checked)


def tomorrow_morning() -> datetime:
    return (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Task panel widget
# ---------------------------------------------------------------------------

class TaskPanel(QWidget):
    """Floating task panel for the Spider-Man Hanging Reminder."""

    #: Emitted when a task checkbox is toggled: (task_id, completed)
    task_toggled = Signal(int, bool)
    #: Emitted when a task is double-clicked (enter edit mode): task_id
    task_double_clicked = Signal(int)
    #: Emitted when the user requests to close the panel
    panel_closed = Signal()
    #: Emitted when the user picks "Focus on this" for a task: task_id
    focus_requested = Signal(int)
    #: Emitted after tasks were added/edited/deleted/snoozed
    tasks_changed = Signal()

    def __init__(self, repository, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.FramelessWindowHint)

        # Appearance
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # macOS hides an inactive app's Tool windows; Spidey is never the active app
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        self._repository = repository
        self._task_items: List[QListWidgetItem] = []

        # --- UI Layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12 + STRIPE_HEIGHT, 12, 12)
        layout.setSpacing(8)

        # ---- Header ----
        header = QHBoxLayout()
        self._title_label = QLabel("Your Missions")
        self._title_label.setStyleSheet(
            f"font-weight: bold; font-size: 13px; color: {PANEL_TEXT.name()};"
        )
        self._pending_label = QLabel("0 pending")
        self._pending_label.setStyleSheet(
            f"color: {PANEL_ACcent.name()}; font-size: 11px;"
        )
        self._close_btn = QPushButton("×")
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {PANEL_TEXT.name()};
                border: none;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {PANEL_ORANGE.name()};
            }}
        """
        )
        self._close_btn.clicked.connect(self._on_close)

        self._stats_btn = QPushButton("\U0001F4CA")
        self._stats_btn.setCheckable(True)
        self._stats_btn.setFixedSize(24, 20)
        self._stats_btn.setToolTip("Show stats")
        self._stats_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 13px; }"
            "QPushButton:checked { background: rgba(255,255,255,30); border-radius: 4px; }"
        )
        self._stats_btn.toggled.connect(self._toggle_stats)

        header.addWidget(self._title_label)
        header.addStretch()
        header.addWidget(self._pending_label)
        header.addWidget(self._stats_btn)
        header.addWidget(self._close_btn)
        layout.addLayout(header)

        # ---- Task list ----
        self._task_list = QListWidget()
        self._task_list.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self._task_list.setUniformItemSizes(False)
        self._task_list.setMovement(QListWidget.Snap)
        self._task_list.itemChanged.connect(self._on_item_changed)
        self._task_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._task_list.setStyleSheet(
            f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                border-radius: 6px;
            }}
            QListWidget::item:hover, QListWidget::item:selected {{
                background: rgba(255, 255, 255, 18);
            }}
        """
        )
        self._empty_label = QLabel("No missions here \U0001F578")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {PANEL_DISABLED.name()}; font-size: 12px;")
        layout.addWidget(self._empty_label)
        layout.addWidget(self._task_list, 1)  # stretch factor
        self._task_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._task_list.customContextMenuRequested.connect(self._on_context_menu)

        # ---- Stats (hidden until the 📊 toggle) ----
        self._stats_view = StatsView()
        self._stats_view.setVisible(False)
        layout.addWidget(self._stats_view)

        # ---- Quick task creation ----
        create_layout = QHBoxLayout()
        self._task_input = QLineEdit()
        self._task_input.setPlaceholderText("New task… e.g. Pay rent fri 6pm !high")
        self._task_input.setMaximumHeight(30)
        self._task_input.setStyleSheet(
            f"""
            QLineEdit {{
                background: rgba(255, 255, 255, 14);
                color: {PANEL_TEXT.name()};
                border: 1px solid {PANEL_DISABLED.name()};
                border-radius: 4px;
                padding: 4px;
                font-size: 12px;
            }}
        """
        )
        self._task_input.returnPressed.connect(self._on_add_task)

        self._add_btn = QPushButton("Add")
        self._add_btn.setFixedHeight(30)
        self._add_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {PANEL_ACcent.name()};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 0 8px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background: {PANEL_ORANGE.name()};
            }}
        """
        )
        self._add_btn.clicked.connect(self._on_add_task)

        create_layout.addWidget(self._task_input)
        create_layout.addWidget(self._add_btn)
        layout.addLayout(create_layout)

        self._input_preview = QLabel()
        self._input_preview.setTextFormat(Qt.TextFormat.RichText)
        self._input_preview.setStyleSheet(f"color: {PANEL_DISABLED.name()}; font-size: 10px;")
        self._input_preview.setVisible(False)
        layout.addWidget(self._input_preview)
        self._task_input.textChanged.connect(self._on_input_changed)

        # Initialise the task list from the repository
        self._refresh_list()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def _refresh_list(self) -> None:
        """Reload the open tasks from the repository."""
        self._task_list.clear()
        self._task_items.clear()

        tasks = self._repository.get_pending()
        for task in tasks:
            item = QListWidgetItem(self._task_list)
            model_item = _TaskModelItem(task, on_toggle=self._on_task_checked)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self._task_list.setItemWidget(item, model_item)
            self._task_items.append(item)

        self._task_list.setVisible(bool(tasks))
        self._empty_label.setVisible(not tasks)

        # Update pending count display
        count = len(tasks)
        self._pending_label.setText(f"{count} pending")
        self._resize_to_content()

    # ---- Add task ----

    def _on_add_task(self) -> None:
        text = self._task_input.text().strip()
        if not text:
            return

        parsed = parse_task_text(text)
        self.add_task(parsed.title, parsed.deadline, parsed.priority)
        self._task_input.clear()

    def add_task(self, title: str, deadline: Optional[datetime] = None,
                 priority: str = "normal") -> int:
        """Save a new task (also used by the quick-add box)."""
        task = Task(title=title, priority=priority, deadline=deadline)
        task_id = self._repository.save(task)
        self._after_change()
        return task_id

    def _on_input_changed(self, text: str) -> None:
        self._input_preview.setVisible(bool(text.strip()))
        self._input_preview.setText(preview_html(text))
        self._resize_to_content()

    def _after_change(self) -> None:
        self._refresh_list()
        self.tasks_changed.emit()

    # ---- Item interactions ----

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """List items carry no check state – rows report toggles directly."""

    def _on_task_checked(self, task_id: int, completed: bool) -> None:
        """A row was ticked – after a short strike-through, hand it to the app.

        The app completes it (removing it and offering Undo) and refreshes
        this list.  Unticking within that moment cancels.
        """
        if not completed:
            return
        QTimer.singleShot(COMPLETE_DELAY_MS, lambda: self._emit_if_still_ticked(task_id))

    def _emit_if_still_ticked(self, task_id: int) -> None:
        for item in self._task_items:
            row = self._task_list.itemWidget(item)
            if row is not None and row.task.id == task_id and row.task.completed:
                self.task_toggled.emit(task_id, True)
                return

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Double-click a row – open the editor."""
        model_item = self._task_list.itemWidget(item)
        if model_item is not None and hasattr(model_item, "task"):
            self.task_double_clicked.emit(model_item.task.id)
            self.edit_task(model_item.task.id)

    def edit_task(self, task_id: int) -> None:
        from hanging_reminder.ui.task_editor import TaskEditor

        task = self._repository.get(task_id)
        if task is None:
            return
        editor = TaskEditor(task, parent=self)
        editor.saved.connect(lambda t: (self._repository.update(t), self._after_change()))
        editor.deleted.connect(lambda tid: (self._repository.delete(tid), self._after_change()))
        editor.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        editor.show()
        editor.raise_()
        editor.activateWindow()

    def snooze_task(self, task_id: int, until: datetime) -> None:
        self._repository.snooze(task_id, until)
        self._after_change()

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._task_list.itemAt(pos)
        model_item = self._task_list.itemWidget(item) if item is not None else None
        if model_item is None:
            return
        task = model_item.task
        menu = QMenu(self)
        menu.addAction("Mark done \u2713", lambda: self.task_toggled.emit(task.id, True))
        menu.addAction("Edit…", lambda: self.edit_task(task.id))
        if not task.completed:
            menu.addAction("Focus on this", lambda: self.focus_requested.emit(task.id))
            snooze = menu.addMenu("Snooze")
            for label, delta in SNOOZE_CHOICES:
                snooze.addAction(label, lambda d=delta: self.snooze_task(
                    task.id, datetime.now() + d))
            snooze.addAction("Tomorrow 9:00", lambda: self.snooze_task(
                task.id, tomorrow_morning()))
        menu.addSeparator()
        menu.addAction("Delete", lambda: (self._repository.delete(task.id), self._after_change()))
        menu.exec(self._task_list.viewport().mapToGlobal(pos))

    def _toggle_stats(self, shown: bool) -> None:
        if shown:
            self._stats_view.set_summary(summary_from_repository(self._repository))
        self._stats_view.setVisible(shown)
        self._resize_to_content()

    # ---- Close ----

    def _on_close(self) -> None:
        self.panel_closed.emit()
        self.close()

    # ---- Painting – dark rounded card matching the speech bubble ----

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRect(0, 0, self.width(), self.height())

        path = QPainterPath()
        path.addRoundedRect(rect.adjusted(0, 0, -1, -1), PANEL_RADIUS, PANEL_RADIUS)
        painter.fillPath(path, QBrush(QColor(30, 34, 44, 245)))
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawPath(path)

        painter.setClipPath(path)
        painter.fillRect(QRect(0, 0, self.width(), STRIPE_HEIGHT), PANEL_ACcent)
        painter.end()

    def _resize_to_content(self) -> None:
        rows = max(1, min(len(self._task_items), MAX_VISIBLE_ROWS))
        list_h = rows * (ROW_HEIGHT + 2) + 4
        self._task_list.setFixedHeight(list_h)
        if self._stats_btn.isChecked():
            self._stats_view.set_summary(summary_from_repository(self._repository))
        self.layout().activate()
        height = self.layout().sizeHint().height()
        if self.isVisible():
            geo = self.geometry()
            self.setGeometry(geo.x(), geo.y(), PANEL_WIDTH, height)
        else:
            self.resize(PANEL_WIDTH, height)

    # ---- Positioning ----

    def update_anchor(self, char_screen_pos: QPoint) -> None:
        """Position the task panel relative to the character.

        Puts the panel to the right of the character, with vertical
        centering.  Clamps to screen edges.
        """
        if self.parent() is None:
            return

        cx, cy = char_screen_pos.x(), char_screen_pos.y()

        # Screen geometry
        screen = QApplication.screenAt(QPoint(cx, cy))
        if screen is None:
            screen = QApplication.primaryScreen()
        geom = screen.availableGeometry()

        self._resize_to_content()
        panel_w, panel_h = self.width(), self.height()

        # Position: right of character, vertically centered
        x = cx + 60
        y = cy - panel_h / 2

        # Clamp to screen edges – prefer right side, flip to the left
        if x + panel_w > geom.right():
            x = cx - 60 - panel_w
        if x + panel_w > geom.right():
            x = geom.right() - panel_w - 10
        if x < geom.left():
            x = geom.left() + 10

        if y < geom.top():
            y = geom.top() + 10
        if y + panel_h > geom.bottom():
            y = geom.bottom() - panel_h - 10

        self.setGeometry(int(x), int(y), int(panel_w), int(panel_h))

    def load_tasks(self) -> None:
        """Reload the task list from the repository (called on startup)."""
        self._refresh_list()