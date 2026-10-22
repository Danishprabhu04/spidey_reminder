"""Modern, dark-themed task panel that floats beside the Spider-Man companion.

Features
--------
- Header: "Your Missions" with close button.
- Pending task count display.
- Quick task creation: type text and press Enter.
- Task list with checkboxes, priority tags, and due-date hints.
- Completion state updates the SQLite repository immediately.
- Filter buttons: "Pending", "Completed", "All".
- Clear completed action.
- Collapsible details for a selected task.
- Dark theme with red/blue accents inspired by the character.
- Scrollable when there are many tasks.
"""

from __future__ import annotations

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
)


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

        # Due date hint
        if task.deadline:
            due = QLabel(task.deadline.strftime("%b %d"))
            due_colour = PANEL_ORANGE if task.is_overdue else PANEL_DISABLED
            due.setStyleSheet(f"color: {due_colour.name()}; font-size: 10px;")
            due.setToolTip(f"Due: {task.deadline.strftime('%Y-%m-%d')}")
            layout.addWidget(due)

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

    def __init__(self, repository, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.FramelessWindowHint)

        # Appearance
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        self._repository = repository
        self._task_items: List[QListWidgetItem] = []
        self._filter: str = "pending"

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

        header.addWidget(self._title_label)
        header.addStretch()
        header.addWidget(self._pending_label)
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

        # ---- Filter buttons ----
        filter_layout = QHBoxLayout()
        self._btn_pending = QPushButton("Pending")
        self._btn_completed = QPushButton("Completed")
        self._btn_all = QPushButton("All")
        self._btn_clear = QPushButton("Clear completed")

        for btn in (self._btn_pending, self._btn_completed, self._btn_all, self._btn_clear):
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: {PANEL_ACcent.name()};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    background: {PANEL_ORANGE.name()};
                }}
                QPushButton:checked {{
                    background: {PANEL_BLUE.name()};
                }}
            """
            )
        self._btn_pending.setCheckable(True)
        self._btn_completed.setCheckable(True)
        self._btn_all.setCheckable(True)
        self._btn_pending.setChecked(True)  # start with pending filter

        self._btn_pending.clicked.connect(self._filter_pending)
        self._btn_completed.clicked.connect(self._filter_completed)
        self._btn_all.clicked.connect(self._filter_all)
        self._btn_clear.clicked.connect(self._clear_completed)

        filter_layout.addWidget(self._btn_pending)
        filter_layout.addWidget(self._btn_completed)
        filter_layout.addWidget(self._btn_all)
        filter_layout.addWidget(self._btn_clear)
        layout.addLayout(filter_layout)

        # ---- Quick task creation ----
        create_layout = QHBoxLayout()
        self._task_input = QLineEdit()
        self._task_input.setPlaceholderText("New task...")
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

        # Initialise the task list from the repository
        self._refresh_list()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def _refresh_list(self, filter_: str | None = None) -> None:
        """Refresh the task list from the repository, applying *filter_*.

        *filter_* is one of "pending", "completed", "all" (default: current).
        """
        if filter_ is not None:
            self._filter = filter_
        for btn, name in (
            (self._btn_pending, "pending"),
            (self._btn_completed, "completed"),
            (self._btn_all, "all"),
        ):
            btn.setChecked(self._filter == name)

        self._task_list.clear()
        self._task_items.clear()

        tasks = []
        if self._filter in ("pending", "all"):
            tasks += self._repository.get_pending()
        if self._filter in ("completed", "all"):
            tasks += self._repository.get_completed()

        for task in tasks:
            item = QListWidgetItem(self._task_list)
            model_item = _TaskModelItem(task, on_toggle=self._on_task_checked)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self._task_list.setItemWidget(item, model_item)
            self._task_items.append(item)

        self._task_list.setVisible(bool(tasks))
        self._empty_label.setVisible(not tasks)

        # Update pending count display
        count = self._repository.count_pending()
        self._pending_label.setText(f"{count} pending")
        self._resize_to_content()

    # ---- Filter methods ----

    def _filter_pending(self, checked: bool = False) -> None:
        self._refresh_list("pending")

    def _filter_completed(self, checked: bool = False) -> None:
        self._refresh_list("completed")

    def _filter_all(self, checked: bool = False) -> None:
        self._refresh_list("all")

    # ---- Add task ----

    def _on_add_task(self) -> None:
        text = self._task_input.text().strip()
        if not text:
            return

        from datetime import datetime
        from hanging_reminder.tasks.models import Task

        task = Task(
            title=text,
            priority="normal",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._repository.save(task)
        self._refresh_list()
        self._task_input.clear()

    # ---- Item interactions ----

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """List items carry no check state – rows report toggles directly."""

    def _on_task_checked(self, task_id: int, completed: bool) -> None:
        """A row's checkbox was toggled – persist it and notify listeners."""
        self._repository.toggle_complete(task_id)
        self.task_toggled.emit(task_id, completed)
        # Let the tick/strike-through show briefly before the row moves
        QTimer.singleShot(350, self._refresh_list)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click – enter edit mode (placeholder)."""
        row = self._task_list.row(item)
        model_item = self._task_list.itemWidget(item)
        if model_item is not None and hasattr(model_item, "task"):
            task_id = model_item.task.id
            self.task_double_clicked.emit(task_id)

    # ---- Clear completed ----

    def _clear_completed(self) -> None:
        """Remove all completed tasks from the repository."""
        deleted = self._repository.clear_completed()
        self._refresh_list()
        # Emit some signal if needed …

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
        # header + list + filters + input + margins/spacing
        height = 12 + STRIPE_HEIGHT + 24 + 8 + list_h + 8 + 26 + 8 + 30 + 12
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