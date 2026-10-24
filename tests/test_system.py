"""Tests for desktop-integration helpers (no GNOME session needed)."""

from __future__ import annotations

import sys

import pytest

from hanging_reminder.system import autostart
from hanging_reminder.system.gnome_keybinding import format_path_list, parse_path_list


def test_autostart_enable_disable(tmp_path):
    entry = tmp_path / "autostart" / "spidey.desktop"
    assert not autostart.is_enabled(entry)
    autostart.enable(entry, exec_path="/opt/spidey/bin/hanging-reminder")
    text = entry.read_text()
    assert "Exec=/opt/spidey/bin/hanging-reminder" in text
    assert autostart.is_enabled(entry)
    if sys.platform != "win32":  # Windows has no Unix permission bits
        assert entry.stat().st_mode & 0o777 == 0o644
    autostart.disable(entry)
    assert not autostart.is_enabled(entry)


def test_gsettings_path_lists_round_trip():
    assert parse_path_list("@as []") == []
    paths = parse_path_list("['/a/custom0/', '/b/spidey/']")
    assert paths == ["/a/custom0/", "/b/spidey/"]
    assert parse_path_list(format_path_list(paths)) == paths


# ---------------------------------------------------------------------------
# Cross-platform helpers
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="XDG paths are Linux-only")
def test_paths_follow_xdg_on_linux(isolated_profile):
    from hanging_reminder import paths

    assert paths.config_dir() == isolated_profile / ".config" / "spidey-sense"
    assert paths.data_dir() == isolated_profile / ".local" / "share" / "spidey-sense"
    assert paths.resource_path("dashboard", "static", "index.html").exists()


def test_paths_on_windows(monkeypatch, isolated_profile):
    from hanging_reminder import paths

    monkeypatch.setattr(paths, "IS_WINDOWS", True)
    monkeypatch.setattr(paths, "IS_LINUX", False)
    assert paths.config_dir() == isolated_profile / "AppData" / "SpideySense"
    assert paths.data_dir() == paths.config_dir()
    assert paths.runtime_dir() == paths.data_dir()


def test_launcher_prefers_appimage_and_frozen_exe(monkeypatch):
    import sys

    monkeypatch.setenv("APPIMAGE", "/home/me/Apps/SpideySense.AppImage")
    assert autostart.launcher_path() == "/home/me/Apps/SpideySense.AppImage"
    monkeypatch.delenv("APPIMAGE")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert autostart.launcher_path() == sys.executable


def test_launch_agent_plist_runs_at_load():
    plist = autostart.launch_agent_plist("/Applications/Spidey Sense.app/Contents/MacOS/SpideySense")
    assert "<key>RunAtLoad</key><true/>" in plist
    assert "/Applications/Spidey Sense.app/Contents/MacOS/SpideySense" in plist


def test_windows_hotkey_parsing():
    from hanging_reminder.system import win32

    assert win32.parse_binding("<Super><Alt>m") == (win32.MOD_WIN | win32.MOD_ALT, ord("M"))
    assert win32.parse_binding("<Ctrl><Shift>F5") == (win32.MOD_CONTROL | win32.MOD_SHIFT, 0x74)
    assert win32.parse_binding("m") is None          # needs a modifier
    assert win32.parse_binding("<Hyper>m") is None   # unknown modifier


def test_hotkey_pretty_names():
    from hanging_reminder.system.hotkey import pretty

    assert pretty("<Super><Shift>m") in ("Super+Shift+M", "Win+Shift+M")
    assert pretty("<Ctrl><Alt>t") == "Ctrl+Alt+T"
