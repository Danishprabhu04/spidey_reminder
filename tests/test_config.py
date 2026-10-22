"""Tests for the application configuration module."""

from __future__ import annotations

import os
import tempfile

import pytest

from hanging_reminder.config import AppConfig


class TestAppConfig:
    """Application configuration tests."""

    def test_load_defaults(self):
        """Load configuration with defaults (no file on disk)."""
        config = AppConfig.load()
        assert config.spring_stiffness == 150.0
        assert config.damping == 0.2
        assert config.gravity == 9.81
        assert config.character_size == 80
        assert config.idle_animation is True

    def test_save_and_reload(self, tmpdir):
        """Save config to disk and reload it."""
        config = AppConfig.load()
        config.spring_stiffness = 200.0
        config.damping = 0.3

        # Save to the XDG default config path (which is under tmpdir)
        # by temporarily setting XDG_CONFIG_HOME
        original_cfg_home = os.environ.get("XDG_CONFIG_HOME", "")
        os.environ["XDG_CONFIG_HOME"] = str(tmpdir)
        try:
            config.save()
            # Reload – should pick up the saved values
            config2 = AppConfig.load()
            # Restore original env
            if original_cfg_home:
                os.environ["XDG_CONFIG_HOME"] = original_cfg_home
            else:
                del os.environ["XDG_CONFIG_HOME"]
            assert config2.spring_stiffness == 200.0
            assert config2.damping == 0.3
        finally:
            # Ensure env is cleaned up
            if "XDG_CONFIG_HOME" in os.environ:
                if original_cfg_home:
                    os.environ["XDG_CONFIG_HOME"] = original_cfg_home
                else:
                    del os.environ["XDG_CONFIG_HOME"]

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
        assert "config" in config.config_path.lower()
        assert "share" in config.db_path.lower() or "local" in config.db_path.lower()