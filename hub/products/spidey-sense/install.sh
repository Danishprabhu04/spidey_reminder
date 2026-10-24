#!/usr/bin/env bash
# Spidey Sense installer for Linux and macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/Danishprabhu04/spidey_reminder/main/hub/products/spidey-sense/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/Danishprabhu04/spidey_reminder/main/hub/products/spidey-sense/install.sh | bash -s -- --uninstall
#
# Linux: unpacks Spidey into ~/.local/opt/spidey-sense, adds an app-menu
#        entry, starts him at login and launches him.  No sudo needed.
# macOS: copies "Spidey Sense.app" into ~/Applications and opens it.
#
# Your missions and settings are kept on uninstall (add --purge to delete them).
set -euo pipefail

BASE="${SPIDEY_DOWNLOAD_BASE:-https://github.com/Danishprabhu04/spidey_reminder/releases/latest/download}"
APP_DIR="$HOME/.local/opt/spidey-sense"
BIN_LINK="$HOME/.local/bin/spidey-sense"
MENU_ENTRY="${XDG_DATA_HOME:-$HOME/.local/share}/applications/spidey-sense.desktop"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/spidey-reminder.desktop"
DATA_DIRS=("${XDG_CONFIG_HOME:-$HOME/.config}/spidey-sense" "${XDG_DATA_HOME:-$HOME/.local/share}/spidey-sense")
MAC_APP="$HOME/Applications/Spidey Sense.app"
tmp=""
trap '[ -n "$tmp" ] && rm -rf "$tmp"' EXIT

red=$'\033[31m'; green=$'\033[32m'; bold=$'\033[1m'; reset=$'\033[0m'
say()  { printf '%s🕷  %s%s\n' "$bold" "$*" "$reset"; }
ok()   { printf '%s✔%s %s\n' "$green" "$reset" "$*"; }
die()  { printf '%s✘ %s%s\n' "$red" "$*" "$reset" >&2; exit 1; }

download() {  # url dest
    if command -v curl >/dev/null 2>&1; then
        curl -fL --progress-bar -o "$2" "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -q --show-progress -O "$2" "$1"
    else
        die "Please install curl or wget first."
    fi
}

stop_running() {
    pkill -x SpideySense >/dev/null 2>&1 || true
    sleep 1
}

# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------

linux_install() {
    [ "$(uname -m)" = "x86_64" ] || die "Spidey currently ships for 64-bit Intel/AMD (x86_64) only."
    tmp="$(mktemp -d)"

    say "Downloading Spidey Sense…"
    download "$BASE/SpideySense-linux-x86_64.tar.gz" "$tmp/spidey.tar.gz"
    tar -xzf "$tmp/spidey.tar.gz" -C "$tmp"
    [ -x "$tmp/SpideySense/SpideySense" ] || die "The download looks broken – please try again."

    stop_running
    rm -rf "$APP_DIR"
    mkdir -p "$(dirname "$APP_DIR")" "$(dirname "$BIN_LINK")" "$(dirname "$MENU_ENTRY")" "$(dirname "$AUTOSTART")"
    mv "$tmp/SpideySense" "$APP_DIR"
    ln -sf "$APP_DIR/SpideySense" "$BIN_LINK"
    ok "Installed to $APP_DIR"

    sed -e "s|^Exec=.*|Exec=$APP_DIR/SpideySense|" -e "s|^Icon=.*|Icon=$APP_DIR/spidey-sense.png|" \
        "$APP_DIR/spidey-sense.desktop" > "$MENU_ENTRY"
    ok "Added Spidey Sense to your app menu"

    cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Exec=$APP_DIR/SpideySense
Icon=$APP_DIR/spidey-sense.png
Hidden=false
NoDisplay=false
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
Name=Spidey Sense
Comment=A friendly desktop companion helping you remember tasks
Categories=Utility;
EOF
    ok "Spidey will start when you log in (turn it off in Settings)"

    if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        (cd "$HOME" && setsid nohup "$APP_DIR/SpideySense" >/dev/null 2>&1 &)
        ok "Spidey is swinging in – look at the top of your screen!"
    fi
    echo
    say "Tap Spidey to see your missions, double-tap to add one."
    echo "   Web dashboard: right-click his tray icon → Open web dashboard"
    echo "   Uninstall:     curl -fsSL <this script's URL> | bash -s -- --uninstall"
}

linux_uninstall() {
    stop_running
    rm -rf "$APP_DIR"
    rm -f "$BIN_LINK" "$MENU_ENTRY"
    if [ -f "$AUTOSTART" ] && grep -q "spidey-sense/SpideySense" "$AUTOSTART"; then
        rm -f "$AUTOSTART"
    fi
    ok "Spidey Sense removed"
}

# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

mac_install() {
    local mount
    tmp="$(mktemp -d)"
    say "Downloading Spidey Sense…"
    download "$BASE/SpideySense-macOS.dmg" "$tmp/spidey.dmg"
    mount="$(hdiutil attach -nobrowse -readonly "$tmp/spidey.dmg" | awk -F'\t' '/\/Volumes\//{print $NF}' | tail -1)"
    [ -d "$mount/Spidey Sense.app" ] || die "The download looks broken – please try again."
    stop_running
    mkdir -p "$HOME/Applications"
    rm -rf "$MAC_APP"
    cp -R "$mount/Spidey Sense.app" "$MAC_APP"
    hdiutil detach -quiet "$mount" || true
    xattr -dr com.apple.quarantine "$MAC_APP" 2>/dev/null || true
    ok "Installed to $MAC_APP"
    open "$MAC_APP"
    ok "Spidey is swinging in – look at the top of your screen!"
}

mac_uninstall() {
    stop_running
    launchctl remove com.spideysense.app >/dev/null 2>&1 || true
    rm -rf "$MAC_APP"
    rm -f "$HOME/Library/LaunchAgents/com.spideysense.app.plist"
    ok "Spidey Sense removed"
}

# ---------------------------------------------------------------------------

action="install"; purge=0
for arg in "$@"; do
    case "$arg" in
        --uninstall) action="uninstall" ;;
        --purge) action="uninstall"; purge=1 ;;
        -h|--help) sed -n '2,12p' "$0" 2>/dev/null || true; exit 0 ;;
        *) die "Unknown option: $arg" ;;
    esac
done

case "$(uname -s)" in
    Linux)  os=linux ;;
    Darwin) os=mac ;;
    *) die "This installer is for Linux and macOS. On Windows, download the installer from the website." ;;
esac

"${os}_${action}"

if [ "$purge" = 1 ]; then
    if [ "$os" = mac ]; then
        rm -rf "$HOME/Library/Application Support/SpideySense"
    else
        rm -rf "${DATA_DIRS[@]}"
    fi
    ok "Deleted your missions and settings"
fi
