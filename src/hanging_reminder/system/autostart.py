"""Start-at-login, per operating system.

- Linux:   an XDG autostart entry in ``~/.config/autostart`` (GNOME starts
           every ``*.desktop`` there at login).  ``Exec`` is an absolute path
           because ``~/.local/bin`` is not always on PATH that early.
- Windows: a value under ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``.
- macOS:   a LaunchAgent plist in ``~/Library/LaunchAgents``.

Usable from the shell too::

    python3 -m hanging_reminder.system.autostart enable|disable|status
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

from hanging_reminder import paths

DESKTOP_FILE = Path.home() / ".config" / "autostart" / "spidey-reminder.desktop"
LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "com.spideysense.app.plist"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "SpideySense"
ICON_PATH = paths.icon_path()


def launcher_path() -> str:
    """Absolute path of the program that starts Spidey."""
    if os.environ.get("APPIMAGE"):  # running from the Linux AppImage
        return os.environ["APPIMAGE"]
    if paths.is_frozen():  # Windows .exe / macOS .app / PyInstaller build
        return sys.executable
    found = shutil.which("hanging-reminder")
    return found or str(Path.home() / ".local" / "bin" / "hanging-reminder")


def launch_command(*args: str) -> str:
    """Shell-quoted launcher command line, e.g. for a hotkey."""
    parts = [launcher_path(), *args]
    if paths.IS_WINDOWS:
        return " ".join(f'"{p}"' if " " in p else p for p in parts)
    return " ".join(shlex.quote(p) for p in parts)


def supported() -> bool:
    return paths.IS_LINUX or paths.IS_WINDOWS or paths.IS_MAC


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------

def desktop_entry(exec_path: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Exec={exec_path}\n"
        f"Icon={ICON_PATH}\n"
        "Hidden=false\n"
        "NoDisplay=false\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-GNOME-Autostart-Delay=3\n"
        "Name=Spidey Sense\n"
        "Comment=A friendly desktop companion helping you remember tasks\n"
        "Categories=Utility;\n"
    )


def _desktop_is_enabled(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return "Hidden=true" not in text and "X-GNOME-Autostart-enabled=false" not in text


def _desktop_enable(path: Path, exec_path: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(desktop_entry(exec_path), encoding="utf-8")
    path.chmod(0o644)


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

def launch_agent_plist(exec_path: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        "  <key>Label</key><string>com.spideysense.app</string>\n"
        f"  <key>ProgramArguments</key><array><string>{exec_path}</string></array>\n"
        "  <key>RunAtLoad</key><true/>\n"
        "</dict></plist>\n"
    )


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _run_key(write: bool = False):
    import winreg
    access = winreg.KEY_READ | (winreg.KEY_SET_VALUE if write else 0)
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, access)


def _windows_is_enabled() -> bool:
    import winreg
    try:
        with _run_key() as key:
            winreg.QueryValueEx(key, RUN_VALUE)
        return True
    except OSError:
        return False


def _windows_enable(exec_path: str) -> None:
    import winreg
    with _run_key(write=True) as key:
        winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, f'"{exec_path}"')


def _windows_disable() -> None:
    import winreg
    try:
        with _run_key(write=True) as key:
            winreg.DeleteValue(key, RUN_VALUE)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def location() -> str:
    if paths.IS_WINDOWS:
        return f"HKCU\\{RUN_KEY}\\{RUN_VALUE}"
    if paths.IS_MAC:
        return str(LAUNCH_AGENT)
    return str(DESKTOP_FILE)


def is_enabled(path: Path | None = None) -> bool:
    if path is None and paths.IS_WINDOWS:
        return _windows_is_enabled()
    if path is None and paths.IS_MAC:
        return LAUNCH_AGENT.exists()
    return _desktop_is_enabled(path or DESKTOP_FILE)


def enable(path: Path | None = None, exec_path: str | None = None) -> None:
    exec_path = exec_path or launcher_path()
    if path is None and paths.IS_WINDOWS:
        _windows_enable(exec_path)
    elif path is None and paths.IS_MAC:
        LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
        LAUNCH_AGENT.write_text(launch_agent_plist(exec_path), encoding="utf-8")
    else:
        _desktop_enable(path or DESKTOP_FILE, exec_path)


def disable(path: Path | None = None) -> None:
    if path is None and paths.IS_WINDOWS:
        _windows_disable()
    elif path is None and paths.IS_MAC:
        LAUNCH_AGENT.unlink(missing_ok=True)
    else:
        (path or DESKTOP_FILE).unlink(missing_ok=True)


def set_enabled(enabled: bool) -> None:
    enable() if enabled else disable()


def _main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "status"
    if command == "enable":
        enable()
    elif command == "disable":
        disable()
    elif command != "status":
        print("usage: python3 -m hanging_reminder.system.autostart enable|disable|status")
        return 2
    print(f"Start at login: {'on' if is_enabled() else 'off'} ({location()})")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
