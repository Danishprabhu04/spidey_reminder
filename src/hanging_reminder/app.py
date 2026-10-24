"""Main application controller for Spider-Man Hanging Reminder.

Wires together all components:
- Configuration
- Task repository (SQLite persistence)
- Elastic web physics (owned by the companion window)
- Transparent companion window
- Task panel
- Speech bubble
- Power-event integration
- Sound effects, settings, do-not-disturb
- Local-socket IPC so ``hanging-reminder --quick-add`` reaches the running app
- Local web dashboard (http://127.0.0.1:47823) and the global quick-add shortcut
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QLockFile, QTimer, QPoint, Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtCore import QUrl

from hanging_reminder import APP_NAME, __version__, paths
from hanging_reminder.config import AppConfig
from hanging_reminder.dashboard.api import DashboardApi
from hanging_reminder.dashboard.server import DashboardServer, MainThreadDispatcher
from hanging_reminder.system.hotkey import HotkeyManager
from hanging_reminder.tasks.repository import TaskRepository
from hanging_reminder.ui.companion_window import CompanionWindow
from hanging_reminder.ui.task_panel import TaskPanel
from hanging_reminder.ui.speech_bubble import SpeechBubble
from hanging_reminder.ui.tray_icon import SpideyTrayIcon, ensure_icon_file
from hanging_reminder.ui.sounds import SoundBoard
from hanging_reminder.ui.quick_add import QuickAddBox
from hanging_reminder.tasks.nlp import describe_deadline
from hanging_reminder.reminders.scheduler import Reminder, ReminderPlanner
from hanging_reminder.system.notifications import Notifier
from hanging_reminder.system.presence import PresenceMonitor
from hanging_reminder.focus.session import BREAK, FOCUSING, FocusSession, format_mmss
from hanging_reminder.system.power_manager import PowerManager
from hanging_reminder.logging_config import logger


# ---------------------------------------------------------------------------
# Application controller
# ---------------------------------------------------------------------------

def _user_tag() -> str:
    if hasattr(os, "getuid"):
        return str(os.getuid())
    try:
        return "".join(c for c in getpass.getuser() if c.isalnum()) or "user"
    except Exception:
        return "user"


IPC_SERVER_NAME = f"spidey-sense-{_user_tag()}"
REMINDER_TICK_MS = 15_000
DND_TOMORROW_HOUR = 8  # "Until tomorrow" ends at 08:00


class HangingReminderApp:
    """Root application controller – creates and manages all UI and backend objects."""

    def __init__(self, self_test: bool = False) -> None:
        self._self_test = self_test
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

        # Sound effects
        self.sounds = SoundBoard(self.config, parent=self._qt_app)
        self.window.web_released.connect(lambda: self.sounds.play("thwip"))
        self.window.web_rebounded.connect(lambda _ratio: self.sounds.play("boing"))
        self._settings_dialog = None

        # Quick-add box (double-tap Spidey, tray menu or the GNOME shortcut)
        self.quick_add = QuickAddBox()
        self.quick_add.submitted.connect(self._on_quick_add)

        # ------------------------------------------------------------------
        # 8. Set up power-event integration (systemd-logind)
        # ------------------------------------------------------------------
        self.power_manager = PowerManager(config=self.config, parent=self._qt_app)
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
        self.task_panel.tasks_changed.connect(self.refresh_task_counts)

        # Tap on Spidey – show pending tasks in a speech bubble
        self.window.tasks_requested.connect(self._show_tasks_bubble)
        self.window.double_tapped.connect(lambda _pos: self.open_quick_add())
        self.window.character_moved.connect(self.speech_bubble.update_anchor)
        self.speech_bubble.open_panel_requested.connect(self._toggle_task_panel)
        self.speech_bubble.dismissed.connect(self._on_bubble_dismissed)
        self.speech_bubble.action_clicked.connect(self.undo_completion)
        self._undo_ids: list[int] = []

        # --------------------------------------------------------------
        # 10a. Taskbar (system tray) icon + Spidey show/hide toggle
        # --------------------------------------------------------------
        icon_path = ensure_icon_file()
        self.tray_icon = SpideyTrayIcon(
            icon_path,
            toggle_handler=self._set_spidey_visible,
            todo_handler=self._toggle_task_panel,
            quit_handler=self._shutdown,
            quick_add_handler=self.open_quick_add,
            settings_handler=self._open_settings,
            dnd_handler=self._set_dnd,
            focus_handler=self._toggle_focus,
            dashboard_handler=self.open_dashboard,
            parent=self._qt_app,
        )
        if self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.show()
            logger.info("Taskbar tray icon visible (toggle: left-click)")
        else:
            logger.warning("System tray not available – toggle via menu only")
        self._qt_app.setWindowIcon(QIcon(icon_path))

        # --------------------------------------------------------------
        # 10b. Smart reminders – due alerts, nags, briefs; wait while away
        # --------------------------------------------------------------
        self.notifier = Notifier(icon_path, tray=self.tray_icon)
        self.presence = PresenceMonitor(self.config, parent=self._qt_app)
        self.presence.changed.connect(self._on_presence_changed)
        self.planner = ReminderPlanner(self.repository, self.config)
        self._reminder_timer = QTimer(self._qt_app, interval=REMINDER_TICK_MS,
                                      timeout=self._on_reminder_tick)
        self._reminder_timer.start()
        self.speech_bubble.done_requested.connect(self.complete_tasks)
        self.speech_bubble.snooze_requested.connect(self.snooze_tasks)

        # --------------------------------------------------------------
        # 10c. Focus timer (Pomodoro)
        # --------------------------------------------------------------
        self.focus = FocusSession(parent=self._qt_app)
        self.focus.ticked.connect(self._on_focus_tick)
        self.focus.finished.connect(self._on_focus_finished)
        self.focus.stopped.connect(self._on_focus_stopped)
        self.task_panel.focus_requested.connect(self.start_focus)

        # --------------------------------------------------------------
        # 10d. Global quick-add shortcut + local web dashboard
        # --------------------------------------------------------------
        self.hotkey = HotkeyManager(parent=self._qt_app)
        self.hotkey.activated.connect(self.open_quick_add)
        if not self_test and self.config.quick_add_hotkey:
            self.hotkey.apply(self.config.quick_add_hotkey)
        self._dispatcher = MainThreadDispatcher(parent=self._qt_app)
        self.dashboard = DashboardServer(DashboardApi(self).handle, self._dispatcher,
                                         favicon=Path(icon_path), port=0 if self_test else 47823)
        self.dashboard.start()

        # Monitors plugged in / out
        self._qt_app.screenAdded.connect(lambda _s: self.window.screens_changed())
        self._qt_app.screenRemoved.connect(lambda _s: QTimer.singleShot(0, self.window.screens_changed))

        # Mood inputs – task counts refreshed periodically and after changes
        self._counts_timer = QTimer(self._qt_app, interval=30_000,
                                    timeout=self.refresh_task_counts)
        self._counts_timer.start()
        self.refresh_task_counts()

        # --------------------------------------------------------------
        # 10c. Do-not-disturb expiry + IPC from later launches
        # --------------------------------------------------------------
        self._dnd_timer = QTimer(self._qt_app, singleShot=True, timeout=self._end_dnd)
        self._ipc_server = QLocalServer(self._qt_app)
        QLocalServer.removeServer(IPC_SERVER_NAME)  # stale socket from a crash
        if self._ipc_server.listen(IPC_SERVER_NAME):
            self._ipc_server.newConnection.connect(self._on_ipc_connection)
        else:
            logger.warning("IPC server unavailable: %s", self._ipc_server.errorString())

        # ------------------------------------------------------------------
        # 10. Show the companion window (it drives its own physics + repaint)
        # ------------------------------------------------------------------
        if self.config.dnd_active():
            self._apply_dnd()
        else:
            self.window.show()

        logger.info("HangingReminderApp fully initialised – running")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_task_toggled(self, task_id: int, completed: bool) -> None:
        """A task was ticked in the mission list – complete (remove) it."""
        if completed:
            self.complete_tasks([task_id])

    def celebrate_completion(self) -> None:
        """Backflip, confetti, cheer – a bigger party when nothing is left."""
        pending = self.repository.count_pending()
        all_done = pending == 0
        self.window.celebrate(big=all_done)
        self.sounds.play("cheer")
        message = ("All missions done! \U0001F578\U0001F389" if all_done
                   else f"Mission complete! {pending} to go.")
        self.speech_bubble.update_anchor(self.window.head_global_pos())
        self.speech_bubble.show_message(message, action="Undo \u21B6" if self._undo_ids else None)
        QTimer.singleShot(self.config.speech_bubble_duration * 2, self.speech_bubble.hide_message)

    def undo_completion(self) -> int:
        """Bring back the tasks completed by the last tick / Done."""
        ids, self._undo_ids = self._undo_ids, []
        restored = [self.repository.undo_complete(cid) for cid in ids]
        restored = [r for r in restored if r is not None]
        if not restored:
            return 0
        if self.task_panel.isVisible():
            self.task_panel.load_tasks()
        self.refresh_task_counts()
        title = self.repository.get(restored[0]).title
        self._say(f"\u21B6 Brought back \u201C{title}\u201D" if len(restored) == 1
                  else f"\u21B6 Brought back {len(restored)} missions")
        logger.info("Undid completion of %d task(s)", len(restored))
        return len(restored)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_ids)

    def tasks_changed_externally(self) -> None:
        """Tasks were edited outside the panel (e.g. the web dashboard)."""
        if self.task_panel.isVisible():
            self.task_panel.load_tasks()
        self.refresh_task_counts()

    def refresh_task_counts(self) -> None:
        """Feed pending/overdue counts to Spidey's mood."""
        try:
            self.window.set_task_counts(self.repository.count_pending(),
                                        self.repository.count_overdue())
        except Exception:
            logger.exception("Could not refresh task counts")

    # ------------------------------------------------------------------
    # Spidey visibility toggle + shutdown (taskbar icon)
    # ------------------------------------------------------------------

    def _set_spidey_visible(self, visible: bool) -> None:
        """Taskbar toggle: show/hide Spidey on all desktops and workspaces."""
        if visible:
            self.window.show()
            self.window.raise_()  # never activate – the overlay refuses focus
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
        """Ask the planner what to show now; it waits while the user is away."""
        now = datetime.now()
        try:
            reminders = self.planner.tick(now, self.presence.state.available)
        except Exception:
            logger.exception("Reminder planning failed")
            return
        if self.focus.state == FOCUSING:
            reminders = [r for r in reminders if r.kind != "nag"]  # don't break focus
        for reminder in reminders:
            self._present(reminder)
            self.planner.delivered(reminder, now)
        if reminders:
            self.config.save()  # brief dates
            self.refresh_task_counts()

    def _on_presence_changed(self, state) -> None:
        logger.info("Presence: away=%s busy=%s", state.away, state.busy)
        self.window.set_away(state.away)
        if state.available:
            QTimer.singleShot(1500, self._on_reminder_tick)  # catch up on return

    def _say(self, message: str) -> None:
        self.speech_bubble.update_anchor(self.window.head_global_pos())
        self.speech_bubble.show_message(message)
        QTimer.singleShot(self.config.speech_bubble_duration, self.speech_bubble.hide_message)

    def _present(self, reminder: Reminder) -> None:
        visible = self.window.isVisible()
        self.speech_bubble.update_anchor(self.window.head_global_pos())
        if reminder.kind == "due":
            self._present_due(reminder.tasks, visible)
        elif reminder.kind == "nag" and visible:
            noun = "mission" if reminder.pending == 1 else "missions"
            self._say(f"\U0001F578 {reminder.pending} {noun} pending, boss! Tap me to see them.")
        elif reminder.kind == "morning" and visible:
            if reminder.tasks:
                self.speech_bubble.show_tasks(
                    reminder.tasks, duration_ms=self.config.speech_bubble_duration * 3,
                    title=f"\u2600 Good morning! {len(reminder.tasks)} for today")
            else:
                self._say("\u2600 Good morning! No missions yet \u2013 double-tap me to add one.")
        elif reminder.kind == "eod" and visible:
            if reminder.tasks:
                self.speech_bubble.show_tasks(
                    reminder.tasks, duration_ms=self.config.speech_bubble_duration * 3,
                    title=f"\U0001F319 {reminder.done_today} done today, {len(reminder.tasks)} left")
            else:
                self._say(f"\U0001F319 All clear \u2013 {reminder.done_today} done today. Great work!")
                self.window.celebrate()
        logger.info("Reminder shown: %s (%d tasks)", reminder.kind, len(reminder.tasks))

    def _present_due(self, tasks: list, visible: bool) -> None:
        single = len(tasks) == 1
        title = "\u23F0 Due now!" if single else f"\u23F0 {len(tasks)} missions due"
        if visible:
            self.window.drop_alert()
            self.sounds.play("alert")
            self.speech_bubble.show_alert(tasks, title=title,
                                          duration_ms=self.config.speech_bubble_duration * 4)
        ids = [t.id for t in tasks]
        if single:
            body = tasks[0].title
            actions = {"done": "Done", "snooze": "Snooze 10 min"}
        else:
            body = "\n".join(f"\u2022 {t.title}" for t in tasks[:5])
            actions = {"open": "Show missions"}

        def on_action(key: str) -> None:
            if key == "done":
                self.complete_tasks(ids)
            elif key == "snooze":
                self.snooze_tasks(ids, 10)
            else:
                self._set_spidey_visible(True)
                if not self.task_panel.isVisible():
                    self._toggle_task_panel()

        self.notifier.notify(f"{title} \u2013 Spidey", body, actions, on_action)

    def complete_tasks(self, task_ids: list) -> None:
        """Complete = remove from the list (kept in history for stats/Undo)."""
        self._undo_ids = [cid for cid in (self.repository.complete(t) for t in task_ids)
                          if cid is not None]
        if not self._undo_ids:
            return
        logger.info("Completed and removed %d task(s)", len(self._undo_ids))
        if self.task_panel.isVisible():
            self.task_panel.load_tasks()
        self.refresh_task_counts()
        self.celebrate_completion()

    def snooze_tasks(self, task_ids: list, minutes: int) -> None:
        from hanging_reminder.ui.task_panel import tomorrow_morning

        until = tomorrow_morning() if minutes < 0 else datetime.now() + timedelta(minutes=minutes)
        for task_id in task_ids:
            self.repository.snooze(task_id, until)
        if self.task_panel.isVisible():
            self.task_panel.load_tasks()
        self._say(f"\U0001F4A4 Okay, I'll remind you {describe_deadline(until).lower()}.")

    # ------------------------------------------------------------------
    # Focus timer
    # ------------------------------------------------------------------

    def start_focus(self, task_id: int | None = None) -> None:
        task = self.repository.get(task_id) if task_id is not None else None
        title = task.title if task else ""
        self.focus.start_focus(int(self.config.focus_minutes), task_id, title)
        self.window.set_focusing(True)
        what = f"\u201C{title}\u201D" if title else "focus mode"
        self._say(f"\U0001F3AF {what} \u2013 {self.config.focus_minutes} min. You got this!")
        logger.info("Focus started (%s min) on %s", self.config.focus_minutes, title or "-")

    def _toggle_focus(self) -> None:
        if self.focus.running:
            self.stop_focus()
        else:
            self.start_focus()

    def stop_focus(self) -> None:
        if not self.focus.running:
            return
        if self.focus.state == FOCUSING:
            self._log_focus(completed=False)
        self.focus.stop()
        self._say("Focus stopped. Take it easy!")

    def _log_focus(self, completed: bool) -> None:
        if self.focus.started_at is None:
            return
        self.repository.add_focus_session(self.focus.task_id, self.focus.started_at,
                                          self.focus.now(), completed)

    def _on_focus_tick(self, state: str, remaining: int, total: int) -> None:
        self.window.set_focus_ring(remaining / total if total else 0.0, state)
        label = "Focus" if state == FOCUSING else "Break"
        title = f" \u2013 {self.focus.task_title}" if state == FOCUSING and self.focus.task_title else ""
        self.tray_icon.set_status("focus", f"{label}: {format_mmss(remaining)} left{title}")
        self.tray_icon.set_focus_label(f"Stop {label.lower()} ({format_mmss(remaining)} left)")

    def _on_focus_finished(self, state: str) -> None:
        if state == FOCUSING:
            self._log_focus(completed=True)
            self.window.set_focusing(False)
            self.window.celebrate()
            self.sounds.play("cheer")
            minutes = int(self.config.break_minutes)
            self.focus.start_break(minutes)
            self._say(f"Focus done! \u2615 {minutes} min break.")
            task_id = self.focus.task_id

            def on_action(key: str) -> None:
                if key == "done" and task_id is not None:
                    self.complete_tasks([task_id])
                elif key == "again":
                    self.focus.stop()
                    self.start_focus(task_id)

            actions = {"again": "Skip break"}
            if task_id is not None:
                actions = {"done": "Task done", **actions}
            self.notifier.notify("Focus session complete \u2013 Spidey",
                                 f"Time for a {minutes}-minute break.", actions, on_action)
        else:
            self.sounds.play("alert")
            self._say("Break's over \u2013 back to it! \U0001F4AA")
            self.notifier.notify("Break's over \u2013 Spidey", "Ready for the next round?")

    def _on_focus_stopped(self) -> None:
        self.window.set_focusing(False)
        self.window.set_focus_ring(None)
        self.tray_icon.set_status("focus", "")
        self.tray_icon.set_focus_label("Start focus session")

    # ------------------------------------------------------------------
    # Quick add, settings, do-not-disturb, IPC
    # ------------------------------------------------------------------

    def open_quick_add(self) -> None:
        """Open the quick-add box next to Spidey."""
        if not self.config.dnd_active():
            self._set_spidey_visible(True)
        self.quick_add.open_at(self.window.head_global_pos())

    def _on_quick_add(self, parsed) -> None:
        self.add_parsed_task(parsed)

    def add_parsed_task(self, parsed) -> int:
        """Save a parsed task and let Spidey react (quick-add box, dashboard)."""
        task_id = self.task_panel.add_task(parsed.title, parsed.deadline, parsed.priority)
        if self.task_panel.isVisible():
            self.task_panel.load_tasks()
        self.window.perform("look_around")
        self.sounds.play("thwip")
        when = f" – due {describe_deadline(parsed.deadline)}" if parsed.deadline else ""
        self.speech_bubble.update_anchor(self.window.head_global_pos())
        self.speech_bubble.show_message(f"Got it! \u201C{parsed.title}\u201D{when}")
        QTimer.singleShot(self.config.speech_bubble_duration, self.speech_bubble.hide_message)
        logger.info("Quick-added task: %s", parsed.title)
        self.refresh_task_counts()
        return task_id

    def open_dashboard(self) -> None:
        if self.dashboard.url:
            QDesktopServices.openUrl(QUrl(self.dashboard.url))
        else:
            self._say("The web dashboard couldn't start \u2013 see the log.")

    def _open_settings(self) -> None:
        from hanging_reminder.ui.settings_dialog import SettingsDialog

        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.config, sounds=self.sounds,
                                                   dashboard_url=self.dashboard.url)
            self._settings_dialog.saved.connect(self._on_settings_saved)
        self._settings_dialog.load_from_config()
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _on_settings_saved(self) -> None:
        self.window.apply_config()
        self.power_manager.set_timeout_ms(self.config.power_reminder_timeout)
        self.hotkey.apply(self.config.quick_add_hotkey)
        logger.info("Settings saved and applied")

    def _set_dnd(self, minutes: int) -> None:
        """Tray: 0 = off, -1 = until tomorrow morning, else for *minutes*."""
        if minutes == 0:
            self._end_dnd()
            return
        now = datetime.now()
        if minutes < 0:
            until = (now + timedelta(days=1)).replace(
                hour=DND_TOMORROW_HOUR, minute=0, second=0, microsecond=0
            )
        else:
            until = now + timedelta(minutes=minutes)
        self.config.dnd_until = until.isoformat(timespec="seconds")
        self.config.save()
        self._apply_dnd()

    def _apply_dnd(self) -> None:
        """Hide Spidey and silence him until ``config.dnd_until``."""
        until = datetime.fromisoformat(self.config.dnd_until)
        self._set_spidey_visible(False)
        remaining_ms = max(0, int((until - datetime.now()).total_seconds() * 1000))
        self._dnd_timer.start(min(remaining_ms, 2**31 - 1))
        label = until.strftime("%H:%M") if until.date() == datetime.now().date() \
            else until.strftime("%a %H:%M")
        self.tray_icon.set_status("dnd", f"Do not disturb until {label}")
        logger.info("Do not disturb until %s", until)

    def _end_dnd(self) -> None:
        self._dnd_timer.stop()
        was_on = bool(self.config.dnd_until)
        self.config.dnd_until = ""
        self.config.save()
        self.tray_icon.set_status("dnd", "")
        if was_on:
            self._set_spidey_visible(True)
            logger.info("Do not disturb ended")

    def _on_ipc_connection(self) -> None:
        socket = self._ipc_server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._on_ipc_message(socket))
        socket.disconnected.connect(socket.deleteLater)

    def _on_ipc_message(self, socket: QLocalSocket) -> None:
        command = bytes(socket.readAll()).decode("utf-8", "replace").strip()
        logger.info("IPC command: %s", command)
        self.handle_command(command)

    def handle_command(self, command: str) -> None:
        if command == "quick-add":
            self.open_quick_add()
        elif command == "dashboard":
            self.open_dashboard()
        elif command == "show":
            if self.config.dnd_active():
                self._end_dnd()
            self._set_spidey_visible(True)

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
        if not pending or self.config.dnd_active():
            self.power_manager.user_continued()  # nothing to remind about / silenced
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
        self.dashboard.stop()
        self.hotkey.shutdown()
        self.tray_icon.shutdown()
        self.repository.close()
        self.power_manager.release_inhibitor()
        # The companion window will be deleted via WA_DeleteOnClose


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _send_to_running_app(command: str) -> bool:
    """Hand *command* to the already-running Spidey over the local socket."""
    socket = QLocalSocket()
    socket.connectToServer(IPC_SERVER_NAME)
    if not socket.waitForConnected(1000):
        return False
    socket.write(command.encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True


def main(argv: list[str] | None = None) -> int:
    """Entry point for the Spider-Man Hanging Reminder application."""
    parser = argparse.ArgumentParser(prog="spidey-sense", description=f"{APP_NAME} desktop companion")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--quick-add", action="store_true",
                        help="open the quick-add box (starts Spidey if needed)")
    parser.add_argument("--show", action="store_true", help="show Spidey")
    parser.add_argument("--dashboard", action="store_true", help="open the web dashboard")
    parser.add_argument("--self-test", action="store_true",
                        help="start offscreen for a few seconds and exit (used by the installer builds)")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    command = "quick-add" if args.quick_add else "dashboard" if args.dashboard else "show"

    # Single instance – autostart, the menu and a manual launch may overlap
    lock = QLockFile(str(paths.runtime_dir() / "spidey-sense.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        if _send_to_running_app(command):
            logger.info("Spidey is already running – sent '%s' to it", command)
        else:
            logger.info("Spidey is already running – not starting a second one")
        return 0

    # Native Wayland forbids clients from positioning themselves, staying on
    # top and shaping their input region – run through XWayland instead.
    if (
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        and "QT_QPA_PLATFORM" not in os.environ
    ):
        import ctypes.util
        # Installed builds bundle libxcb-cursor next to Qt
        if paths.is_frozen() or ctypes.util.find_library("xcb-cursor"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"
        else:
            logger.warning(
                "libxcb-cursor0 is missing – staying on native Wayland, where Spidey "
                "can't stay on top or be dragged freely. Fix: sudo apt install libxcb-cursor0"
            )
    app = HangingReminderApp()
    _first_run_setup()
    if args.quick_add:
        QTimer.singleShot(500, app.open_quick_add)
    elif args.dashboard:
        QTimer.singleShot(500, app.open_dashboard)
    try:
        return app.run()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        return 0
    finally:
        app.close()
        lock.unlock()


def _first_run_setup() -> None:
    """Installed builds: turn on start-at-login once (the Windows installer
    and the Linux install script do this themselves)."""
    marker = paths.data_dir() / ".first-run-done"
    if marker.exists():
        return
    try:
        from hanging_reminder.system import autostart
        if paths.IS_MAC and paths.is_frozen() and not autostart.is_enabled():
            autostart.enable()
        marker.write_text(__version__, encoding="utf-8")
    except OSError:
        logger.exception("First-run setup failed")


def _self_test() -> int:
    """Boot the whole app offscreen for ~3 s with a throwaway profile.

    Catches missing Qt plugins, DLLs or data files in packaged builds.
    """
    import tempfile

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    # offscreen can't shape windows – don't flood the log about it
    os.environ.setdefault("QT_LOGGING_RULES", "default.warning=false")
    with tempfile.TemporaryDirectory(prefix="spidey-selftest-") as tmp:
        for var in ("APPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "HOME", "USERPROFILE"):
            os.environ[var] = tmp
        app = HangingReminderApp(self_test=True)
        ok = {"dashboard": bool(app.dashboard.url)}
        import threading
        probed = threading.Event()

        def probe() -> None:
            import json
            import urllib.request
            request = urllib.request.Request(app.dashboard.url + "api/state",
                                             headers={"X-Spidey-Token": app.dashboard.token})
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    ok["api"] = "tasks" in json.loads(response.read())
            except Exception as exc:
                ok["api"] = False
                print(f"self-test: dashboard API failed: {exc}", file=sys.stderr)
            probed.set()  # never call Qt from this thread

        QTimer.singleShot(2500, lambda: threading.Thread(target=probe, daemon=True).start())
        watcher = QTimer(app._qt_app, interval=100,
                         timeout=lambda: probed.is_set() and app._qt_app.quit())
        watcher.start()
        QTimer.singleShot(15_000, app._qt_app.quit)  # never hang CI
        app.run()
        app.close()
    passed = all(ok.values()) and len(ok) == 2
    print(f"{APP_NAME} {__version__} self-test: {'OK' if passed else 'FAILED'} {ok}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())