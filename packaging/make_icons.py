"""Render Spidey into build/icons/ as spidey.png, spidey.ico and spidey.icns.

Uses the same painter code as the tray icon, so the installers, the
website and the app all share one character.  Needs Pillow.

    python packaging/make_icons.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    from PIL import Image
    from PySide6.QtWidgets import QApplication

    from hanging_reminder.ui.tray_icon import build_spidey_icon_pixmap

    app = QApplication.instance() or QApplication([])  # noqa: F841 – needed for painting
    out = ROOT / "build" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    png = out / "spidey.png"
    build_spidey_icon_pixmap(1024).save(str(png), "PNG")

    image = Image.open(png).convert("RGBA")
    image.save(out / "spidey.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    image.save(out / "spidey.icns")
    for size in (256, 512):
        image.resize((size, size), Image.LANCZOS).save(out / f"spidey-{size}.png")
    print(f"Icons written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
