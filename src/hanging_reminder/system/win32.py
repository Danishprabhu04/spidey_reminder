"""Small ctypes wrappers around the Win32 API (Windows only, imported lazily).

- :func:`idle_ms` – time since the last keyboard/mouse input
- :func:`user_busy` – a fullscreen app, presentation or quiet time is on
- :class:`GlobalHotkey` – ``RegisterHotKey`` + a native event filter that
  catches ``WM_HOTKEY`` on Qt's event loop
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
HOTKEY_ID = 0x5EED

# SHQueryUserNotificationState results that mean "don't interrupt"
QUNS_BUSY = 2                   # fullscreen app
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4
QUNS_QUIET_TIME = 6
_BUSY_STATES = {QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE, QUNS_QUIET_TIME}

_MODIFIERS = {"super": MOD_WIN, "win": MOD_WIN, "meta": MOD_WIN, "ctrl": MOD_CONTROL,
              "control": MOD_CONTROL, "primary": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT}
_NAMED_KEYS = {"space": 0x20, "return": 0x0D, "enter": 0x0D, "tab": 0x09, "escape": 0x1B,
               **{f"f{n}": 0x6F + n for n in range(1, 13)}}


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class _Msg(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


def idle_ms() -> int:
    info = _LastInputInfo(cbSize=ctypes.sizeof(_LastInputInfo))
    try:
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0
        return max(0, (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF)
    except (AttributeError, OSError):
        return 0


def user_busy() -> bool:
    state = ctypes.c_int(0)
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return False
    except (AttributeError, OSError):
        return False
    return state.value in _BUSY_STATES


def parse_binding(binding: str) -> Optional[Tuple[int, int]]:
    """``"<Super><Alt>m"`` -> (MOD_WIN | MOD_ALT, ord('M')); None if unusable."""
    mods, rest = 0, binding.strip()
    while rest.startswith("<"):
        end = rest.find(">")
        if end < 0:
            return None
        mod = _MODIFIERS.get(rest[1:end].lower())
        if mod is None:
            return None
        mods |= mod
        rest = rest[end + 1:]
    key = rest.strip().lower()
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key in _NAMED_KEYS:
        vk = _NAMED_KEYS[key]
    else:
        return None
    return (mods, vk) if mods else None


class GlobalHotkey(QAbstractNativeEventFilter):
    """A system-wide shortcut delivered through Qt's native event filter."""

    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        self._callback = callback
        self._registered = False
        QCoreApplication.instance().installNativeEventFilter(self)

    def register(self, binding: str) -> bool:
        self.unregister()
        parsed = parse_binding(binding)
        if parsed is None:
            return False
        mods, vk = parsed
        self._registered = bool(ctypes.windll.user32.RegisterHotKey(
            None, HOTKEY_ID, mods | MOD_NOREPEAT, vk))
        return self._registered

    def unregister(self) -> None:
        if self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            self._registered = False

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", "windows_generic_MSG") and self._registered:
            msg = _Msg.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._callback()
                return True, 0
        return False, 0
