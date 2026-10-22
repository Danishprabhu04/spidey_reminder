"""Main application controller for Spider-Man Hanging Reminder.

Wires together all components:
- Configuration
- Task repository (SQLite persistence)
- Elastic web physics (owned by the companion window)
- Transparent companion window
- Task panel
- Speech bubble
- Power-event integration
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QLockFile, QTimer, QPoint, Qt
from PySide6.QtGui import QIcon

from hanging_reminder.config import AppConfig
from hanging_reminder.tasks.repository import TaskRepository
from hanging_reminder.ui.companion_window import CompanionWindow
from hanging_reminder.ui.task_panel import TaskPanel
from hanging_reminder.ui.speech_bubble import SpeechBubble
from hanging_reminder.ui.tray_icon import SpideyTrayIcon, ensure_icon_file
from hanging_reminder.system.power_manager import PowerManager
from hanging_reminder.logging_config import logger


# ---------------------------------------------------------------------------
# Application controller
# ---------------------------------------------------------------------------

class HangingReminderApp:
    """Root application controller – creates and manages all UI and backend objects."""

    def __init__(self) -> None:
        # ------------------------------------------------------------------
        # 1. Load configuration
        # ------------------------------------------------------------------
        self.config = AppConfig.load()
        logger.info("Configuration loaded")

        # ------------------------------------------------------------------
        # 2. Initialise backend: task repository
        # ------------------------------------------------------------------
        self.repository = TaskRepository(db_path=self.config.db_path)
        logger.info("Backend initialized – task repository")

        # ------------------------------------------------------------------
        # 3. Create the Qt application (must be before any UI)
        # ------------------------------------------------------------------
        if QApplication.instance() is None:
            self._qt_app = QApplication(sys.argv)
        else:
            self._qt_app = QApplication.instance()

        # High-DPI scaling is always on in Qt 6.
        # Closing panels/bubbles must not quit – Spidey lives in the tray too
        self._qt_app.setQuitOnLastWindowClosed(False)

        # ------------------------------------------------------------------
        # 4. Create the companion window (frameless, transparent)
        # ------------------------------------------------------------------
        self.window = CompanionWindow(config=self.config)
        logger.info(f"Companion window created at position ({self.window.x()}, {self.window.y()})")

        # ------------------------------------------------------------------
        # 5. Create the task panel (linked to the repository)
        # ------------------------------------------------------------------
        self.task_panel = TaskPanel(repository=self.repository, parent=self.window)
        logger.info("Task panel created")

        # ------------------------------------------------------------------
        # 6. Position the task panel relative to the character
        # ------------------------------------------------------------------
        # Initial positioning – will be updated on show
        self.task_panel.update_anchor(
            self.window.head_global_pos()
        )

        # ------------------------------------------------------------------
        # 7. Create the speech bubble (linked to the character)
        # ------------------------------------------------------------------
        self.speech_bubble = SpeechBubble(parent=self.window)
        logger.info("Speech bubble created")

        # ------------------------------------------------------------------
        # 8. Set up power-event integration (systemd-logind)
        # ------------------------------------------------------------------
        self.power_manager = PowerManager(config=self.config, parent=self.window)
        # Before sleep/shutdown Spidey lists pending tasks (inhibitor held at init)
        self.power_manager.reminder_requested.connect(self._on_power_reminder)
        self._power_reminder_active: bool = False

        # ------------------------------------------------------------------
        # 9. Wire up UI event handlers
        # ------------------------------------------------------------------

        # Task panel – task toggled: update character dialogue
        self.task_panel.task_toggled.connect(self._on_task_toggled)

        # Task panel – panel closed: ensure cleanup
        self.task_panel.panel_closed.connect(self._on_panel_closed)

        # Tap on Spidey – show pending tasks in a speech bubble
        self.window.tasks_requested.connect(self._show_tasks_bubble)
        self.window.character_moved.connect(self.speech_bubble.update_anchor)
        self.speech_bubble.open_panel_requested.connect(self._toggle_task_panel)
        self.speech_bubble.dismissed.connect(self._on_bubble_dismissed)

        # --------------------------------------------------------------
        # 10a. Taskbar (system tray) icon + Spidey show/hide toggle
        # --------------------------------------------------------------
        icon_path = ensure_icon_file()
        self.tray_icon = SpideyTrayIcon(
            icon_path,
            toggle_handler=self._set_spidey_visible,
            todo_handler=self._toggle_task_panel,
            quit_handler=self._shutdown,
            parent=self._qt_app,
        )
        if self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.show()
            logger.info("Taskbar tray icon visible (toggle: left-click)")
        else:
            logger.warning("System tray not available – toggle via menu only")
        self._qt_app.setWindowIcon(QIcon(icon_path))

        # --------------------------------------------------------------
        # 10b. Task reminder timer – periodically nag about pending tasks
        # --------------------------------------------------------------
        interval_s = max(30, int(getattr(self.config, "reminder_interval", 600)))
        self._reminder_timer = QTimer(self._qt_app, interval=interval_s * 1000,
                                      timeout=self._on_reminder_tick)
        self._reminder_timer.start()
        # First gentle nudge shortly after startup
        QTimer.singleShot(20_000, self._on_reminder_tick)

        # ------------------------------------------------------------------
        # 10. Show the companion window (it drives its own physics + repaint)
        # ------------------------------------------------------------------
        self.window.show()

        logger.info("HangingReminderApp fully initialised – running")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_task_toggled(self, task_id: int, completed: bool) -> None:
        """Handle task toggle – update character dialogue state."""
        # Could affect what the character says via speech bubble
        logger.debug(f"Task {task_id} {'completed' if completed else 'opened'}")

    # ------------------------------------------------------------------
    # Spidey visibility toggle + shutdown (taskbar icon)
    # ------------------------------------------------------------------

    def _set_spidey_visible(self, visible: bool) -> None:
        """Taskbar toggle: show/hide Spidey on all desktops and workspaces."""
        if visible:
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()
            logger.info("Spidey now VISIBLE (toggled on via taskbar)")
        else:
            for overlay in (self.task_panel, self.speech_bubble):
                if overlay.isVisible():
                    overlay.hide()
            self.window.hide()
            logger.info("Spidey now HIDDEN (toggled off via taskbar)")
        if hasattr(self, "tray_icon") and self.tray_icon is not None:
            self.tray_icon.set_visible_state(visible)

    def _shutdown(self) -> None:
        """Quit the application cleanly from the tray menu."""
        logger.info("Shutdown requested via taskbar menu")
        self._qt_app.quit()  # main() runs close() once the loop exits

    def _on_panel_closed(self) -> None:
        """Handle task panel closing – cleanup."""
        logger.info("Task panel closed")
        # Acceptable – the window remains active

    # ------------------------------------------------------------------
    # Todo button + reminders
    # ------------------------------------------------------------------

    def _toggle_task_panel(self) -> None:
        """Show/hide the mission list when the 📝 button is clicked."""
        if self.task_panel.isVisible():
            self.task_panel.hide()
            return
        self.task_panel.load_tasks()
        self.task_panel.update_anchor(
            self.window.head_global_pos()
        )
        self.task_panel.show()
        self.task_panel.raise_()
        logger.info("Task panel toggled open via todo button")

    def _show_tasks_bubble(self, char_screen_pos: QPoint) -> None:
        """Spidey was tapped – list the pending missions beside him."""
        try:
            pending = self.repository.get_pending()
        except Exception:
            logger.exception("Could not load pending tasks")
            return
        self.speech_bubble.update_anchor(char_screen_pos)
        self.speech_bubble.show_tasks(pending, duration_ms=self.config.speech_bubble_duration * 2)
        logger.info("Task bubble shown: %d pending", len(pending))

    def _on_reminder_tick(self) -> None:
        """Periodically remind the user about pending tasks via Spidey."""
        if not self.window.isVisible():
            return  # Spidey toggled off – stay silent
        try:
            pending = self.repository.count_pending()
        except Exception:
            return
        if pending <= 0:
            return

        noun = "mission" if pending == 1 else "missions"
        self.speech_bubble.update_anchor(
            self.window.head_global_pos()
        )
        self.speech_bubble.show_message(f"\U0001F578 {pending} {noun} pending, boss! Tap me to see them.")
        QTimer.singleShot(self.config.speech_bubble_duration, self.speech_bubble.hide_message)
        logger.info("Reminder shown: %d pending %s", pending, noun)

    # ------------------------------------------------------------------
    # Power-event handlers – connected to PowerManager signals
    # ------------------------------------------------------------------

    def _on_power_reminder(self, operation: str, timeout_ms: int) -> None:
        """Sleep/shutdown is coming – show pending tasks while it's held back."""
        try:
            pending = self.repository.get_pending()
        except Exception:
            logger.exception("Could not load pending tasks for the power reminder")
            pending = []
        if not pending:
            self.power_manager.user_continued()  # nothing to remind about
            return

        verb = "sleep" if operation == "sleep" else "shut down"
        logger.info("Power reminder for %s: %d pending (%d ms)", operation, len(pending), timeout_ms)
        self._power_reminder_active = timeout_ms > 0
        self.speech_bubble.update_anchor(self.window.head_global_pos())
        self.speech_bubble.show_tasks(
            pending,
            duration_ms=timeout_ms or self.config.speech_bubble_duration,
            title=f"Wait! Before you {verb}\u2026",
        )

    def _on_bubble_dismissed(self) -> None:
        """Tapping the bubble during a power reminder lets the system proceed."""
        if self._power_reminder_active:
            self._power_reminder_active = False
            self.power_manager.user_continued()

    # ------------------------------------------------------------------
    # Application run loop
    # ------------------------------------------------------------------

    def run(self) -> int:
        """Run the Qt application main loop."""
        return self._qt_app.exec()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Clean up resources on application exit."""
        logger.info("Shutting down HangingReminderApp")
        self.tray_icon.shutdown()
        self.repository.close()
        self.power_manager.release_inhibitor()
        # The companion window will be deleted via WA_DeleteOnClose


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Entry point for the Spider-Man Hanging Reminder application."""
    # Single instance – autostart, the menu and a manual launch may overlap
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or str(Path.home() / ".local" / "share" / "spidey-sense")
    lock = QLockFile(str(Path(runtime_dir) / "spidey-sense.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        logger.info("Spidey is already running – not starting a second one")
        return 0

    # Native Wayland forbids clients from positioning themselves, staying on
    # top and shaping their input region – run through XWayland instead.
    if (
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        and "QT_QPA_PLATFORM" not in os.environ
    ):
        import ctypes.util
        if ctypes.util.find_library("xcb-cursor"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"
        else:
            logger.warning(
                "libxcb-cursor0 is missing – staying on native Wayland, where Spidey "
                "can't stay on top or be dragged freely. Fix: sudo apt install libxcb-cursor0"
            )
    app = HangingReminderApp()
    try:
        return app.run()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        return 0
    finally:
        app.close()
        lock.unlock()


if __name__ == "__main__":
    sys.exit(main())