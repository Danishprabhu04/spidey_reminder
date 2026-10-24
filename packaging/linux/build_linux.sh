#!/usr/bin/env bash
# Package the PyInstaller output for Linux:
#   dist/SpideySense-linux-x86_64.tar.gz   (used by the one-line installer)
#   dist/SpideySense-x86_64.AppImage       (double-click download; skipped with --no-appimage)
#
#   python packaging/make_icons.py
#   pyinstaller packaging/spidey.spec --noconfirm
#   packaging/linux/build_linux.sh [--no-appimage]
#
# The AppImage step downloads appimagetool into build/ on first use.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUNDLE="$ROOT/dist/SpideySense"
TARBALL="$ROOT/dist/SpideySense-linux-x86_64.tar.gz"
APPDIR="$ROOT/build/AppDir"
TOOL="$ROOT/build/appimagetool-x86_64.AppImage"
APPIMAGE="$ROOT/dist/SpideySense-x86_64.AppImage"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"

[ -x "$BUNDLE/SpideySense" ] || { echo "Run PyInstaller first ($BUNDLE missing)"; exit 1; }

# ---- tarball: SpideySense/ + icon + desktop entry --------------------------
STAGE="$ROOT/build/linux-stage/SpideySense"
rm -rf "$ROOT/build/linux-stage"
mkdir -p "$STAGE"
cp -a "$BUNDLE/." "$STAGE/"
cp "$ROOT/build/icons/spidey-256.png" "$STAGE/spidey-sense.png"
cp "$ROOT/packaging/linux/spidey-sense.desktop" "$STAGE/"
tar -C "$ROOT/build/linux-stage" -czf "$TARBALL" SpideySense
echo "Built $TARBALL ($(du -h "$TARBALL" | cut -f1))"

[ "${1:-}" = "--no-appimage" ] && exit 0

# ---- AppImage --------------------------------------------------------------
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$BUNDLE" "$APPDIR/usr/lib/spidey-sense"
cp "$ROOT/packaging/linux/spidey-sense.desktop" "$APPDIR/spidey-sense.desktop"
cp "$ROOT/packaging/linux/spidey-sense.desktop" "$APPDIR/usr/share/applications/"
cp "$ROOT/build/icons/spidey-256.png" "$APPDIR/spidey-sense.png"
cp "$ROOT/build/icons/spidey-256.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/spidey-sense.png"
ln -s spidey-sense.png "$APPDIR/.DirIcon"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/spidey-sense/SpideySense" "$@"
RUN
chmod +x "$APPDIR/AppRun"

if [ ! -x "$TOOL" ]; then
    echo "Downloading appimagetool..."
    curl -fsSL -o "$TOOL" "$TOOL_URL"
    chmod +x "$TOOL"
fi
# Works without FUSE (CI containers)
APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 "$TOOL" --no-appstream "$APPDIR" "$APPIMAGE"
echo "Built $APPIMAGE ($(du -h "$APPIMAGE" | cut -f1))"
