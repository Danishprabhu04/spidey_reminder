#!/bin/bash
# Installation script for Spider-Man Hanging Reminder on Ubuntu 24.04 LTS
set -e

echo "=== Spider-Man Hanging Reminder Installation ==="

# -------------------------------------------------------
# 0. System libraries – Qt's XWayland (xcb) backend needs libxcb-cursor0
#    so Spidey can stay on top and be dragged freely on GNOME Wayland
# -------------------------------------------------------
echo "Installing system libraries (sudo)..."
sudo apt-get install -y libxcb-cursor0

# -------------------------------------------------------
# 1. Install Python dependencies
# -------------------------------------------------------
echo "Installing Python dependencies..."
python3 -m pip install --break-system-packages -r requirements.txt

# -------------------------------------------------------
# 2. Create XDG directories
# -------------------------------------------------------
echo "Creating data directories..."
mkdir -p ~/.local/share/spidey-sense
mkdir -p ~/.config/spidey-sense

# -------------------------------------------------------
# 3. (Optional) Install as a pip package so the console entry works
# -------------------------------------------------------
echo "Installing package..."
python3 -m pip install --break-system-packages -e .

# -------------------------------------------------------
# 4. Create the desktop autostart entry (starts Spidey at every login)
# -------------------------------------------------------
echo "Creating autostart entry..."
# Absolute path – at login ~/.local/bin is not always on PATH yet
APP_BIN="$(command -v hanging-reminder || echo "$HOME/.local/bin/hanging-reminder")"
ICON="$HOME/.local/share/spidey-sense/spidey_icon.png"
mkdir -p ~/.config/autostart
DESKTOP_FILE=~/.config/autostart/spidey-reminder.desktop
cat > "$DESKTOP_FILE" << DESKTOP
[Desktop Entry]
Type=Application
Exec=$APP_BIN
Icon=$ICON
Hidden=false
NoDisplay=false
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
Name=Spider-Man Hanging Reminder
Comment=A friendly desktop companion helping you remember tasks
Categories=Utility;
DESKTOP
chmod 644 "$DESKTOP_FILE"

# -------------------------------------------------------
# 5. Verify installation
# -------------------------------------------------------
echo ""
echo "=== Installation Summary ==="
echo "Application data: ~/.local/share/spidey-sense/"
echo "Configuration:    ~/.config/spidey-sense/"
echo "Autostart:        ~/.config/autostart/spidey-reminder.desktop"
echo ""
echo "To launch the application:"
echo "  hanging-reminder"
echo ""
echo "To run without installing (development):"
echo "  cd /path/to/spidey-sense && PYTHONPATH=src python3 -m hanging_reminder.app"
echo ""
echo "Enjoy your friendly neighborhood Spider-Man companion!"