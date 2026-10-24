#!/usr/bin/env bash
# Build dist/SpideySense-macOS.dmg from "dist/Spidey Sense.app".
#
#   python packaging/make_icons.py
#   pyinstaller packaging/spidey.spec --noconfirm
#   packaging/macos/build_dmg.sh
#
# The app is not signed/notarized: on first open, right-click it -> Open.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$ROOT/dist/Spidey Sense.app"
STAGE="$ROOT/build/dmg"
OUT="$ROOT/dist/SpideySense-macOS.dmg"

[ -d "$APP" ] || { echo "Run PyInstaller first ($APP missing)"; exit 1; }

# Ad-hoc signature so Apple Silicon will run it at all
codesign --force --deep --sign - "$APP"

rm -rf "$STAGE" "$OUT"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Spidey Sense" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
echo "Built $OUT ($(du -h "$OUT" | cut -f1))"
