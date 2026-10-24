"""Application configuration with validation and persistence.

Configuration is stored as JSON at ``~/.config/spidey-sense/config.json``
(default XDG Base Directory compliance).  All values are validated on
load and save; invalid values fall back to defaults.
"""

from __future__ import annotations

import json
import math
from dataclasses import MISSING, dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional

from hanging_reminder import paths


# ---------------------------------------------------------------------------
# XDG base directory paths
# ---------------------------------------------------------------------------

def _config_dir() -> Path:
    """Return the config directory for the application."""
    return paths.config_dir()


def _db_dir() -> Path:
    """Return the data directory for the application."""
    return paths.data_dir()


# ---------------------------------------------------------------------------
# Validation rules (module-level, outside the dataclass)
# ---------------------------------------------------------------------------

_VALIDATION_RULES: Dict[str, Any] = {
    "spring_stiffness": lambda v: v > 0,
    "damping": lambda v: 0.0 <= v < 1.0,
    "gravity": lambda v: v > 0,
    "max_angle": lambda v: 0.01 < v < math.pi,
    "character_size": lambda v: v > 0,
    "speech_bubble_duration": lambda v: v > 0,
    "power_reminder_timeout": lambda v: v > 0,
    "reminder_interval": lambda v: v > 0,
    "anchor_offset_right": lambda v: isinstance(v, (int, float)) and v >= 0,
    "sound_volume": lambda v: isinstance(v, (int, float)) and 0.0 <= v <= 1.0,
    "web_stiffness": lambda v: isinstance(v, (int, float)) and 20.0 <= v <= 300.0,
    "idle_away_seconds": lambda v: isinstance(v, int) and v >= 30,
    "focus_minutes": lambda v: isinstance(v, int) and 1 <= v <= 180,
    "break_minutes": lambda v: isinstance(v, int) and 1 <= v <= 60,
    "end_of_day_time": lambda v: _is_hhmm(v),
    "dnd_until": lambda v: v == "" or _is_iso(v),
    "anchor_offsets": lambda v: isinstance(v, dict),
    "quick_add_hotkey": lambda v: isinstance(v, str),
}


def _is_hhmm(value: Any) -> bool:
    try:
        hours, minutes = str(value).split(":")
        return 0 <= int(hours) < 24 and 0 <= int(minutes) < 60
    except ValueError:
        return False


def _is_iso(value: Any) -> bool:
    from datetime import datetime
    try:
        datetime.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def _default_of(field_name: str) -> Any:
    """The dataclass default for *field_name* (fresh copy for factories)."""
    f = AppConfig.__dataclass_fields__[field_name]
    if f.default_factory is not MISSING:  # type: ignore[misc]
        return f.default_factory()
    return f.default


# ---------------------------------------------------------------------------
# Dataclass configuration
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    """Hold all mutable application settings.

    Physical / animation parameters
    -------------------------------
    spring_stiffness : float
        Hooke's law stiffness coefficient (units: N/m equivalent).  Higher
        values = snappier response, lower = softer, more elastic motion.
    damping : float
        Viscous damping ratio (0 = undamped, 1 = critically damped).
        Recommended range: 0.1 – 0.5.
    gravity : float
        Effective gravity for the pendulum model (m/s²).
    max_angle : float
        Hard clamp on pendulum angle (radians).  Controls how far the
        character swings from vertical.
    character_size : int
        Nominal pixel size of the Spider-Man sprite (square).

    Behavioural
    -----------
    idle_animation : bool
        Enable the subtle idle sway/breathing when the user is not
        interacting.
    reduced_motion : bool
        If True, idle motion is suppressed and the character remains
        closer to vertical.
    start_at_login : bool
        If True, create a desktop autostart entry on first launch.
    sound_effects : bool
        If True, short UI sounds play on interactions (not enabled by
        default to respect user preferences).

    Visual / UI
    -----------
    anchor_corner : str
        Which top corner the web attaches to.  One of:
        "top-left", "top-center", "top-right".
    anchor_offset_right : int
        Distance (px) from the right screen edge to the web's fixed anchor
        on the top bar – under Spidey's tray icon.  Updated when the user
        drops Spidey at the top bar.
    speech_bubble_duration : int
        How long (ms) a speech bubble remains visible after a click.
    power_reminder_timeout : int
        How long (ms) the power-event reminder dialog waits for user input.

    Derived paths (populated after class construction if needed)
    -----------------------------------------------------------
    config_path : str
        Full path to the JSON config file.
    db_path : str
        Full path to the SQLite database.
    """

    # Physics
    spring_stiffness: float = 150.0
    damping: float = 0.2
    gravity: float = 9.81
    max_angle: float = 0.7  # ~40 degrees in radians
    character_size: int = 80

    # Behaviour
    idle_animation: bool = True
    reduced_motion: bool = False
    start_at_login: bool = True
    sound_effects: bool = False
    sound_volume: float = 0.6
    autonomous_moves: bool = True
    eyes_follow_cursor: bool = True

    # Visual / UI
    anchor_corner: str = "top-left"
    anchor_offset_right: int = 160  # Ubuntu puts tray icons near the right end
    anchor_offsets: Dict[str, int] = field(default_factory=dict)  # per screen name
    screen_name: str = ""
    web_stiffness: float = 72.0
    quick_add_hotkey: str = field(
        default_factory=lambda: "<Super><Alt>m" if paths.IS_WINDOWS else "<Super><Shift>m")
    speech_bubble_duration: int = 5000
    power_reminder_timeout: int = 15000

    # Reminders
    reminder_interval: int = 600  # seconds between pending-task reminders
    morning_brief: bool = True
    end_of_day_time: str = "17:30"
    idle_away_seconds: int = 300
    dnd_until: str = ""           # ISO timestamp, "" = off
    last_brief_date: str = ""     # ISO date of the last morning brief
    last_eod_date: str = ""       # ISO date of the last end-of-day brief

    # Focus timer
    focus_minutes: int = 25
    break_minutes: int = 5

    # Derived paths (populated after class construction if needed)
    config_path: str = field(default_factory=lambda: str(_config_dir() / "config.json"))
    db_path: str = field(default_factory=lambda: str(_db_dir() / "tasks.db"))

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def validate(self) -> bool:
        """Return True if all fields satisfy their validation rules.

        Fields that fail validation are silently reset to their defaults.
        """
        changed = False
        for field_name, rule in _VALIDATION_RULES.items():
            value = getattr(self, field_name, None)
            if not rule(value):
                setattr(self, field_name, _default_of(field_name))
                changed = True
        return not changed

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    def anchor_offset_for(self, screen_name: str) -> int:
        """Web anchor distance from the right edge on *screen_name*."""
        return int(self.anchor_offsets.get(screen_name, self.anchor_offset_right))

    def set_anchor_offset(self, screen_name: str, offset: int) -> None:
        self.anchor_offsets[screen_name] = int(offset)
        self.anchor_offset_right = int(offset)  # default for new screens

    def dnd_active(self, now: Optional["datetime"] = None) -> bool:
        """True while do-not-disturb is switched on and not yet expired."""
        if not self.dnd_until:
            return False
        from datetime import datetime
        return (now or datetime.now()) < datetime.fromisoformat(self.dnd_until)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write the current configuration to the XDG config file."""
        path = Path(self.config_path)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
        except OSError as exc:
            import sys
            print(f"[Config] Could not save config: {exc}", file=sys.stderr)

    @classmethod
    def load(cls) -> AppConfig:
        """Load configuration from disk, creating defaults if absent."""
        path = _config_dir() / "config.json"
        instance = cls()

        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Update instance attributes from loaded data
                for key, value in data.items():
                    if hasattr(instance, key):
                        setattr(instance, key, value)
            except (json.JSONDecodeError, OSError) as exc:
                import sys
                print(f"[Config] Could not load config: {exc}", file=sys.stderr)
                # Keep defaults

        # Validate and clamp
        instance.validate()
        return instance