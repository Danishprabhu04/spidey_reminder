"""Application configuration with validation and persistence.

Configuration is stored as JSON at ``~/.config/spidey-sense/config.json``
(default XDG Base Directory compliance).  All values are validated on
load and save; invalid values fall back to defaults.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# XDG base directory paths
# ---------------------------------------------------------------------------

def _config_dir() -> Path:
    """Return the XDG config directory for the application."""
    base = Path.home() / ".config" / "spidey-sense"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _db_dir() -> Path:
    """Return the XDG data directory for the application."""
    base = Path.home() / ".local" / "share" / "spidey-sense"
    base.mkdir(parents=True, exist_ok=True)
    return base


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
}


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

    # Visual / UI
    anchor_corner: str = "top-left"
    anchor_offset_right: int = 160  # Ubuntu puts tray icons near the right end
    speech_bubble_duration: int = 5000
    power_reminder_timeout: int = 15000

    # Reminders
    reminder_interval: int = 600  # seconds between pending-task reminders

    # Derived paths (populated after class construction if needed)
    config_path: str = str(_config_dir() / "config.json")
    db_path: str = str(_db_dir() / "tasks.db")

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
                # Reset to default via a local mapping
                defaults = {
                    "spring_stiffness": 150.0,
                    "damping": 0.2,
                    "gravity": 9.81,
                    "max_angle": 0.7,
                    "character_size": 80,
                    "speech_bubble_duration": 5000,
                    "power_reminder_timeout": 15000,
                    "anchor_offset_right": 160,
                }
                setattr(self, field_name, defaults.get(field_name, 0))
                changed = True
        return not changed

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