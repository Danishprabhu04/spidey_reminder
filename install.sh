#!/bin/bash
# Installation script for Spider-Man Hanging Reminder on Ubuntu 24.04 LTS
set -e

echo "=== Spider-Man Hanging Reminder Installation ==="

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
# 4. Create the desktop autostart entry
# -------------------------------------------------------
echo "Creating autostart entry..."
DESKTOP_FILE=~/.config/autostart/spidey-reminder.desktop
cat > "$DESKTOP_FILE" << 'DESKTOP'
[Desktop Entry]
Type=Application
Exec=hanging-reminder
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Spider-Man Hanging Reminder
Comment=A friendly desktop companion helping you remember tasks
DESKPOL
chmod +x "$DESKTOP_FILE"

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