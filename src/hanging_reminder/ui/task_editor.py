"""Edit one task: title, priority, due date/time and notes (or delete it)."""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hanging_reminder.tasks.models import Task
from hanging_reminder.ui.settings_dialog import STYLE

EXTRA_STYLE = """
QPlainTextEdit, QDateTimeEdit {
    background: #2a2f3a; color: #e6e6e6; border: 1px solid #4a4f5b;
    border-radius: 4px; padding: 3px 6px;
}
QPushButton#prio { background: #3a3f4b; font-weight: normal; padding: 5px 12px; }
QPushButton#prio:checked { background: #dc3232; font-weight: bold; }
QPushButton#danger { background: transparent; color: #ff7a7a; }
QPushButton#danger:hover { background: #4a2a2e; }
"""


class TaskEditor(QDialog):
    saved = Signal(object)     # Task
    deleted = Signal(int)      # task id

    def __init__(self, task: Task, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task = task
        self.setWindowTitle("Edit mission")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(STYLE + EXTRA_STYLE)
        self.setMinimumWidth(380)

        self.title_edit = QLineEdit(task.title)

        self._prio_group = QButtonGroup(self)
        prio_row = QHBoxLayout()
        for name in ("low", "normal", "high"):
            button = QPushButton(name.title())
            button.setObjectName("prio")
            button.setCheckable(True)
            button.setChecked(task.priority == name)
            self._prio_group.addButton(button)
            button.setProperty("priority", name)
            prio_row.addWidget(button)
        prio_row.addStretch()

        self.due_check = QCheckBox("Due")
        self.due_edit = QDateTimeEdit()
        self.due_edit.setCalendarPopup(True)
        self.due_edit.setDisplayFormat("ddd d MMM yyyy  HH:mm")
        default_due = task.deadline or (datetime.now() + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0)
        self.due_edit.setDateTime(QDateTime(default_due))
        self.due_check.setChecked(task.deadline is not None)
        self.due_edit.setEnabled(task.deadline is not None)
        self.due_check.toggled.connect(self.due_edit.setEnabled)
        due_row = QHBoxLayout()
        due_row.addWidget(self.due_check)
        due_row.addWidget(self.due_edit, 1)

        self.notes_edit = QPlainTextEdit(task.description)
        self.notes_edit.setPlaceholderText("Notes…")
        self.notes_edit.setFixedHeight(80)

        form = QFormLayout()
        form.addRow("Title", self.title_edit)
        form.addRow("Priority", prio_row)
        form.addRow("", due_row)
        form.addRow("Notes", self.notes_edit)

        delete = QPushButton("Delete")
        delete.setObjectName("danger")
        delete.clicked.connect(self._on_delete)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self._on_save)
        buttons = QHBoxLayout()
        buttons.addWidget(delete)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)

    def edited_task(self) -> Task:
        task = self._task
        task.title = self.title_edit.text().strip() or task.title
        checked = self._prio_group.checkedButton()
        task.priority = checked.property("priority") if checked else task.priority
        task.deadline = (
            self.due_edit.dateTime().toPython().replace(second=0, microsecond=0)
            if self.due_check.isChecked() else None
        )
        task.description = self.notes_edit.toPlainText().strip()
        return task

    def _on_save(self) -> None:
        self.saved.emit(self.edited_task())
        self.accept()

    def _on_delete(self) -> None:
        self.deleted.emit(self._task.id)
        self.accept()
