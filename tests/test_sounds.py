"""Tests for the synthesized sound effects – no audio device needed."""

from __future__ import annotations

import wave

from hanging_reminder.ui.sounds import SOUND_NAMES, SAMPLE_RATE, ensure_sound_files


def test_sound_files_are_generated(tmp_path):
    paths = ensure_sound_files(tmp_path)
    assert set(paths) == set(SOUND_NAMES)
    for path in paths.values():
        with wave.open(str(path)) as wav:
            assert wav.getframerate() == SAMPLE_RATE
            assert wav.getnchannels() == 1
            assert 0.1 < wav.getnframes() / SAMPLE_RATE < 1.0


def test_existing_files_are_reused(tmp_path):
    first = ensure_sound_files(tmp_path)
    mtimes = {name: p.stat().st_mtime_ns for name, p in first.items()}
    second = ensure_sound_files(tmp_path)
    assert {name: p.stat().st_mtime_ns for name, p in second.items()} == mtimes


def test_volume_levels_get_their_own_quieter_file(tmp_path):
    from hanging_reminder.ui.sounds import sound_file, volume_step

    assert volume_step(0.64) == 60 and volume_step(1.4) == 100 and volume_step(-1) == 0
    loud = sound_file("cheer", 1.0, tmp_path)
    quiet = sound_file("cheer", 0.3, tmp_path)
    assert loud != quiet and quiet.name.endswith("_30.wav")

    def peak(path):
        import struct
        with wave.open(str(path)) as wav:
            frames = wav.readframes(wav.getnframes())
        return max(abs(v) for (v,) in struct.iter_unpack("<h", frames))

    assert 0.25 < peak(quiet) / peak(loud) < 0.35


def test_soundboard_respects_switch_and_dnd(monkeypatch):
    from hanging_reminder.config import AppConfig
    from hanging_reminder.ui import sounds

    played = []
    board = sounds.SoundBoard(AppConfig(sound_effects=False))
    board._player = ["fake"]
    monkeypatch.setattr(board, "_start", lambda path: played.append(path.name))
    board.play("thwip")
    assert played == []
    board.play("thwip", force=True)
    assert played and played[0].startswith("thwip")
