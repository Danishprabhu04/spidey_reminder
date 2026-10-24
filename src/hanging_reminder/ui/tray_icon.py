"""System-tray (taskbar) icon for the Spider-Man companion.

Provides:
- A generated Spidey icon (rendered from the same painter code as the
  companion window) so the app shows up in the GNOME/Ubuntu top bar.
- Left-click toggles Spidey visibility (hide/show on every desktop).
- A context menu with a Show/Hide toggle, quick add, mission list,
  focus timer, web dashboard, do-not-disturb, settings and Quit.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from hanging_reminder import APP_NAME, paths
from hanging_reminder.logging_config import logger

ICON_PATH = paths.icon_path()


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
        quick_add_handler=None,
        settings_handler=None,
        dnd_handler=None,
        focus_handler=None,
        dashboard_handler=None,
        parent=None,
    ) -> None:
        super().__init__(QIcon(icon_path), parent)
        self._base_tooltip = f"{APP_NAME} – click to hide / show Spidey"
        self._status_lines: dict[str, str] = {}
        self.setToolTip(self._base_tooltip)

        menu = QMenu()
        self._menu = menu  # keep a reference – QSystemTrayIcon doesn't own it

        self._toggle_action = QAction("Hide Spidey", menu)
        self._toggle_action.setCheckable(True)
        self._toggle_action.setChecked(True)
        self._toggle_action.toggled.connect(self._on_menu_toggle)
        menu.addAction(self._toggle_action)

        if quick_add_handler is not None:
            quick_action = QAction("Quick add…", menu)
            quick_action.triggered.connect(quick_add_handler)
            menu.addAction(quick_action)

        if todo_handler is not None:
            todo_action = QAction("Mission list", menu)
            todo_action.triggered.connect(todo_handler)
            menu.addAction(todo_action)

        self._focus_action = None
        if focus_handler is not None:
            self._focus_action = QAction("Start focus session", menu)
            self._focus_action.triggered.connect(focus_handler)
            menu.addAction(self._focus_action)

        if dashboard_handler is not None:
            dashboard_action = QAction("Open web dashboard", menu)
            dashboard_action.triggered.connect(dashboard_handler)
            menu.addAction(dashboard_action)

        if dnd_handler is not None:
            dnd_menu = menu.addMenu("Do not disturb")
            for label, minutes in (("For 1 hour", 60), ("Until tomorrow", -1), ("Off", 0)):
                action = QAction(label, dnd_menu)
                action.triggered.connect(lambda _=False, m=minutes: dnd_handler(m))
                dnd_menu.addAction(action)

        menu.addSeparator()

        if settings_handler is not None:
            settings_action = QAction("Settings…", menu)
            settings_action.triggered.connect(settings_handler)
            menu.addAction(settings_action)

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
        self._base_tooltip = (
            f"{APP_NAME} – click to %s Spidey" % ("show" if not visible else "hide")
        )
        self._refresh_tooltip()
        if self._toggle_cb is not None:
            self._toggle_cb(visible)

    def set_visible_state(self, visible: bool) -> None:
        """Sync the menu checkbox with the real window visibility."""
        if self._toggle_action.isChecked() != visible:
            self._toggle_action.setChecked(visible)
        self._toggle_action.setText("Show Spidey" if not visible else "Hide Spidey")

    def set_status(self, key: str, text: str) -> None:
        """Add/replace (or clear with "") a status line in the tooltip."""
        if text:
            self._status_lines[key] = text
        else:
            self._status_lines.pop(key, None)
        self._refresh_tooltip()

    def set_focus_label(self, text: str) -> None:
        if self._focus_action is not None:
            self._focus_action.setText(text)

    def _refresh_tooltip(self) -> None:
        self.setToolTip("\n".join([self._base_tooltip, *self._status_lines.values()]))

    def shutdown(self) -> None:
        """Cleanly remove the tray icon before the app exits."""
        try:
            self.hide()
            self.deleteLater()
        except Exception:
            pass
