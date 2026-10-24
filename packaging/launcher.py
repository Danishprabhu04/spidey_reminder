"""Entry point for the PyInstaller builds."""

import sys

from hanging_reminder.app import main

if __name__ == "__main__":
    sys.exit(main())
