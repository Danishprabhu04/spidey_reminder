"""Main application controller for Spider-Man Hanging Reminder.

Wires together all components:
- Configuration
- Task repository (SQLite persistence)
- Physics engine (pendulum + spring)
- Transparent companion window
- Task panel
- Speech bubble
- Power-event integration
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QPoint, Qt
from PySide6.QtGui import QIcon

from hanging_reminder.config import AppConfig
from hanging_reminder.tasks.repository import TaskRepository
from hanging_reminder.physics import SimulationEngine, Spring, Pendulum
from hanging_reminder.ui.companion_window import CompanionWindow
from hanging_reminder.ui.task_panel import TaskPanel
from hanging_reminder.ui.speech_bubble import SpeechBubble
from hanging_reminder.ui.tray_icon import SpideyTrayIcon, ensure_icon_file
from hanging_reminder.system.power_manager import PowerManager, show_power_reminder
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
        # 2. Initialise backend: task repository, physics engines
        # ------------------------------------------------------------------
        self.repository = TaskRepository(db_path=self.config.db_path)
        self.simulation = SimulationEngine(dt=1.0 / 120)

        self._spring = Spring(
            rest_length=self.config.character_size * 0.6,
            stiffness=self.config.spring_stiffness,
            damping=self.config.damping,
        )
        self._pendulum = Pendulum(
            length=max(self.config.character_size * 0.05, 2.0),
            gravity=self.config.gravity,
            damping=self.config.damping,
            max_angle=self.config.max_angle,
        )

        self.simulation.add_entity(self._spring)
        self.simulation.add_entity(self._pendulum)

        logger.info("Backend initialized – repository + physics engines")

        # ------------------------------------------------------------------
        # 3. Create the Qt application (must be before any UI)
        # ------------------------------------------------------------------
        if QApplication.instance() is None:
            self._qt_app = QApplication(sys.argv)
        else:
            self._qt_app = QApplication.instance()

        # Ensure high-DPI scaling
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            self._qt_app.setAttribute(Qt.AA_EnableHighDpiScaling)
        if hasattr(Qt, "AA_UseHighDpiPixmaps"):
            self._qt_app.setAttribute(Qt.AA_UseHighDpiPixmaps)

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
            self.window.mapToGlobal(QPoint(self.window.width() / 2, self.window.height() / 2))
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
        # Connect power manager signals to app-level handlers
        self.power_manager.reminder_requested.connect(self._on_power_reminder)
        self.power_manager.cancel_requested.connect(self._on_power_cancel)
        self.power_manager.continue_requested.connect(self._on_power_continue)
        self.power_manager.timeout_requested.connect(self._on_power_timeout)

        # Attempt to acquire a logind inhibitor early (will be re-acquired
        # when a actual sleep/shutdown approach)
        # We do this once at startup; the actual inhibitor is re-acquired
        # when the logind signal fires.
        # Note: this early attempt may fail if systemd/logind isn't available;
        # that's OK – the signal handlers will re-attempt at the right time.
        _ = self.power_manager.attempt_inhibit("sleep")  # best-effort

        # ------------------------------------------------------------------
        # 9. Wire up UI event handlers
        # ------------------------------------------------------------------

        # Task panel – task toggled: update character dialogue
        self.task_panel.task_toggled.connect(self._on_task_toggled)

        # Task panel – panel closed: ensure cleanup
        self.task_panel.panel_closed.connect(self._on_panel_closed)

        # Companion window todo (📝) button – toggle the mission list
        self.window.todo_toggle_requested.connect(self._toggle_task_panel)

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
        # 10. Start the GUI timer – drives physics + repaint
        # ------------------------------------------------------------------
        # Qt's default timer resolution is ~15ms (~66 FPS).  We'll use
        # 16ms for ~60 FPS target.
        self._timer = QTimer(self._qt_app, interval=16, timeout=self._on_timer_tick)
        self._timer.start()
        logger.info("GUI timer started (16ms interval)")

        # ------------------------------------------------------------------
        # 11. Show the companion window
        # ------------------------------------------------------------------
        self.window.show()
        # Ensure the window is on the correct monitor
        self.window._reposition_to_monitor()

        logger.info("HangingReminderApp fully initialised – running")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_timer_tick(self) -> None:
        """Called 60 times per second – drive physics and repaint."""
        # Fixed timestep physics update (already handled by simulation engine,
        # but we also update the pendulum/spring state that the window uses)
        dt = 1.0 / 120
        self._pendulum.integrate(dt)
        self._spring.integrate(dt)

        # Smooth settling logic (already in companion window's _on_physics_tick)
        # The window handles its own physics tick; we just ensure consistency.

        # Force repaint – the companion window's paintEvent will render
        # the character, web, and update rotations based on physics state.
        self.window.update()

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
        self.close()

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
            self.window.mapToGlobal(QPoint(int(self.window.width() / 2), int(self.window.height() / 2)))
        )
        self.task_panel.show()
        self.task_panel.raise_()
        logger.info("Task panel toggled open via todo button")

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
            self.window.mapToGlobal(QPoint(int(self.window.width() / 2), int(self.window.height() / 2)))
        )
        self.speech_bubble.show_message(f"\U0001F578 {pending} {noun} pending, boss! Tap the \U0001F4DD to plan.")
        QTimer.singleShot(self.config.speech_bubble_duration, self.speech_bubble.hide_message)
        logger.info("Reminder shown: %d pending %s", pending, noun)

    # ------------------------------------------------------------------
    # Power-event handlers – connected to PowerManager signals
    # ------------------------------------------------------------------

    def _on_power_reminder(self, operation: str, timeout_ms: int) -> None:
        """User needs to respond to a power-event reminder.

        Show a dialog with "Cancel and stay" / "Continue anyway" options.
        The dialog should be modal but not block the GUI thread indefinitely.
        """
        logger.info(f"Power reminder for {operation} (timeout={timeout_ms}ms)")
        # The application should display a QDialog here with two buttons.
        # For now, we log and default to "continue" after the timeout.
        # In a full implementation, show a QMessageBox or custom dialog.

    def _on_power_cancel(self, operation: str) -> None:
        """User chose 'Cancel and stay' – prevent the power action."""
        logger.info(f"User cancelled {operation}; application should attempt to delay sleep/shutdown")
        # The application should use whatever mechanism it has to cancel
        # the pending operation.  On GNOME/Ubuntu this might involve
        # org.freedesktop.login1 inhibitor protocols or simply preventing
        # the window from closing.  We cannot guarantee this works in all cases.

    def _on_power_continue(self, operation: str) -> None:
        """User chose 'Continue anyway' – allow the power action."""
        logger.info(f"User continued past {operation}; releasing inhibitor")
        # Release the inhibitor so the power action can proceed.

    def _on_power_timeout(self, operation: str) -> None:
        """User didn't respond in time – auto-continue."""
        logger.warning(f"Power reminder timed out for {operation}; auto-continuing")
        # Release the inhibitor and allow the operation to proceed.

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
        self._timer.stop()
        self.repository.close()
        self.power_manager.release_inhibitor()
        # The companion window will be deleted via WA_DeleteOnClose


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Entry point for the Spider-Man Hanging Reminder application."""
    app = HangingReminderApp()
    try:
        return app.run()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        return 0
    finally:
        app.close()


if __name__ == "__main__":
    sys.exit(main())