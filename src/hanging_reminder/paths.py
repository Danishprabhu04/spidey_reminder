"""Every file location Spidey uses, per operating system.

- Linux:   ``~/.config/spidey-sense`` + ``~/.local/share/spidey-sense`` (XDG)
- Windows: ``%APPDATA%\\SpideySense`` (config and data together)
- macOS:   ``~/Library/Application Support/SpideySense``

``resource_path`` finds files shipped with the app, both from a source
checkout and inside a PyInstaller bundle.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

_PACKAGE_DIR = Path(__file__).resolve().parent


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _base(kind: str) -> Path:
    if IS_WINDOWS:
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "SpideySense"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "SpideySense"
    if kind == "config":
        root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    else:
        root = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(root) / "spidey-sense"


def config_dir() -> Path:
    return _ensure(_base("config"))


def data_dir() -> Path:
    return _ensure(_base("data"))


def sounds_dir() -> Path:
    return data_dir() / "sounds"


def log_path() -> Path:
    return data_dir() / "log.txt"


def icon_path() -> Path:
    return data_dir() / "spidey_icon.png"


def runtime_dir() -> Path:
    """Per-session directory for the single-instance lock and dashboard port."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if IS_LINUX and runtime and Path(runtime).is_dir():
        return Path(runtime)
    return data_dir()


def is_frozen() -> bool:
    """True when running from a PyInstaller-built installer."""
    return bool(getattr(sys, "frozen", False))


def resource_path(*parts: str) -> Path:
    """A file shipped inside the package (works in a PyInstaller bundle too)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS, "hanging_reminder", *parts)
    return _PACKAGE_DIR.joinpath(*parts)
