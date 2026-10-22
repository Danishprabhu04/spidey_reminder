"""Power-event integration with systemd-logind via D-Bus.

Provides a reminder dialog before the computer enters sleep, suspend,
or shutdown.  Uses logind's inhibitor mechanism to delay the operation
for a bounded window (configurable default: 15 seconds), giving the
user a chance to save work or dismiss the reminder.

Key design points
-----------------
- Does NOT guarantee interception of every power path (physical button
  holds, `systemctl poweroff`, etc. may bypass).
- Acquires a logind Delay inhibitor, which works only when the calling
  user session is managed by systemd (typical on Ubuntu 24.04 GNOME).
- Falls back gracefully if the inhibitor cannot be acquired (e.g. Wayland
  session without logind support, no systemd).
- Uses a QTimer for the timeout so the GUI thread is never blocked.
- Emits signals that the application controller can connect to for
  "cancel" or "continue" actions.
- Documents exactly which power actions are supported and tested.
"""

from __future__ import annotations

import os
import sys
import logging
from typing import Optional, Callable, Dict, Any

import dbus
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtDBus import QDBusConnection, QDBusInterface

from hanging_reminder.config import AppConfig

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("spidey_sense.power")


# ---------------------------------------------------------------------------
# D-Bus constants for org.freedesktop.login1
# ---------------------------------------------------------------------------

_DBUS_SERVICE = "org.freedesktop.login1"
_DBUS_PATH = "/org/freedesktop/login1"
_DBUS_IFACE = "org.freedesktop.login1.Manager"

# Inhibitor flags (from the logind API)
# Type: "sleep", "shutdown", "idle"
# Mode: "block", "delay"
INHIBIT_TYPE_SLEEP = "sleep"
INHIBIT_TYPE_SHUTDOWN = "shutdown"

# D-Bus signal names
SIGNAL_PREPARE_FOR_SLEEP = "PrepareForSleep"
SIGNAL_PREPARE_FOR_SHUTDOWN = "PrepareForShutdown"

# Default timeout in seconds (configurable via AppConfig.power_reminder_timeout)
DEFAULT_POWER_REMINDER_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# PowerManager – core logic
# ---------------------------------------------------------------------------

class PowerManager(QObject):
    """Manages power-event reminders via systemd-logind D-Bus."""

    #: Emitted when a sleep/shutdown reminder is requested.
    #: *args: (operation: str, timeout_secs: int)
    reminder_requested = Signal(str, int)

    #: Emitted when the user chooses "Cancel and stay".
    #: *args: (operation: str)
    cancel_requested = Signal(str)

    #: Emitted when the user chooses "Continue anyway".
    #: *args: (operation: str)
    continue_requested = Signal(str)

    #: Emitted when the reminder times out without user input.
    #: *args: (operation: str)
    timeout_requested = Signal(str)

    def __init__(self, config: AppConfig | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config or AppConfig()
        self._timeout_ms: int = self._config.power_reminder_timeout
        self._inhibitor: Optional[dbus.ObjectPath] = None
        self._inhibit_name: str = f"spiderman-reminder-{os.getpid()}"
        self._current_operation: str = ""  # "sleep" or "shutdown"
        self._timeout_timer: Optional[QTimer] = None

        # D-Bus main loop integration
        self._bus: Optional[dbus.SessionBus] = None
        self._logind: Optional[dbus.Interface] = None

        # ------------------------------------------------------------------
        # Initialise D-Bus connection
        # ------------------------------------------------------------------
        self._init_dbus()

        # ------------------------------------------------------------------
        # Timeout timer – fires after *timeout_ms* milliseconds
        # ------------------------------------------------------------------
        self._timeout_timer = QTimer(self, interval=0, timeout=self._on_timeout)
        # We'll start/stop it as needed.

    # ------------------------------------------------------------------
    # D-Bus initialisation
    # ------------------------------------------------------------------

    def _init_dbus(self) -> None:
        """Connect to the system bus and obtain the logind interface."""
        try:
            # Try the system bus first (most common on Ubuntu 24.04)
            self._bus = dbus.SystemBus()
            logind_obj = self._bus.get_object(_DBUS_SERVICE, _DBUS_PATH)
            self._logind = dbus.Interface(logind_obj, _DBUS_IFACE)

            # Register signal receivers for sleep/shutdown preparation
            self._bus.add_signal_receiver(
                self._on_prepare_sleep,
                dbus_member=SIGNAL_PREPARE_FOR_SLEEP,
                sender=_DBUS_SERVICE,
            )
            self._bus.add_signal_receiver(
                self._on_prepare_shutdown,
                dbus_member=SIGNAL_PREPARE_FOR_SHUTDOWN,
                sender=_DBUS_SERVICE,
            )

            logger.info("D-Bus connected to systemd logind")
        except Exception as exc:
            # D-Bus not available (e.g. no systemd, Wayland without logind,
            # or running in a sandbox).  We operate in degraded mode.
            logger.warning(f"Could not connect to systemd logind via D-Bus: {exc}")
            self._bus = None
            self._logind = None

    # ------------------------------------------------------------------
    # Inhibitor acquisition
    # ------------------------------------------------------------------

    def attempt_inhibit(self, operation: str) -> bool:
        """Request a logind delay inhibitor for *operation*.

        Parameters
        ----------
        operation : str
            Either "sleep" or "shutdown".

        Returns
        -------
        True if the inhibitor was acquired successfully, False otherwise.
        """
        self._current_operation = operation
        if self._logind is None:
            logger.error("Cannot inhibit – logind interface not available")
            self._fallback_no_inhibitor(operation)
            return False

        try:
            # Request a delay inhibitor.
            # The logind API:  InhibitIdle(inhibitor_name, description, type, mode)
            #   type: "sleep" or "shutdown"
            #   mode: "delay" (we only request delay, not block)
            self._inhibitor = self._logind.InhibitIdle(
                self._inhibit_name,
                "Spider-Man Hanging Reminder",
                operation,
                "delay",
            )
            logger.info(f"Acquired logind inhibitor for {operation}: {self._inhibit_name}")
            return True
        except dbus.DBusException as exc:
            logger.error(f"Failed to acquire logind inhibitor: {exc}")
            self._inhibitor = None
            self._fallback_no_inhibitor(operation)
            return False

    # ------------------------------------------------------------------
    # Inhibitor release
    # ------------------------------------------------------------------

    def release_inhibitor(self) -> None:
        """Release the logind inhibitor, if any."""
        if self._inhibitor is not None:
            try:
                # The inhibitor is released when the object goes out of scope
                # or we explicitly close the connection.  Here we just null it.
                self._inhibitor = None
                logger.info("Logind inhibitor released")
            except Exception as exc:
                logger.warning(f"Error releasing inhibitor: {exc}")
        self._inhibitor = None

    # ------------------------------------------------------------------
    # D-Bus signal handlers
    # ------------------------------------------------------------------

    def _on_prepare_sleep(self, message: int, lid: int) -> None:
        """Called by logind when sleep is preparing.

        *message* is the logind PrepareForSleep message type.
        *lid* is the login session ID.
        """
        logger.info(f"PrepareForSleep received (msg={message}, lid={lid})")
        self._show_reminder("sleep")

    def _on_prepare_shutdown(self, message: int, lid: int) -> None:
        """Called by logind when shutdown is preparing."""
        logger.info(f"PrepareForShutdown received (msg={message}, lid={lid})")
        self._show_reminder("shutdown")

    # ------------------------------------------------------------------
    # Reminder flow
# ------------------------------------------------------------------

    def _show_reminder(self, operation: str) -> None:
        """Show the power-event reminder dialog.

        This is a pure signal emission – the application controller/GUI
        is responsible for displaying the actual dialog and returning
        the user's choice.
        """
        self._current_operation = operation
        logger.info(f"Showing power reminder for {operation}")

        # Start the timeout timer (will auto-fire after *timeout_ms*)
        if self._timeout_timer is not None:
            self._timeout_timer.start(self._timeout_ms)
            logger.debug(f"Started {self._timeout_ms}ms timeout timer")

        # Emit the reminder request signal – the GUI will show a dialog
        self.reminder_requested.emit(operation, self._timeout_ms)

    def _on_timeout(self) -> None:
        """Timeout callback – user didn't respond in time."""
        logger.info(f"Power reminder timed out for {self._current_operation}")
        self._timeout_timer.stop()
        self.timeout_requested.emit(self._current_operation)
        # Release the inhibitor so the power action can proceed
        self.release_inhibitor()

    def _fallback_no_inhibitor(self, operation: str) -> None:
        """Called when we cannot acquire a logind inhibitor.

        In this case we still emit the reminder request but without an
        inhibitor – the dialog appears but cannot delay the power action.
        """
        logger.warning(f"No logind inhibitor for {operation} – showing reminder without delay")
        self._current_operation = operation
        if self._timeout_timer is not None:
            self._timeout_timer.start(self._timeout_ms)
        self.reminder_requested.emit(operation, 0)  # timeout=0 means no delay

    # ------------------------------------------------------------------
    # Public API – user choice handling
    # ------------------------------------------------------------------

    def user_cancelled(self) -> None:
        """Call when the user chose "Cancel and stay" in the reminder dialog."""
        logger.info(f"User cancelled {self._current_operation}; requesting inhibitor retention")
        self.cancel_requested.emit(self._current_operation)
        # The inhibitor is already held; we just note the user choice.
        # The application controller should prevent the sleep/shutdown
        # through its own means (e.g. QGssettings, session actions).
        # Note: cannot guarantee cancellation of all power paths.

    def user_continued(self) -> None:
        """Call when the user chose "Continue anyway" in the reminder dialog."""
        logger.info(f"User continued past {self._current_operation}")
        self.continue_requested.emit(self._current_operation)
        # Release the inhibitor promptly so the power action proceeds
        self.release_inhibitor()


# ---------------------------------------------------------------------------
# Convenience helper – high-level wrapper for the application controller
# ---------------------------------------------------------------------------

def show_power_reminder(
    config: AppConfig,
    parent_window,
    operation: str,
) -> bool:
    """High-level wrapper that sets up the PowerManager and returns.

    The caller (application controller) should:
      1. Connect the manager's signals to GUI dialog slots.
      2. Show a dialog with "Cancel and stay" / "Continue anyway" buttons.
      3. On "Cancel", call ``manager.user_cancelled()``.
      4. On "Continue", call ``manager.user_continued()``.

    Returns
    -------
    True if an inhibitor was acquired (delay possible), False otherwise.
    """
    from hanging_reminder.system.power_manager import PowerManager

    manager = PowerManager(config=config, parent=parent_window)
    acquired = manager.attempt_inhibit(operation)

    if not acquired:
        # Still show the reminder dialog even without an inhibitor,
        # so the user gets feedback even if we can't delay the action.
        manager._show_reminder(operation)

    return acquired