"""Is the user actually at the computer?  (GNOME session D-Bus + X11)

Polled every few seconds:

- idle time   – ``org.gnome.Mutter.IdleMonitor.GetIdletime`` (ms)
- screen lock – ``org.gnome.ScreenSaver.GetActive`` (+ its ActiveChanged signal)
- fullscreen  – best effort: the active X11 window's ``_NET_WM_STATE`` via
  ``xprop``.  Native Wayland apps are invisible to an XWayland client, so a
  fullscreen Wayland video won't be detected.

Windows: ``GetLastInputInfo`` for idle time and
``SHQueryUserNotificationState`` for fullscreen apps / presentations /
quiet hours.  macOS: ``ioreg`` HIDIdleTime (best effort).

``away`` = idle too long or locked; ``busy`` = something is fullscreen.
Reminders wait while either is true.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

from hanging_reminder import paths

POLL_MS = 5000
_ACTIVE_RE = re.compile(r"window id # (0x[0-9a-f]+)", re.I)


@dataclass(frozen=True)
class PresenceState:
    away: bool = False
    busy: bool = False

    @property
    def available(self) -> bool:
        return not (self.away or self.busy)


def presence_state(idle_ms: int, locked: bool, fullscreen: bool, away_after_ms: int) -> PresenceState:
    return PresenceState(away=locked or idle_ms >= away_after_ms, busy=fullscreen)


def x11_active_window_fullscreen() -> bool:
    """True if the focused X11 window is fullscreen (False if unknown)."""
    if shutil.which("xprop") is None:
        return False
    try:
        root = subprocess.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"], capture_output=True,
                              text=True, timeout=1).stdout
        match = _ACTIVE_RE.search(root)
        if not match or int(match.group(1), 16) == 0:
            return False
        state = subprocess.run(["xprop", "-id", match.group(1), "_NET_WM_STATE"],
                               capture_output=True, text=True, timeout=1).stdout
        return "_NET_WM_STATE_FULLSCREEN" in state
    except (subprocess.SubprocessError, OSError):
        return False


_HID_IDLE_RE = re.compile(r'"HIDIdleTime"\s*=\s*(\d+)')


def mac_idle_ms() -> int:
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True,
                             text=True, timeout=2).stdout
    except (subprocess.SubprocessError, OSError):
        return 0
    match = _HID_IDLE_RE.search(out)
    return int(match.group(1)) // 1_000_000 if match else 0  # ns -> ms


class PresenceMonitor(QObject):
    changed = Signal(object)  # PresenceState

    def __init__(self, config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self.state = PresenceState()
        self._idle = None
        self._screensaver = None
        if paths.IS_LINUX:
            self._init_dbus()

        self._timer = QTimer(self, interval=POLL_MS, timeout=self.poll)
        self._timer.start()

    def _init_dbus(self) -> None:
        from hanging_reminder.logging_config import logger
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            DBusGMainLoop(set_as_default=True)
            bus = dbus.SessionBus()
            self._idle = dbus.Interface(
                bus.get_object("org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core"),
                "org.gnome.Mutter.IdleMonitor",
            )
            self._screensaver = dbus.Interface(
                bus.get_object("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver"),
                "org.gnome.ScreenSaver",
            )
            # React to lock/unlock immediately instead of on the next poll
            bus.add_signal_receiver(lambda _active: self.poll(), signal_name="ActiveChanged",
                                    dbus_interface="org.gnome.ScreenSaver")
        except Exception as exc:
            logger.warning("Presence detection limited (no GNOME session bus): %s", exc)

    def _idle_ms(self) -> int:
        if paths.IS_WINDOWS:
            from hanging_reminder.system import win32
            return win32.idle_ms()
        if paths.IS_MAC:
            return mac_idle_ms()
        try:
            return int(self._idle.GetIdletime()) if self._idle is not None else 0
        except Exception:
            return 0

    def _locked(self) -> bool:
        try:
            return bool(self._screensaver.GetActive()) if self._screensaver is not None else False
        except Exception:
            return False

    def _fullscreen(self) -> bool:
        if paths.IS_WINDOWS:
            from hanging_reminder.system import win32
            return win32.user_busy()
        if paths.IS_LINUX:
            return x11_active_window_fullscreen()
        return False

    def poll(self) -> PresenceState:
        state = presence_state(
            self._idle_ms(),
            self._locked(),
            self._fullscreen(),
            int(self._config.idle_away_seconds) * 1000,
        )
        if state != self.state:
            self.state = state
            self.changed.emit(state)
        return state
