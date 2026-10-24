# Spidey Sense

A friendly desktop companion for **Windows, Linux and macOS**: a tiny Spidey hangs from the top of your screen on an elastic web, keeps your to-do list ("missions") and reminds you at the right moment.

**App hub & downloads:** the [`hub/`](hub/) folder is a static website (your app hub, with Spidey's page at `hub/products/spidey-sense/`). Installers are attached to this repo's [Releases](https://github.com/Danishprabhu04/spidey_reminder/releases/latest).

## Overview

Spidey hangs from a transparent web attached to your screen's top edge. He swings naturally with physics, reacts to your mouse, and shows you your unfinished missions when you tap him. A local web dashboard lets you manage everything from the browser, and he reminds you of pending tasks when they're due – and before your computer goes to sleep or shuts down (Linux).

## Features

### Animation & Physics
- **Idle hanging**: Subtle sway and breathing-like motion keeps the character alive without distraction
- **Elastic drag**: Grab Spider-Man anywhere on screen – his web stretches like a bungee
- **Free swinging**: On release he flings, bounces and swings with no angle limit (he can even flip), with a front/back depth wobble
- **Fixed web anchor**: His web hangs from one spot on the top bar, under his tray icon – after a throw he springs back up to it. Drop him right under the tray icon to move the pin (remembered across restarts)
- **Tap for missions**: A single tap pops a speech bubble listing your pending tasks, with a link to the full mission list
- **Click-through**: Only Spidey and his web catch the mouse – the rest of the screen works as usual

### Personality
- **Moods**: His eyes show how things are going – happy when you're clear, worried about overdue tasks, sleepy at night or when you're away, dizzy after a hard spin, proud after a win
- **Eyes follow your cursor**, and they widen in surprise when the pointer comes right up to him
- **Celebrations**: Completing a task earns a backflip and web confetti; clearing everything throws a bigger party
- **Wanders on his own**: Every 5–12 minutes he swings along the top bar, yo-yos on his web or looks around – then returns home

### Task Management
- **Quick add**: Double-tap Spidey, press **Super+Shift+M** anywhere, or use the tray menu – type naturally: `Call mom tomorrow 5pm !high`, `Pay rent fri`, `Backup in 2 hours`
- **Due dates & priority**: Parsed from what you type (with a live preview), editable later – double-click a task to edit, right-click for Edit / Focus / Snooze / Delete
- **Overdue glow**: Overdue tasks glow red, ones due within 2 hours turn amber
- **Streaks & stats**: 📊 in the mission panel shows your streak, tasks done today/this week, focus minutes and a 7-day chart
- **Persistence**: Everything is stored in SQLite and restored on restart

### Smart Reminders
- **Due-time alerts**: When a task is due Spidey drops down on his web, wiggles and shows it with **Done** / **Snooze** buttons, plus a desktop notification with the same actions
- **Snooze**: 10 minutes, 1 hour or tomorrow 9:00 (right-click the alert bubble, or from the mission list)
- **Idle-aware**: Reminders wait while you're away, the screen is locked or an (X11) app is fullscreen, then arrive together when you're back
- **Morning & end-of-day briefs**: Today's missions when you start the day; a wrap-up at your end-of-day time
- **Periodic nudge**: "N missions pending" every so often (paused during focus sessions)

### Focus Timer
- **Pomodoro**: Right-click a task → *Focus on this* (or tray → *Start focus session*); a countdown ring appears on Spidey's chest and his eyes look determined
- **Breaks**: When the session ends he celebrates and starts your break, then calls you back; focus minutes count toward your stats

### Desktop Experience
- **Frameless transparent overlay**: No visible rectangle around the character
- **Always-on-top** via XWayland on GNOME Wayland (needs `libxcb-cursor0`)
- **Multi-monitor**: Drag him onto another screen and he hangs from that screen's top bar; he remembers which screen
- **Do not disturb**: Tray → *Do not disturb* hides and silences him for 1 hour or until tomorrow
- **Sound effects**: Optional thwip, boing, cheer and alert sounds (generated on first run)
- **Settings window**: Tray → *Settings…* for size, web springiness, motion, reminders, focus lengths, sounds, start at login and the quick-add shortcut

### Power Event Reminders
- **Before sleep/shutdown**: Spidey lists your pending tasks while holding the action back for up to 15 seconds (configurable)
- **Tap to continue**: Tapping the bubble lets the system go ahead immediately; with no pending tasks there is no delay

### Web Dashboard
- **http://127.0.0.1:47823** while Spidey runs (tray → *Open web dashboard*, or `hanging-reminder --dashboard`)
- Add (with the same natural-language parser), edit, snooze, complete + undo, delete; streak/week stats; focus timer – changes show up on Spidey instantly
- Private by design: listens on 127.0.0.1 only, checks the `Host` header (no DNS rebinding) and requires a per-launch token that only the served page knows

### Platforms
| | Linux (GNOME) | Windows 10/11 | macOS (beta) |
|---|---|---|---|
| Start at login | XDG autostart | `HKCU\…\Run` | LaunchAgent |
| Quick-add shortcut | GNOME custom shortcut (Super+Shift+M) | `RegisterHotKey` (Win+Alt+M) | – |
| Away / fullscreen detection | Mutter idle + screen lock + X11 fullscreen | `GetLastInputInfo` + `SHQueryUserNotificationState` | idle time |
| Notifications | freedesktop, with Done/Snooze buttons | tray balloon | tray balloon |
| Before-sleep reminder | logind delay inhibitor | at sign-out/shutdown only | – |
| Data | `~/.config/spidey-sense`, `~/.local/share/spidey-sense` | `%APPDATA%\SpideySense` | `~/Library/Application Support/SpideySense` |

No admin/root rights are needed anywhere.

## Installation

### For users (friends)
Send them the hub – each app's download button picks the right installer:

- **Windows:** `SpideySense-Setup.exe` (per-user, no admin) – or `irm https://raw.githubusercontent.com/Danishprabhu04/spidey_reminder/main/hub/products/spidey-sense/install.ps1 | iex`
- **Linux:** `curl -fsSL https://raw.githubusercontent.com/Danishprabhu04/spidey_reminder/main/hub/products/spidey-sense/install.sh | bash` (installs to `~/.local/opt/spidey-sense`, adds a menu entry + autostart; append `-s -- --uninstall` to `bash` to remove it) – or the AppImage
- **macOS:** `SpideySense-macOS.dmg` (unsigned: right-click → Open the first time)

### For development

```bash
./install.sh                      # Ubuntu: system libs, pip install -e ., autostart, hotkey
# or by hand:
python3 -m pip install -e ".[dev]"
python3 -m hanging_reminder.app   # or: hanging-reminder / spidey-sense
```

## The app hub (`hub/`)

A plain HTML/CSS/JS site – no build step – so it deploys anywhere (GitHub Pages, Netlify, Vercel, Cloudflare Pages: just point it at the `hub/` folder).

**GitHub Pages (built in):** `.github/workflows/hub.yml` publishes `hub/` on every change. Turn it on once in the repo's *Settings → Pages → Source: GitHub Actions*, then re-run the *publish-hub* workflow (Actions tab). The hub appears at https://danishprabhu04.github.io/spidey_reminder/

```
hub/index.html                 hub home page: hero, app cards, spotlight, about
hub/assets/catalog.js          ← the app list: edit this to add an app or change links/versions
hub/assets/hub.css, hub.js     hub styles + card rendering and OS-aware download buttons
hub/products/spidey-sense/     Spidey's own page (+ install.sh / install.ps1)
```

To add another app: add an entry to `products` in `catalog.js` (copy the Spidey one) and, if you like, a page under `hub/products/<id>/`.
Preview locally: `cd hub && python3 -m http.server` → http://localhost:8000

## Releasing installers

`.github/workflows/release.yml` runs the tests on Windows/Linux/macOS, builds with PyInstaller, boots every build with `--self-test`, packages them (Inno Setup `.exe`, `.tar.gz` + AppImage, `.dmg`) and – on a version tag – attaches them to a GitHub Release of this repo. No secrets needed.

```bash
# bump __version__ in src/hanging_reminder/__init__.py and "version" in hub/assets/catalog.js, commit, then
git tag v1.0.0 && git push origin v1.0.0
```
Until the first release exists, the download buttons lead to a 404.

Building locally (Linux):
```bash
python3 -m venv --system-site-packages build/venv
build/venv/bin/python -s -m pip install PySide6-Essentials pyinstaller pillow
build/venv/bin/python -s packaging/make_icons.py
build/venv/bin/python -s -m PyInstaller packaging/spidey.spec --noconfirm
dist/SpideySense/SpideySense --self-test
packaging/linux/build_linux.sh            # --no-appimage to skip the AppImage
```
Set `SPIDEY_DOWNLOAD_BASE` to test the install scripts against local files.

## Running

```bash
# From the project directory
PYTHONPATH=src python3 -m hanging_reminder.app

# Or using the console script (if installed)
hanging-reminder                 # start (or show the running Spidey)
hanging-reminder --quick-add     # open the quick-add box
hanging-reminder --dashboard     # open the web dashboard
hanging-reminder --self-test     # boot offscreen for a few seconds and exit
hanging-reminder --version
```

## Repository layout

```
src/hanging_reminder/   the app (Qt UI, physics, tasks, reminders, dashboard/)
tests/                  pytest suite (isolated from your real profile by conftest.py)
packaging/              PyInstaller spec, icon generator, Windows/Linux/macOS installer scripts
hub/                    the app hub website (plain HTML/CSS/JS) incl. Spidey's page and install scripts
.github/workflows/      build-and-release pipeline
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