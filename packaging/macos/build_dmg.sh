#!/usr/bin/env bash
# Build dist/SpideySense-macOS.dmg from "dist/Spidey Sense.app".
#
#   python packaging/make_icons.py
#   pyinstaller packaging/spidey.spec --noconfirm
#   packaging/macos/build_dmg.sh
#
# The app is not signed/notarized: on first open, right-click it -> Open.
set -euo pipefail
trap 'echo "::error::build_dmg.sh failed at line $LINENO: $BASH_COMMAND"' ERR

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$ROOT/dist/Spidey Sense.app"
STAGE="$ROOT/build/dmg"
OUT="$ROOT/dist/SpideySense-macOS.dmg"

[ -d "$APP" ] || { echo "Run PyInstaller first ($APP missing)"; exit 1; }

# PyInstaller already ad-hoc signs every binary; re-sign the whole bundle so
# Apple Silicon accepts it.  Not fatal: an unsigned build still opens via
# right-click -> Open.
if ! out=$(codesign --force --deep --sign - "$APP" 2>&1); then
    echo "::warning::codesign failed: ${out//$'\n'/%0A}"
fi

rm -rf "$STAGE" "$OUT"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

# hdiutil fails now and then on CI runners ("Resource busy") - retry
for attempt in 1 2 3 4 5; do
    if out=$(hdiutil create -volname "Spidey Sense" -srcfolder "$STAGE" -ov -format UDZO "$OUT" 2>&1); then
        break
    fi
    echo "::warning::hdiutil attempt $attempt failed: ${out//$'\n'/%0A}"
    [ "$attempt" = 5 ] && { echo "::error::hdiutil create failed: ${out//$'\n'/%0A}"; exit 1; }
    sleep $((attempt * 5))
done
echo "Built $OUT ($(du -h "$OUT" | cut -f1))"
