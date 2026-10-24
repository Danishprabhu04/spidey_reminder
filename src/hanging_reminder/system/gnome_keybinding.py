"""Global quick-add hotkey via a GNOME custom keyboard shortcut.

Apps running through XWayland cannot grab keys globally, so the shortcut
is registered with GNOME itself (Settings → Keyboard → Custom Shortcuts).
It runs ``hanging-reminder --quick-add``; that second launch hands the
command to the running Spidey over a local socket and exits.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
from typing import List

SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = SCHEMA + ".custom-keybinding"
KEY_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/spidey-quick-add/"
NAME = "Spidey quick add"


def parse_path_list(text: str) -> List[str]:
    """Parse gsettings' GVariant string array output (``@as []`` or ``['/a/']``)."""
    text = text.strip()
    if text.startswith("@as"):
        text = text[3:].strip()
    value = ast.literal_eval(text) if text else []
    return [str(v) for v in value]


def format_path_list(paths: List[str]) -> str:
    return "[" + ", ".join(f"'{p}'" for p in paths) + "]"


def available() -> bool:
    return shutil.which("gsettings") is not None


def _gsettings(*args: str) -> str:
    return subprocess.run(
        ["gsettings", *args], check=True, capture_output=True, text=True, timeout=5
    ).stdout


def _custom(*args: str) -> str:
    return _gsettings(args[0], f"{CUSTOM_SCHEMA}:{KEY_PATH}", *args[1:])


def current_binding() -> str:
    """The registered shortcut (e.g. ``<Super><Shift>m``) or "" if none."""
    if not available():
        return ""
    try:
        if KEY_PATH not in parse_path_list(_gsettings("get", SCHEMA, "custom-keybindings")):
            return ""
        return ast.literal_eval(_custom("get", "binding").strip())
    except (subprocess.SubprocessError, ValueError, SyntaxError):
        return ""


def register(binding: str, command: str) -> bool:
    """Create/update the shortcut. Returns False if gsettings is unavailable."""
    if not available():
        return False
    paths = parse_path_list(_gsettings("get", SCHEMA, "custom-keybindings"))
    if KEY_PATH not in paths:
        paths.append(KEY_PATH)
        _gsettings("set", SCHEMA, "custom-keybindings", format_path_list(paths))
    _custom("set", "name", NAME)
    _custom("set", "command", command)
    _custom("set", "binding", binding)
    return True


def unregister() -> None:
    if not available():
        return
    paths = parse_path_list(_gsettings("get", SCHEMA, "custom-keybindings"))
    if KEY_PATH in paths:
        paths.remove(KEY_PATH)
        _gsettings("set", SCHEMA, "custom-keybindings", format_path_list(paths))
    for key in ("name", "command", "binding"):
        _custom("reset", key)
