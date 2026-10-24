"""Settings window – opened from the tray menu ("Settings…").

Edits :class:`AppConfig` in tabs (General, Motion, Reminders, Focus,
Sounds).  Saving writes the config file and start-at-login, then emits
:attr:`SettingsDialog.saved` so the running app can apply the changes live
(including the quick-add shortcut).  Rows for features the current
operating system can't do are left out.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from hanging_reminder import APP_NAME, __version__, paths
from hanging_reminder.config import AppConfig
from hanging_reminder.system import autostart
from hanging_reminder.system.hotkey import HotkeyManager, default_binding


STYLE = """
QDialog { background: #1e222c; }
QLabel, QCheckBox { color: #dcdcdc; font-size: 12px; }
QLabel#hint { color: #8a8f99; font-size: 11px; }
QTabWidget::pane { border: 1px solid #3a3f4b; border-radius: 8px; top: -1px; }
QTabBar::tab {
    background: #2a2f3a; color: #c8c8c8; padding: 6px 12px;
    border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px;
}
QTabBar::tab:selected { background: #dc3232; color: white; }
QSpinBox, QDoubleSpinBox, QTimeEdit, QLineEdit {
    background: #2a2f3a; color: #e6e6e6; border: 1px solid #4a4f5b;
    border-radius: 4px; padding: 3px 6px; min-width: 90px;
}
QPushButton {
    background: #dc3232; color: white; border: none; border-radius: 5px;
    padding: 6px 14px; font-weight: bold;
}
QPushButton:hover { background: #e6821e; }
QPushButton#secondary { background: #3a3f4b; }
QPushButton#secondary:hover { background: #4a5060; }
QLabel a { color: #ff6b6b; }
"""

# Web springiness slider (1–10) <-> ElasticRope stiffness
STIFFNESS_MIN = 30.0
STIFFNESS_STEP = 15.0


def stiffness_to_slider(stiffness: float) -> int:
    return max(1, min(10, round((stiffness - STIFFNESS_MIN) / STIFFNESS_STEP) + 1))


def slider_to_stiffness(value: int) -> float:
    return STIFFNESS_MIN + (value - 1) * STIFFNESS_STEP


class SettingsDialog(QDialog):
    """Dark tabbed settings editor for :class:`AppConfig`."""

    saved = Signal()

    def __init__(self, config: AppConfig, sounds=None, parent: QWidget | None = None,
                 dashboard_url: str = "") -> None:
        super().__init__(parent)
        self._config = config
        self._sounds = sounds
        self._dashboard_url = dashboard_url
        self.setWindowTitle("Spidey Settings")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(420)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._motion_tab(), "Motion")
        tabs.addTab(self._reminders_tab(), "Reminders")
        tabs.addTab(self._focus_tab(), "Focus")
        tabs.addTab(self._sounds_tab(), "Sounds")

        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self._on_save)

        about = QLabel(f"{APP_NAME} {__version__}" + (
            f' \u00B7 <a href="{dashboard_url}">Open web dashboard</a>' if dashboard_url else ""))
        about.setObjectName("hint")
        about.setOpenExternalLinks(True)

        buttons = QHBoxLayout()
        buttons.addWidget(about)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addLayout(buttons)
        self.load_from_config()

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    @staticmethod
    def _form() -> tuple[QWidget, QFormLayout]:
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(10)
        return page, form

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("hint")
        label.setWordWrap(True)
        return label

    def _general_tab(self) -> QWidget:
        page, form = self._form()
        self.size_spin = QSpinBox()
        self.size_spin.setRange(50, 160)
        self.size_spin.setSuffix(" px")
        form.addRow("Spidey size", self.size_spin)

        self.login_check = QCheckBox("Start Spidey when I log in")
        if autostart.supported():
            form.addRow("", self.login_check)

        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText(default_binding())
        if HotkeyManager.supported():
            form.addRow("Quick-add shortcut", self.hotkey_edit)
            form.addRow("", self._hint(
                f"Format: {default_binding()} or <Ctrl><Alt>t. Leave empty to turn it off."
            ))
        return page

    def _motion_tab(self) -> QWidget:
        page, form = self._form()
        self.spring_slider = QSlider(Qt.Orientation.Horizontal)
        self.spring_slider.setRange(1, 10)
        form.addRow("Web springiness", self.spring_slider)
        form.addRow("", self._hint("Left = soft and bouncy, right = tight and snappy."))

        self.reduced_check = QCheckBox("Reduced motion (no idle sway or wandering)")
        self.sway_check = QCheckBox("Gentle idle sway")
        self.wander_check = QCheckBox("Swing around on his own now and then")
        self.eyes_check = QCheckBox("Eyes follow my cursor")
        for check in (self.reduced_check, self.sway_check, self.wander_check, self.eyes_check):
            form.addRow("", check)
        return page

    def _reminders_tab(self) -> QWidget:
        page, form = self._form()
        self.nag_spin = QSpinBox()
        self.nag_spin.setRange(1, 240)
        self.nag_spin.setSuffix(" min")
        form.addRow("Remind about pending tasks every", self.nag_spin)

        self.morning_check = QCheckBox("Morning brief when I start the day")
        form.addRow("", self.morning_check)

        self.eod_time = QTimeEdit()
        self.eod_time.setDisplayFormat("HH:mm")
        form.addRow("End-of-day brief at", self.eod_time)

        self.away_spin = QSpinBox()
        self.away_spin.setRange(1, 60)
        self.away_spin.setSuffix(" min")
        form.addRow("Treat me as away after", self.away_spin)
        form.addRow("", self._hint("Reminders wait while you're away or the screen is locked."))

        self.power_spin = QSpinBox()
        self.power_spin.setRange(3, 29)
        self.power_spin.setSuffix(" s")
        if paths.IS_LINUX:  # only logind can hold sleep/shutdown back
            form.addRow("Hold sleep/shutdown for", self.power_spin)
        return page

    def _focus_tab(self) -> QWidget:
        page, form = self._form()
        self.focus_spin = QSpinBox()
        self.focus_spin.setRange(1, 180)
        self.focus_spin.setSuffix(" min")
        form.addRow("Focus session", self.focus_spin)
        self.break_spin = QSpinBox()
        self.break_spin.setRange(1, 60)
        self.break_spin.setSuffix(" min")
        form.addRow("Break", self.break_spin)
        return page

    def _sounds_tab(self) -> QWidget:
        page, form = self._form()
        self.sound_check = QCheckBox("Play sound effects")
        form.addRow("", self.sound_check)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        form.addRow("Volume", self.volume_slider)

        previews = QHBoxLayout()
        for name, label in (("thwip", "Thwip"), ("boing", "Boing"),
                            ("cheer", "Cheer"), ("alert", "Alert")):
            button = QPushButton(label)
            button.setObjectName("secondary")
            button.clicked.connect(lambda _=False, n=name: self._preview(n))
            previews.addWidget(button)
        form.addRow("Preview", previews)
        return page

    def _preview(self, name: str) -> None:
        if self._sounds is None:
            return
        saved_volume = self._config.sound_volume
        self._config.sound_volume = self.volume_slider.value() / 100.0
        self._sounds.play(name, force=True)
        self._config.sound_volume = saved_volume

    # ------------------------------------------------------------------
    # Config <-> widgets
    # ------------------------------------------------------------------

    def load_from_config(self) -> None:
        c = self._config
        self.size_spin.setValue(int(c.character_size))
        try:
            self.login_check.setChecked(autostart.is_enabled())
        except OSError:
            self.login_check.setChecked(c.start_at_login)
        self.hotkey_edit.setText(c.quick_add_hotkey)

        self.spring_slider.setValue(stiffness_to_slider(c.web_stiffness))
        self.reduced_check.setChecked(c.reduced_motion)
        self.sway_check.setChecked(c.idle_animation)
        self.wander_check.setChecked(c.autonomous_moves)
        self.eyes_check.setChecked(c.eyes_follow_cursor)

        self.nag_spin.setValue(max(1, int(c.reminder_interval) // 60))
        self.morning_check.setChecked(c.morning_brief)
        self.eod_time.setTime(QTime.fromString(c.end_of_day_time, "HH:mm"))
        self.away_spin.setValue(max(1, int(c.idle_away_seconds) // 60))
        self.power_spin.setValue(max(3, min(29, int(c.power_reminder_timeout) // 1000)))

        self.focus_spin.setValue(int(c.focus_minutes))
        self.break_spin.setValue(int(c.break_minutes))

        self.sound_check.setChecked(c.sound_effects)
        self.volume_slider.setValue(int(round(c.sound_volume * 100)))

    def apply_to_config(self) -> None:
        c = self._config
        c.character_size = self.size_spin.value()
        c.quick_add_hotkey = self.hotkey_edit.text().strip()

        c.web_stiffness = slider_to_stiffness(self.spring_slider.value())
        c.reduced_motion = self.reduced_check.isChecked()
        c.idle_animation = self.sway_check.isChecked()
        c.autonomous_moves = self.wander_check.isChecked()
        c.eyes_follow_cursor = self.eyes_check.isChecked()

        c.reminder_interval = self.nag_spin.value() * 60
        c.morning_brief = self.morning_check.isChecked()
        c.end_of_day_time = self.eod_time.time().toString("HH:mm")
        c.idle_away_seconds = self.away_spin.value() * 60
        c.power_reminder_timeout = self.power_spin.value() * 1000

        c.focus_minutes = self.focus_spin.value()
        c.break_minutes = self.break_spin.value()

        c.sound_effects = self.sound_check.isChecked()
        c.sound_volume = self.volume_slider.value() / 100.0
        c.start_at_login = self.login_check.isChecked()

    def _on_save(self) -> None:
        from hanging_reminder.logging_config import logger

        self.apply_to_config()
        self._config.validate()
        self._config.save()

        try:
            autostart.set_enabled(self._config.start_at_login)
        except OSError:
            logger.exception("Could not update the autostart entry")

        self.saved.emit()
        self.accept()
