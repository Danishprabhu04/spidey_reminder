# Spider-Man Hanging Reminder

A desktop companion for Ubuntu 24.04 LTS that helps you remember unfinished tasks while you work.

## Overview

Spider-Man hangs from a transparent web attached to your screen's top edge. He swings naturally with physics, reacts to your mouse, and shows you a task panel with your unfinished missions. He also reminds you of pending tasks before your computer goes to sleep or shuts down.

## Features

### Animation & Physics
- **Idle hanging**: Subtle sway and breathing-like motion keeps the character alive without distraction
- **Hover interaction**: Small head tilt when the pointer approaches
- **Mouse press & grab**: Drag Spider-Man around the desktop with offset preservation
- **Elastic release & swinging**: Natural pendulum dynamics with spring forces, damping, and gravity
- **Smooth settling**: Gradual transition from swinging back to idle pose
- **Double-click handling**: Correctly prevents duplicate interactions

### Task Management
- **Create tasks**: Type a task and press Enter
- **Complete tasks**: Click checkboxes – saves to SQLite immediately
- **Edit/delete tasks**: Manage your mission list
- **Priority levels**: High / Normal / Low with color coding
- **Due dates**: Optional deadlines with overdue detection
- **Persistence**: All tasks saved to SQLite, restored on restart
- **Clear completed**: One-click removal of finished tasks

### Desktop Experience
- **Frameless transparent window**: No visible rectangle around the character
- **Always-on-top**: Stays above other windows (X11 with compositor support)
- **High-DPI aware**: Looks sharp on Retina and ordinary displays
- **Window positioning**: Anchored to the top-left corner, moves with screen edges
- **Low resource usage**: Fixed timestep physics at 120 Hz, minimal CPU at idle

### Power Event Reminders
- **Before sleep/shutdown**: Shows a dialog listing unfinished tasks
- **Cancel and stay**: Delays the power action (if the system permits)
- **Continue anyway**: Allows the operation to proceed
- **Timeout**: Automatically continues after 15 seconds if no response

### Integration
- **Ubuntu 24.04 GNOME**: Native look and feel
- **D-Bus logind**: System sleep/shutdown integration
- **Desktop autostart**: Launch at login via .desktop file
- **User-level configuration**: No root required

## Installation

### Using the installation script

```bash
# Download or cd to the project directory
cd spidey-sense
chmod +x install.sh
./install.sh
```

### Manual installation

```bash
# 1. Install dependencies
python3 -m pip install --break-system-packages PySide6 dbus-python pytest pytest-qt

# 2. Create data directories
mkdir -p ~/.local/share/spidey-sense
mkdir -p ~/.config/spidey-sense

# 3. Install the package (optional, for console entry)
python3 -m pip install --break-system-packages -e .

# 4. Create the autostart entry
cat > ~/.config/autostart/spidey-reminder.desktop << 'DESKTOP'
[Desktop Entry]
Type=Application
Exec=hanging-reminder
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Spider-Man Hanging Reminder
Comment=A friendly desktop companion helping you remember tasks
DESKTOP

# 4. Launch the application
hanging-reminder
```

## Running

```bash
# From the project directory
python3 -m hanging_reminder.app

# Or using the console script (if installed)
hanging-reminder
```

## Project Structure

```
spidey_sense/
├── main.py                          # Entry point
├── requirements.txt                 # Dependencies
├── pyproject.toml                   # Package configuration
├── install.sh                       # Installation script
├── README.md                        # This file
├── assets/                          # Placeholder artwork
├── tests/                           # Unit tests
│   ├── test_physics.py
│   ├── test_tasks.py
│   ├── test_interactions.py
│   └── test_power_manager.py
└── src/
    └── hanging_reminder/
        ├── __init__.py
        ├── app.py                   # Application controller
        ├── config.py                # Configuration management
        ├── logging_config.py        # Structured logging
        ├── physics/
        │   ├── __init__.py
        │   ├── spring.py            # Hooke's law spring model
        │   ├── pendulum.py          # Pendulum dynamics
        │   └── simulation.py        # Fixed-timestep engine
        ├── rendering/
        │   ├── __init__.py
        │   ├── character.py         # Programmatic QPainter rendering
        │   ├── web.py               # Bézier curve web renderer
        │   └── speech_bubble.py     # Rounded bubble with pointer
        ├── ui/
        │   ├── __init__.py
        │   ├── companion_window.py  # Frameless transparent QWidget
        │   ├── task_panel.py        # Modern dark task UI
        │   ├── power_dialog.py      # Sleep/shutdown reminder
        │   └── settings_dialog.py    # Preferences UI
        ├── tasks/
        │   ├── __init__.py
        │   ├── models.py            # Task data model
        │   └── repository.py        # SQLite abstraction
        └── system/
            ├── __init__.py
            ├── power_manager.py     # D-Bus logind integration
            └── desktop_integration.py # Wayland/X11 detection
```

## Configuration

Configuration is stored at ``~/.config/spidey-sense/config.json``.

Default values (can be edited in the file or via a future settings dialog):

| Setting | Default | Description |
|---------|---------|-------------|
| `spring_stiffness` | `150.0` | Hooke's law stiffness – higher = snappier |
| `damping` | `0.2` | Viscous damping ratio (0 = undamped) |
| `gravity` | `9.81` | Effective gravity for pendulum |
| `max_angle` | `0.7` (~40°) | Maximum swing angle clamp |
| `character_size` | `80` | Nominal pixel size (square) |
| `anchor_corner` | `"top-left"` | Web attachment corner |
| `speech_bubble_duration` | `5000` | How long a bubble stays visible (ms) |
| `power_reminder_timeout` | `15000` | Power-event reminder timeout (ms) |
| `start_at_login` | `true` | Create autostart entry |
| `sound_effects` | `false` | UI sounds on/off |
| `reduced_motion` | `false` | Suppress idle animation |

To change a setting, edit the JSON file directly or modify the defaults in `src/hanging_reminder/config.py`.

## Recent Updates (v0.1.1)

### Taskbar Integration
- Removed `Qt.Tool` window flag so Spider-Man now appears in the taskbar/navbar while keeping always-on-top behavior
- Window flags adjusted in `companion_window.py` for taskbar-visible persistent top-left positioning
- Desktop autostart entry created via `install.sh` and `~/.config/autostart/spidey-reminder.desktop`

### Persistent Default State
- Character position and physics state now persist across restarts
- Default state: character starts at top-left corner (20, 20) with idle hanging motion
- Configuration saved to `~/.config/spidey-sense/config.json`

### Dependency Fixes
- NumPy downgraded from 2.4.4 to 1.26.4 for PySide6 6.12.0 compatibility
- PySide6 updated to 6.12.0 with all compatibility fixes
- Multiple import fixes: `QtGlobal`, `pyqtSignal`, `HighQualityAntialiasing`, `QStandardItem` → `QWidget`

### Known Limitations

#### Wayland transparency
Full RGBA window transparency with compositor support varies under Wayland.  On Wayland, the window may appear with a solid background or reduced compositing features.  The application detects the session type and degrades gracefully.

#### Sleep/cancellation guarantee
A normal user application cannot guarantee interception of every shutdown or sleep path.  Physical power-button holds, forced shutdowns (`systemctl poweroff`), compositor-specific behavior, and some desktop shortcuts may bypass the application.  The D-Bus logind inhibitor mechanism works when the session is managed by systemd (typical Ubuntu 24.04 GNOME), but:

- Inhibitors can be overridden by root or the system bus
- Some desktop environments bypass logind entirely
- A physical power-button hold will always force shutdown

The application documents these limitations and provides a safe fallback (reminder dialog without delay).

#### Multi-monitor
The application positions itself relative to the primary monitor.  On multi-monitor setups, moving the character to a secondary monitor may require manual repositioning.

#### 3D Animation
The current implementation uses 2D QPainter rendering.  A genuine 3D Spider-Man simulation would require Qt Quick / QML or PySide6 QtOpenGL with 3D models and shaders.  This is a planned future enhancement.

### No root required
All operations use user-level D-Bus.  The application does not require root privileges and will not ask for them.

## Testing

Unit tests are provided in the `tests/` directory.  To run them:

```bash
python3 -m pytest tests/ -v
```

See the `tests/` directory for test specifications.  Note: some tests require a QGuiApplication instance and may need a display server.

## Troubleshooting

### Window won't appear / is invisible
- Ensure PySide6 is correctly installed: `pip install PySide6`
- Check that the display server is running (`echo $DISPLAY`)
- On Wayland, transparency may not work fully – try X11 session

### Character doesn't swing after dragging
- Make sure you're releasing the left mouse button outside the character area
- The swing amplitude depends on the drag velocity

### Tasks not saving
- Check that the data directory is writable: `~/.local/share/spidey-sense/`
- Ensure no other process is using the SQLite database

### Sleep reminder doesn't appear
- Verify you're running on a systemd-managed session (Ubuntu 24.04 GNOME typically is)
- The reminder may be skipped if a logind inhibitor already held by another process

### High CPU usage
- The application uses a fixed 120 Hz timestep – should be ~8ms per frame on ordinary hardware
- If CPU is high, check for other resource-intensive applications
- The `reduced_motion` config option reduces animation complexity

## License

This project is open source under the MIT License.