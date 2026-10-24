"""Global quick-add shortcut, per operating system.

- Linux (GNOME): a custom keyboard shortcut registered with gsettings that
  runs ``hanging-reminder --quick-add`` (see :mod:`gnome_keybinding`).
- Windows: ``RegisterHotKey`` while Spidey runs (see :mod:`win32`).
- macOS: not available yet.

Bindings use GNOME's notation everywhere, e.g. ``<Super><Shift>m``.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from hanging_reminder import paths
from hanging_reminder.logging_config import logger

LINUX_DEFAULT = "<Super><Shift>m"
WINDOWS_DEFAULT = "<Super><Alt>m"  # Win+Shift+M is taken by Windows itself


def default_binding() -> str:
    return WINDOWS_DEFAULT if paths.IS_WINDOWS else LINUX_DEFAULT


def pretty(binding: str) -> str:
    """``<Super><Shift>m`` -> ``Super+Shift+M`` (``Win+…`` on Windows)."""
    text = binding.replace("><", "+").replace("<", "").replace(">", "+")
    parts = [p for p in text.split("+") if p]
    names = {"super": "Win" if paths.IS_WINDOWS else "Super", "ctrl": "Ctrl",
             "control": "Ctrl", "alt": "Alt", "shift": "Shift", "primary": "Ctrl"}
    return "+".join(names.get(p.lower(), p.upper() if len(p) == 1 else p.title()) for p in parts)


class HotkeyManager(QObject):
    #: The shortcut was pressed (Windows; on Linux GNOME launches us instead)
    activated = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._win = None

    @staticmethod
    def supported() -> bool:
        if paths.IS_WINDOWS:
            return True
        if paths.IS_LINUX:
            from hanging_reminder.system import gnome_keybinding
            return gnome_keybinding.available()
        return False

    def apply(self, binding: str) -> bool:
        """Register *binding* ("" removes the shortcut). True on success."""
        try:
            if paths.IS_WINDOWS:
                return self._apply_windows(binding)
            if paths.IS_LINUX:
                return self._apply_gnome(binding)
        except Exception:
            logger.exception("Could not set the quick-add shortcut %r", binding)
        return False

    def _apply_windows(self, binding: str) -> bool:
        from hanging_reminder.system import win32

        if self._win is None:
            self._win = win32.GlobalHotkey(self.activated.emit)
        if not binding:
            self._win.unregister()
            return True
        ok = self._win.register(binding)
        if not ok:
            logger.warning("Shortcut %s is taken by another app", pretty(binding))
        return ok

    @staticmethod
    def _apply_gnome(binding: str) -> bool:
        from hanging_reminder.system import autostart, gnome_keybinding

        if not binding:
            gnome_keybinding.unregister()
            return True
        return gnome_keybinding.register(binding, autostart.launch_command("--quick-add"))

    def shutdown(self) -> None:
        if self._win is not None:
            self._win.unregister()
