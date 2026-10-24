"""Short synthesized sound effects for Spidey.

The WAVs are generated with plain math on first use (no binary assets in
the repo) into the app's data folder and played with the system's own
player – ``winsound`` on Windows, ``afplay`` on macOS, ``paplay`` /
``pw-play`` / ``aplay`` on Linux – so the installers don't need the large
Qt Multimedia module.  Volume is baked into a per-level copy of each WAV
(10 % steps).  Every play respects the user's sound settings and
do-not-disturb.

Sounds
------
- ``thwip`` : web shot (released after a drag)
- ``boing`` : the web snapping back after a big stretch
- ``cheer`` : a task was completed
- ``alert`` : a reminder needs attention
"""

from __future__ import annotations

import math
import random
import shutil
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Callable, Dict, List

SAMPLE_RATE = 44100
SOUND_VERSION = 1  # bump to regenerate files after changing the synthesis
SOUND_NAMES = ("thwip", "boing", "cheer", "alert")
MIN_REPEAT_S = {"boing": 0.35, "thwip": 0.15}  # avoid machine-gun repeats


def _sounds_dir() -> Path:
    from hanging_reminder import paths
    return paths.sounds_dir()


# ---------------------------------------------------------------------------
# Synthesis – each returns float samples in [-1, 1]
# ---------------------------------------------------------------------------

def _envelope(t: float, attack: float, decay: float) -> float:
    return min(1.0, t / attack) * math.exp(-t / decay) if attack > 0 else math.exp(-t / decay)


def _thwip() -> List[float]:
    rng = random.Random(7)
    n = int(0.20 * SAMPLE_RATE)
    out, phase, smooth = [], 0.0, 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = 3200.0 * math.exp(-t * 14.0) + 500.0      # falling sweep
        phase += 2 * math.pi * freq / SAMPLE_RATE
        smooth += (rng.uniform(-1, 1) - smooth) * 0.35  # softened noise
        out.append((0.55 * math.sin(phase) + 0.45 * smooth) * _envelope(t, 0.004, 0.06))
    return out


def _boing() -> List[float]:
    n = int(0.38 * SAMPLE_RATE)
    out, phase = [], 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = 260.0 * (1.0 + 0.45 * math.sin(2 * math.pi * 11.0 * t) * math.exp(-t * 7.0))
        phase += 2 * math.pi * freq / SAMPLE_RATE
        out.append(math.sin(phase) * _envelope(t, 0.005, 0.14))
    return out


def _tone(freq: float, seconds: float, decay: float) -> List[float]:
    n = int(seconds * SAMPLE_RATE)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        w = 2 * math.pi * freq * t
        sample = math.sin(w) + 0.3 * math.sin(2 * w) + 0.12 * math.sin(3 * w)
        out.append(sample / 1.42 * _envelope(t, 0.004, decay))
    return out


def _cheer() -> List[float]:
    out: List[float] = []
    for freq in (523.25, 659.25, 783.99):          # C5 E5 G5
        out += _tone(freq, 0.09, 0.08)
    out += _tone(1046.5, 0.35, 0.16)               # C6, held
    return out


def _alert() -> List[float]:
    out: List[float] = []
    for _ in range(2):
        out += _tone(880.0, 0.11, 0.09) + _tone(1318.5, 0.13, 0.10)
        out += [0.0] * int(0.06 * SAMPLE_RATE)
    return out


_SYNTHS: Dict[str, Callable[[], List[float]]] = {
    "thwip": _thwip,
    "boing": _boing,
    "cheer": _cheer,
    "alert": _alert,
}


def write_wav(path: Path, samples: List[float], gain: float = 0.8) -> None:
    """Write mono 16-bit PCM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, s * gain)) * 32767)) for s in samples
    )
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(frames)


def volume_step(volume: float) -> int:
    """0.0–1.0 -> 0, 10, …, 100 (percent, rounded to the nearest 10)."""
    return int(round(max(0.0, min(1.0, float(volume))) * 10)) * 10


def sound_file(name: str, volume: float = 1.0, directory: Path | None = None) -> Path:
    """Path of *name* at *volume*, generating the WAV on first use."""
    directory = directory or _sounds_dir()
    step = volume_step(volume)
    suffix = "" if step == 100 else f"_{step}"
    path = directory / f"{name}_v{SOUND_VERSION}{suffix}.wav"
    if not path.exists():
        write_wav(path, _SYNTHS[name](), gain=0.8 * step / 100)
    return path


def ensure_sound_files(directory: Path | None = None) -> Dict[str, Path]:
    """Generate any missing full-volume sound files; return name -> path."""
    return {name: sound_file(name, 1.0, directory) for name in SOUND_NAMES}


def find_player() -> List[str] | None:
    """Command (without the file) that plays a WAV, or None."""
    if sys.platform == "win32":
        return ["winsound"]
    if sys.platform == "darwin":
        return ["afplay"] if shutil.which("afplay") else None
    for command in (["paplay"], ["pw-play"], ["aplay", "-q"]):
        if shutil.which(command[0]):
            return command
    return None


# ---------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------

class SoundBoard:
    """Plays the effects, honouring ``config.sound_effects``/volume/DND."""

    def __init__(self, config, parent=None) -> None:
        self._config = config
        self._last_played: Dict[str, float] = {}
        self._player = find_player()
        if self._player is None:
            from hanging_reminder.logging_config import logger
            logger.warning("No audio player found – sound effects are off")

    def play(self, name: str, force: bool = False) -> None:
        """Play *name*; ``force`` ignores the on/off switch (settings preview)."""
        if not force and (not self._config.sound_effects or self._config.dnd_active()):
            return
        if self._player is None or name not in _SYNTHS:
            return
        now = time.monotonic()
        if now - self._last_played.get(name, 0.0) < MIN_REPEAT_S.get(name, 0.0):
            return
        self._last_played[name] = now
        volume = float(self._config.sound_volume)
        if volume_step(volume) == 0:
            return
        try:
            self._start(sound_file(name, volume))
        except OSError:
            from hanging_reminder.logging_config import logger
            logger.exception("Could not play sound %s", name)

    def _start(self, path: Path) -> None:
        if self._player == ["winsound"]:
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC
                               | winsound.SND_NODEFAULT)
            return
        subprocess.Popen([*self._player, str(path)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
