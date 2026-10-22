"""Structured logging setup for Spider-Man Hanging Reminder.

Provides a module-level ``logger`` instance that writes JSON-formatted
log entries to a rotating file at ``~/.local/share/spidey-sense/log.txt``.

Each log entry includes:
  - timestamp (ISO-8601)
  - log level
  - module name
  - message
  - optional context dictionary

The logger is pre-configured at ``INFO`` level.  Developers should use
``logger.info(...)`` or ``logger.warning(...)`` etc.  Debug-level output
can be enabled by setting the ``SPIDEY_SENSE_DEBUG`` environment variable
to any truthy value.
"""

from __future__ import annotations

import os
import sys
import json
import time
from logging import (
    DEBUG,
    INFO,
    WARNING,
    ERROR,
    CRITICAL,
    Filterer,
    Formatter,
    Handler,
    StreamHandler,
    Logger,
    getLogger,
)
from pathlib import Path
from typing import Dict, Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_serialize(value: Any) -> str:
    """Serialize a value to a JSON-safe string representation."""
    if isinstance(value, (str, int, float, bool)):
        return json.dumps(value)
    if value is None:
        return "null"
    # Fallback – let json.dumps raise or coerce
    return json.dumps(str(value))


def _context_to_str(context: Dict[str, Any]) -> str:
    """Convert a context dict to a compact JSON string for logging."""
    if not context:
        return "{}"
    # Filter out non-serialisable objects
    serialisable = {
        k: v for k, v in context.items()
        if isinstance(v, (str, int, float, bool)) or v is None
    }
    return json.dumps(serialisable)


# ---------------------------------------------------------------------------
# rotating file handler (simple implementation – no external dependency)
# ---------------------------------------------------------------------------

class RotatingFileHandler(Handler):
    """A simple rotating text file handler.

    Rotates when the file exceeds ~1 MB, keeping up to 3 backup files.
    File name format: ``log.txt``, ``log.txt.1``, ``log.txt.2``, etc.
    """

    def __init__(self, filename: str, max_bytes: int = 1_000_000, backup_count: int = 3) -> None:
        super().__init__()
        self._filename = filename
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._path = Path(filename)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _rotate(self) -> None:
        """Shift existing backups and truncate the current file."""
        # Remove oldest if we have too many
        if self._backup_count > 0:
            oldest = self._path.with_suffix(f".{self._backup_count}")
            oldest.unlink(missing_ok=True)

            # Shift numerics down
            for i in range(self._backup_count - 1, 0, -1):
                src = self._path.with_suffix(f".{i}")
                dst = self._path.with_suffix(f".{i + 1}")
                if src.exists():
                    src.rename(dst)

        # Truncate current file
        self._path.write_text("")

    # ------------------------------------------------------------------
    # Handler interface
    # ------------------------------------------------------------------

    def emit(self, record: "LogRecord") -> None:  # pragma: no cover
        """Write *record* to the rotating file."""
        try:
            # Ensure directory exists
            self._path.parent.mkdir(parents=True, exist_ok=True)

            # Rotate if we crossed the size threshold
            if self._path.exists() and self._path.stat().st_size > self._max_bytes:
                self._rotate()

            # Build JSON log line
            entry: Dict[str, Any] = {
                "timestamp": time.time(),
                "levelno": record.levelno,
                "levelname": record.levelname,
                "module": record.module,
                "message": self._format_message(record),
            }

            # Add user context if present
            if hasattr(record, "context") and record.context:
                entry["context"] = _context_to_str(record.context)

            line = json.dumps(entry, ensure_ascii=False)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            # Last-resort: stderr so we don't silently swallow errors
            print(f"[Log emit failed] {record.message}", file=sys.stderr)

    def _format_message(self, record: "LogRecord") -> str:
        """Format the record's message attribute."""
        return record.getMessage()


# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------

def _build_logger() -> Logger:
    """Construct and configure the module-level logger."""
    logger = getLogger("spidey_sense")
    logger.setLevel(INFO)

    # Avoid adding the handler twice if the logger already has handlers
    if logger.handlers:
        return logger

    # Console handler (stderr) – human-readable
    console_handler = StreamHandler(sys.stderr)
    console_formatter = Formatter("%(levelname)s: %(message)s [%(module)s]")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)  # type: ignore[attr-call]

    # File handler – structured JSON
    log_path = str(Path.home() / ".local" / "share" / "spidey-sense" / "log.txt")
    file_handler = RotatingFileHandler(log_path, max_bytes=500_000, backup_count=2)
    file_formatter = Formatter("%(message)s")  # we already emit JSON
    file_handler.setFormatter(file_formatter)  # type: ignore[attr-call]
    logger.addHandler(file_handler)  # type: ignore[attr-call]

    # If debug env var is set, add a stderr debug-level handler
    if os.getenv("SPIDEY_SENSE_DEBUG"):
        debug_handler = sys.stderr
        debug_handler.setLevel(DEBUG)
        logger.setLevel(DEBUG)

    return logger


logger: Logger = _build_logger()

# Convenience shorthand
debug = logger.debug
info = logger.info
warning = logger.warning
error = logger.error
critical = logger.critical