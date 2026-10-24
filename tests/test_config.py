"""Tests for the application configuration module."""

from __future__ import annotations

import os
import tempfile

import pytest

from hanging_reminder.config import AppConfig


class TestAppConfig:
    """Application configuration tests."""

    def test_load_defaults(self, tmp_path, monkeypatch):
        """Load configuration with defaults (no file on disk)."""
        import hanging_reminder.config as config_module
        monkeypatch.setattr(config_module, "_config_dir", lambda: tmp_path)
        config = AppConfig.load()
        assert config.spring_stiffness == 150.0
        assert config.damping == 0.2
        assert config.gravity == 9.81
        assert config.character_size == 80
        assert config.idle_animation is True

    def test_save_and_reload(self, isolated_profile):
        """Save config to disk and reload it (conftest points XDG at a tmp dir)."""
        config = AppConfig.load()
        assert str(isolated_profile) in config.config_path
        config.spring_stiffness = 200.0
        config.damping = 0.3
        config.save()
        config2 = AppConfig.load()
        assert config2.spring_stiffness == 200.0
        assert config2.damping == 0.3

    def test_validation_invalid_damping(self):
        """Invalid damping (>1 or <0) is corrected to default."""
        config = AppConfig()
        # Manually set an invalid value (bypassing the dataclass for test)
        config.damping = 1.5  # invalid
        assert config.validate() is False  # should detect failure
        # After validate, damping should be reset to default
        assert config.damping == 0.2  # reset to default

    def test_validation_invalid_stiffness(self):
        """Invalid spring_stiffness (<=0) is corrected."""
        config = AppConfig()
        config.spring_stiffness = -10.0
        assert config.validate() is False
        assert config.spring_stiffness == 150.0  # reset to default

    def test_validation_invalid_character_size(self):
        """Invalid character_size (<=0) is corrected."""
        config = AppConfig()
        config.character_size = 0
        assert config.validate() is False
        assert config.character_size == 80  # reset to default

    def test_config_has_required_paths(self):
        """Config has config_path and db_path set."""
        config = AppConfig.load()
        from pathlib import Path

        from hanging_reminder import paths

        assert Path(config.config_path) == paths.config_dir() / "config.json"
        assert Path(config.db_path) == paths.data_dir() / "tasks.db"