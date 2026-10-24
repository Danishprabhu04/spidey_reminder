"""Power-event integration with systemd-logind via D-Bus.

Shows a reminder before the computer goes to sleep or shuts down.  A
logind *delay* inhibitor holds the operation back for a bounded window
(``AppConfig.power_reminder_timeout``, capped by logind's
``InhibitDelayMaxUSec``) so Spidey can list your pending tasks first.

Key design points
-----------------
- A delay inhibitor can postpone sleep/shutdown but never cancel it, so
  the reminder ends either on timeout or when the user dismisses it.
- The inhibitor is a file descriptor: holding it open keeps the delay,
  closing it lets the operation proceed.  It is re-acquired on resume.
- D-Bus signals are delivered through the GLib main loop, which Qt's
  event dispatcher already runs on Linux.
- Falls back gracefully when logind is unavailable (no systemd,
  sandbox) – the app keeps working without power reminders.
- Does NOT intercept every power path (holding the power button,
  ``systemctl poweroff -i`` etc. bypass inhibitors).
- Windows/macOS have no logind: there Spidey only gets a last-moment
  shutdown/sign-out reminder through Qt's session manager
  (``commitDataRequest``), which cannot hold the shutdown back.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QGuiApplication

from hanging_reminder import paths

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
_DBUS_PROPS_IFACE = "org.freedesktop.DBus.Properties"

INHIBIT_WHAT = "sleep:shutdown"

# D-Bus signal names
SIGNAL_PREPARE_FOR_SLEEP = "PrepareForSleep"
SIGNAL_PREPARE_FOR_SHUTDOWN = "PrepareForShutdown"

# Leave logind some slack before it gives up on our inhibitor
DELAY_SAFETY_MARGIN_MS = 1000


# ---------------------------------------------------------------------------
# PowerManager – core logic
# ---------------------------------------------------------------------------

class PowerManager(QObject):
    """Manages power-event reminders via systemd-logind D-Bus."""

    #: Emitted when a sleep/shutdown reminder should be shown.
    #: *args: (operation: str, timeout_ms: int) – 0 means it cannot be delayed
    reminder_requested = Signal(str, int)

    #: Emitted when the user dismissed the reminder early.
    #: *args: (operation: str)
    continue_requested = Signal(str)

    #: Emitted when the reminder times out without user input.
    #: *args: (operation: str)
    timeout_requested = Signal(str)

    def __init__(self, config: AppConfig | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config or AppConfig()
        self._timeout_ms: int = self._config.power_reminder_timeout
        self._inhibit_fd: Optional[int] = None
        self._current_operation: str = ""  # "sleep" or "shutdown"

        self._bus = None      # dbus.SystemBus (Linux only)
        self._logind = None   # dbus.Interface
        self._max_delay_ms: int = 2**31 - 1

        # Timeout timer – releases the inhibitor so the operation proceeds
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

        if paths.IS_LINUX:
            self._init_dbus()
        else:
            self._init_session_manager()
        if self._logind is not None:
            self.attempt_inhibit()

    # ------------------------------------------------------------------
    # D-Bus initialisation
    # ------------------------------------------------------------------

    def _init_dbus(self) -> None:
        """Connect to the system bus and subscribe to logind's signals."""
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            DBusGMainLoop(set_as_default=True)

            self._bus = dbus.SystemBus()
            logind_obj = self._bus.get_object(_DBUS_SERVICE, _DBUS_PATH)
            self._logind = dbus.Interface(logind_obj, _DBUS_IFACE)

            self._bus.add_signal_receiver(
                self._on_prepare_sleep,
                signal_name=SIGNAL_PREPARE_FOR_SLEEP,
                dbus_interface=_DBUS_IFACE,
                bus_name=_DBUS_SERVICE,
            )
            self._bus.add_signal_receiver(
                self._on_prepare_shutdown,
                signal_name=SIGNAL_PREPARE_FOR_SHUTDOWN,
                dbus_interface=_DBUS_IFACE,
                bus_name=_DBUS_SERVICE,
            )

            # Never ask for a longer delay than logind will honour
            max_usec = int(logind_obj.Get(
                _DBUS_IFACE, "InhibitDelayMaxUSec", dbus_interface=_DBUS_PROPS_IFACE
            ))
            self._max_delay_ms = max(0, max_usec // 1000 - DELAY_SAFETY_MARGIN_MS)
            self._timeout_ms = min(self._timeout_ms, self._max_delay_ms)

            logger.info("D-Bus connected to systemd logind (reminder window %d ms)", self._timeout_ms)
        except Exception as exc:
            logger.warning("Could not connect to systemd logind via D-Bus: %s", exc)
            self._bus = None
            self._logind = None

    def _init_session_manager(self) -> None:
        """Windows/macOS: remind at sign-out/shutdown (cannot be delayed)."""
        app = QGuiApplication.instance()
        if app is not None:
            app.commitDataRequest.connect(lambda _manager: self._show_reminder("shutdown"))

    def set_timeout_ms(self, timeout_ms: int) -> None:
        """Change the reminder window (still capped by logind's maximum)."""
        self._timeout_ms = min(int(timeout_ms), self._max_delay_ms)

    # ------------------------------------------------------------------
    # Inhibitor
    # ------------------------------------------------------------------

    @property
    def has_inhibitor(self) -> bool:
        return self._inhibit_fd is not None

    def attempt_inhibit(self) -> bool:
        """Take a logind delay inhibitor for sleep and shutdown.

        Returns True if the inhibitor is held.
        """
        if self._inhibit_fd is not None:
            return True
        if self._logind is None:
            return False
        try:
            fd = self._logind.Inhibit(
                INHIBIT_WHAT,
                "Spidey Sense",
                "Show pending missions before sleep or shutdown",
                "delay",
            )
            self._inhibit_fd = fd.take()
            logger.info("Acquired logind delay inhibitor for %s", INHIBIT_WHAT)
            return True
        except Exception as exc:  # dbus.DBusException
            logger.warning("Failed to acquire logind inhibitor: %s", exc)
            self._inhibit_fd = None
            return False

    def release_inhibitor(self) -> None:
        """Close the inhibitor fd so a pending sleep/shutdown proceeds."""
        self._timeout_timer.stop()
        if self._inhibit_fd is None:
            return
        try:
            os.close(self._inhibit_fd)
            logger.info("Logind inhibitor released")
        except OSError as exc:
            logger.warning("Error releasing inhibitor: %s", exc)
        self._inhibit_fd = None

    # ------------------------------------------------------------------
    # D-Bus signal handlers
    # ------------------------------------------------------------------

    def _on_prepare_sleep(self, starting: bool) -> None:
        """logind: True right before sleep, False after resume."""
        logger.info("PrepareForSleep(%s)", bool(starting))
        if starting:
            self._show_reminder("sleep")
        else:
            self.attempt_inhibit()  # ready for the next sleep

    def _on_prepare_shutdown(self, starting: bool) -> None:
        """logind: True right before shutdown/reboot."""
        logger.info("PrepareForShutdown(%s)", bool(starting))
        if starting:
            self._show_reminder("shutdown")

    # ------------------------------------------------------------------
    # Reminder flow
    # ------------------------------------------------------------------

    def _show_reminder(self, operation: str) -> None:
        """Ask the GUI to show the reminder while the inhibitor holds."""
        self._current_operation = operation
        if self.has_inhibitor:
            self._timeout_timer.start(self._timeout_ms)
            self.reminder_requested.emit(operation, self._timeout_ms)
        else:
            self.reminder_requested.emit(operation, 0)

    def _on_timeout(self) -> None:
        """The user didn't respond in time – let the operation proceed."""
        logger.info("Power reminder timed out for %s", self._current_operation)
        self.timeout_requested.emit(self._current_operation)
        self.release_inhibitor()

    # ------------------------------------------------------------------
    # Public API – user choice handling
    # ------------------------------------------------------------------

    def user_continued(self) -> None:
        """The user dismissed the reminder – let the operation proceed now."""
        logger.info("User continued past %s", self._current_operation)
        self.continue_requested.emit(self._current_operation)
        self.release_inhibitor()
