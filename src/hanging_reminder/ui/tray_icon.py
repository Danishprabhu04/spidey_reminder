"""System-tray (taskbar) icon for the Spider-Man companion.

Provides:
- A generated Spidey icon (rendered from the same painter code as the
  companion window) so the app shows up in the GNOME/Ubuntu top bar.
- Left-click toggles Spidey visibility (hide/show on every desktop).
- A context menu with a Show/Hide toggle, mission list and Quit.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from hanging_reminder.logging_config import logger

ICON_PATH = Path.home() / ".local" / "share" / "spidey-sense" / "spidey_icon.png"


def build_spidey_icon_pixmap(size: int = 256) -> QPixmap:
    """Render the chibi Spidey sprite into a square pixmap icon."""
    from hanging_reminder.config import AppConfig
    from hanging_reminder.ui.companion_window import CompanionWindow

    dummy = CompanionWindow.__new__(CompanionWindow)
    dummy.config = AppConfig()
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    CompanionWindow._render_character(dummy, pixmap)
    return pixmap


def ensure_icon_file(path: Path | None = None) -> str:
    """Render Spidey to PNG once so it can be reused by tray/desktop entry."""
    path = path or ICON_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        pixmap = build_spidey_icon_pixmap(256)
        pixmap.save(str(path))
        logger.info("Spidey icon rendered to %s", path)
    if not path.exists():
        logger.error("Failed to generate Spidey icon at %s", path)
    return str(path)


class SpideyTrayIcon(QSystemTrayIcon):
    """Taskbar icon with a Show/Hide toggle for the companion window."""

    def __init__(
        self,
        icon_path: str,
        toggle_handler=None,
        todo_handler=None,
        quit_handler=None,
        parent=None,
    ) -> None:
        super().__init__(QIcon(icon_path), parent)
        self.setToolTip("Spidey Reminder – click to hide / show Spidey")

        menu = QMenu()

        self._toggle_action = QAction("Hide Spidey", menu)
        self._toggle_action.setCheckable(True)
        self._toggle_action.setChecked(True)
        self._toggle_action.toggled.connect(self._on_menu_toggle)
        menu.addAction(self._toggle_action)

        if todo_handler is not None:
            todo_action = QAction("Mission list", menu)
            todo_action.triggered.connect(todo_handler)
            menu.addAction(todo_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        if quit_handler is not None:
            quit_action.triggered.connect(quit_handler)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self._toggle_cb = toggle_handler

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_activated(self, reason) -> None:
        """Left-click (Trigger) toggles visibility; context menu handles the rest."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_action.setChecked(not self._toggle_action.isChecked())

    def _on_menu_toggle(self, visible: bool) -> None:
        self._toggle_action.setText("Show Spidey" if not visible else "Hide Spidey")
        self.setToolTip(
            "Spidey Reminder – click to %s Spidey" % ("show" if not visible else "hide")
        )
        if self._toggle_cb is not None:
            self._toggle_cb(visible)

    def set_visible_state(self, visible: bool) -> None:
        """Sync the menu checkbox with the real window visibility."""
        if self._toggle_action.isChecked() != visible:
            self._toggle_action.setChecked(visible)
        self._toggle_action.setText("Show Spidey" if not visible else "Hide Spidey")

    def shutdown(self) -> None:
        """Cleanly remove the tray icon before the app exits."""
        try:
            self.hide()
            self.deleteLater()
        except Exception:
            pass
