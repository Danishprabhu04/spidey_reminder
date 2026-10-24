"""Desktop notifications with action buttons (org.freedesktop.Notifications).

Used for due-time alerts so they're seen even when Spidey is hidden or
the user is in another app.  ``ActionInvoked`` is routed back to the
callback registered for that notification.

Windows/macOS (or no notification daemon): falls back to the tray icon's
balloon/toast via ``QSystemTrayIcon.showMessage``.  Those have no buttons,
so clicking the message invokes the callback with ``"open"``.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from hanging_reminder import paths
from hanging_reminder.logging_config import logger

APP_NAME = "Spidey Sense"
EXPIRE_MS = 15000


class Notifier:
    def __init__(self, icon_path: str = "", tray=None) -> None:
        self._icon = icon_path
        self._iface = None
        self._dbus = None
        self._callbacks: Dict[int, Callable[[str], None]] = {}
        self._tray = tray
        self._tray_callback: Optional[Callable[[str], None]] = None
        if tray is not None:
            tray.messageClicked.connect(self._on_tray_clicked)
        if not paths.IS_LINUX:
            return
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            DBusGMainLoop(set_as_default=True)
            self._dbus = dbus
            bus = dbus.SessionBus()
            obj = bus.get_object("org.freedesktop.Notifications", "/org/freedesktop/Notifications")
            self._iface = dbus.Interface(obj, "org.freedesktop.Notifications")
            bus.add_signal_receiver(self._on_action, signal_name="ActionInvoked",
                                    dbus_interface="org.freedesktop.Notifications")
            bus.add_signal_receiver(self._on_closed, signal_name="NotificationClosed",
                                    dbus_interface="org.freedesktop.Notifications")
        except Exception as exc:
            logger.warning("Desktop notifications unavailable: %s", exc)

    @property
    def available(self) -> bool:
        return self._iface is not None or self._tray is not None

    def notify(self, summary: str, body: str = "",
               actions: Optional[Dict[str, str]] = None,
               on_action: Optional[Callable[[str], None]] = None) -> int:
        """Show a notification; *actions* maps action key -> button label."""
        if self._iface is None:
            return self._notify_tray(summary, body, on_action)
        flat = []
        for key, label in (actions or {}).items():
            flat += [key, label]
        try:
            nid = int(self._iface.Notify(APP_NAME, 0, self._icon, summary, body, flat,
                                         {"urgency": self._dbus.Byte(1)}, EXPIRE_MS))
        except Exception:
            logger.exception("Notification failed")
            return 0
        if on_action is not None:
            self._callbacks[nid] = on_action
        return nid

    def _notify_tray(self, summary: str, body: str,
                     on_action: Optional[Callable[[str], None]]) -> int:
        if self._tray is None or not self._tray.isVisible():
            return 0
        from PySide6.QtGui import QIcon
        self._tray_callback = on_action
        self._tray.showMessage(summary, body, QIcon(self._icon), EXPIRE_MS)
        return -1

    def _on_tray_clicked(self) -> None:
        callback, self._tray_callback = self._tray_callback, None
        if callback is not None:
            callback("open")

    def _on_action(self, nid, action_key) -> None:
        callback = self._callbacks.pop(int(nid), None)
        if callback is not None:
            callback(str(action_key))

    def _on_closed(self, nid, _reason) -> None:
        self._callbacks.pop(int(nid), None)
