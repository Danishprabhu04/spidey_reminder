# PyInstaller spec for Spidey Sense – run from the repository root:
#     pyinstaller packaging/spidey.spec --noconfirm
# (after `python packaging/make_icons.py`).  Produces dist/SpideySense/
# (Windows, Linux) or dist/Spidey Sense.app (macOS).
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "src"))
from hanging_reminder import __version__  # noqa: E402

ICONS = ROOT / "build" / "icons"
icon = {"win32": "spidey.ico", "darwin": "spidey.icns"}.get(sys.platform, "spidey.png")

# Qt modules Spidey never uses – keeps the download small
EXCLUDES = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtUiTools",
    "PySide6.QtHelp", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtMultimedia", "PySide6.QtOpenGLWidgets",
    "PySide6.QtConcurrent", "PySide6.QtXml", "PySide6.QtSvgWidgets",
    "tkinter", "unittest", "pydoc", "pytest",
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(ROOT / "src" / "hanging_reminder" / "dashboard" / "static"),
            "hanging_reminder/dashboard/static")],
    hiddenimports=["hanging_reminder.system.win32"] if sys.platform == "win32" else
                  ["dbus.mainloop.glib"] if sys.platform.startswith("linux") else [],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SpideySense",
    console=False,
    icon=str(ICONS / icon),
)
coll = COLLECT(exe, a.binaries, a.datas, name="SpideySense", strip=False, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Spidey Sense.app",
        icon=str(ICONS / "spidey.icns"),
        bundle_identifier="com.spideysense.app",
        info_plist={
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSUIElement": True,  # lives in the menu bar, no Dock icon
            "NSHighResolutionCapable": True,
        },
    )
