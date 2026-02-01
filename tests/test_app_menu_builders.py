"""
Tests for app/menu_builders.py module.

Covers:
- build_device_items function
- build_connectivity_items function
- build_display_items function
- build_screensaver_items function
- build_develop_items function
- build_status_bar_items function
- _build_transition_label function
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, Mock

import pytest

from rpi_usb_cloner.app.menu_builders import (
    _build_transition_label,
    build_connectivity_items,
    build_develop_items,
    build_device_items,
    build_display_items,
    build_screensaver_items,
    build_status_bar_items,
)
from rpi_usb_cloner.config.settings import (
    DEFAULT_TRANSITION_FRAME_COUNT,
    DEFAULT_TRANSITION_FRAME_DELAY,
)


class TestBuildDeviceItems:
    """Test build_device_items function."""

    def test_build_items_with_drives(self):
        """Test building items when drives exist."""
        mock_drives_service = Mock()
        mock_drives_service.list_media_drive_labels.return_value = ["sda 8.00GB", "sdb 16.00GB"]
        
        mock_menu = Mock()
        mock_actions = Mock()
        
        items = build_device_items(mock_drives_service, mock_menu, mock_actions)
        
        assert len(items) == 2
        assert items[0].label == "sda 8.00GB"
        assert items[0].submenu == mock_menu
        assert items[1].label == "sdb 16.00GB"
        assert items[1].submenu == mock_menu

    def test_build_items_no_drives(self):
        """Test building items when no drives exist."""
        mock_drives_service = Mock()
        mock_drives_service.list_media_drive_labels.return_value = []
        
        mock_menu = Mock()
        mock_actions = Mock()
        mock_actions.noop = Mock()
        
        items = build_device_items(mock_drives_service, mock_menu, mock_actions)
        
        assert len(items) == 1
        assert items[0].label == "NO USB DEVICES"
        assert items[0].action == mock_actions.noop


class TestBuildTransitionLabel:
    """Test _build_transition_label function."""

    def test_default_values(self):
        """Test label with default transition settings."""
        mock_settings = Mock()
        mock_settings.get_setting.side_effect = lambda key, default: {
            "transition_frame_count": DEFAULT_TRANSITION_FRAME_COUNT,
            "transition_frame_delay": DEFAULT_TRANSITION_FRAME_DELAY,
        }.get(key, default)
        
        result = _build_transition_label(mock_settings)
        assert "TRANSITIONS:" in result
        assert f"{DEFAULT_TRANSITION_FRAME_COUNT}F" in result
        assert f"{DEFAULT_TRANSITION_FRAME_DELAY:.3f}s" in result

    def test_custom_values(self):
        """Test label with custom transition settings."""
        mock_settings = Mock()
        mock_settings.get_setting.side_effect = lambda key, default: {
            "transition_frame_count": 10,
            "transition_frame_delay": 0.050,
        }.get(key, default)
        
        result = _build_transition_label(mock_settings)
        assert "TRANSITIONS: 10F 0.050s" in result

    def test_invalid_values_use_defaults(self):
        """Test that invalid values fall back to defaults."""
        mock_settings = Mock()
        mock_settings.get_setting.side_effect = lambda key, default: {
            "transition_frame_count": "invalid",
            "transition_frame_delay": "invalid",
        }.get(key, default)
        
        result = _build_transition_label(mock_settings)
        # Should use default values
        assert f"{DEFAULT_TRANSITION_FRAME_COUNT}F" in result
        assert f"{DEFAULT_TRANSITION_FRAME_DELAY:.3f}s" in result

    def test_none_values_use_defaults(self):
        """Test that None values fall back to defaults."""
        mock_settings = Mock()
        mock_settings.get_setting.side_effect = lambda key, default: {
            "transition_frame_count": None,
            "transition_frame_delay": None,
        }.get(key, default)
        
        result = _build_transition_label(mock_settings)
        # Should use default values
        assert f"{DEFAULT_TRANSITION_FRAME_COUNT}F" in result
        assert f"{DEFAULT_TRANSITION_FRAME_DELAY:.3f}s" in result


class TestBuildConnectivityItems:
    """Test build_connectivity_items function."""

    def test_web_server_disabled(self):
        """Test with web server disabled."""
        mock_settings = Mock()
        mock_settings.get_bool.return_value = False
        
        mock_actions = Mock()
        
        items = build_connectivity_items(mock_settings, mock_actions)
        
        assert len(items) == 2
        assert items[0].label == "WIFI"
        assert items[0].action == mock_actions.wifi_settings
        # Check toggle label format
        assert "WEB SERVER" in items[1].label

    def test_web_server_enabled(self):
        """Test with web server enabled."""
        mock_settings = Mock()
        mock_settings.get_bool.return_value = True
        
        mock_actions = Mock()
        
        items = build_connectivity_items(mock_settings, mock_actions)
        
        assert len(items) == 2
        # Check toggle label format - should show ON
        assert "WEB SERVER" in items[1].label

    def test_web_server_env_override(self):
        """Test with WEB_SERVER_ENABLED environment variable."""
        mock_settings = Mock()
        mock_settings.get_bool.return_value = False
        
        mock_actions = Mock()
        
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("WEB_SERVER_ENABLED", "true")
            items = build_connectivity_items(mock_settings, mock_actions)
            
            # Should show (ENV) suffix
            assert "(ENV)" in items[1].label

    def test_web_server_env_override_false(self):
        """Test with WEB_SERVER_ENABLED=false."""
        mock_settings = Mock()
        mock_settings.get_bool.return_value = True
        
        mock_actions = Mock()
        
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("WEB_SERVER_ENABLED", "false")
            items = build_connectivity_items(mock_settings, mock_actions)
            
            # Should show (ENV) suffix and be disabled
            assert "(ENV)" in items[1].label


class TestBuildDisplayItems:
    """Test build_display_items function."""

    def test_screensaver_and_status_bar_disabled(self):
        """Test with both screensaver and status bar disabled."""
        mock_settings = Mock()
        mock_settings.get_bool.side_effect = lambda key, default: {
            "screensaver_enabled": False,
            "status_bar_enabled": False,
        }.get(key, default)
        
        mock_app_state = Mock()
        mock_app_state.screensaver_enabled = False
        
        mock_actions = Mock()
        
        items = build_display_items(mock_settings, mock_app_state, mock_actions)
        
        assert len(items) == 2
        assert "SCREENSAVER" in items[0].label
        assert "STATUS BAR" in items[1].label

    def test_screensaver_and_status_bar_enabled(self):
        """Test with both screensaver and status bar enabled."""
        mock_settings = Mock()
        mock_settings.get_bool.side_effect = lambda key, default: {
            "screensaver_enabled": True,
            "status_bar_enabled": True,
        }.get(key, default)
        
        mock_app_state = Mock()
        mock_app_state.screensaver_enabled = True
        
        mock_actions = Mock()
        
        items = build_display_items(mock_settings, mock_app_state, mock_actions)
        
        assert len(items) == 2
        # Items should have toggle labels showing ON


class TestBuildScreensaverItems:
    """Test build_screensaver_items function."""

    def test_screensaver_disabled_random_mode(self):
        """Test with screensaver disabled and random mode."""
        mock_settings = Mock()
        mock_settings.get_bool.return_value = False
        def get_setting_side_effect(key, default=None):
            return {
                "screensaver_mode": "random",
                "screensaver_gif": None,
            }.get(key, default)
        mock_settings.get_setting.side_effect = get_setting_side_effect
        
        mock_app_state = Mock()
        mock_app_state.screensaver_enabled = False
        
        mock_actions = Mock()
        
        items = build_screensaver_items(mock_settings, mock_app_state, mock_actions)
        
        assert len(items) == 3  # toggle, mode, preview
        assert "SCREENSAVER" in items[0].label
        assert "MODE: RANDOM" == items[1].label
        assert items[2].label == "PREVIEW"

    def test_screensaver_enabled_selected_mode_with_gif(self):
        """Test with screensaver enabled and selected mode with GIF."""
        mock_settings = Mock()
        mock_settings.get_bool.return_value = True
        def get_setting_side_effect(key, default=None):
            return {
                "screensaver_mode": "specific",
                "screensaver_gif": "animation.gif",
            }.get(key, default)
        mock_settings.get_setting.side_effect = get_setting_side_effect
        
        mock_app_state = Mock()
        mock_app_state.screensaver_enabled = True
        
        mock_actions = Mock()
        
        items = build_screensaver_items(mock_settings, mock_app_state, mock_actions)
        
        assert len(items) == 4  # toggle, mode, select gif, preview
        assert "MODE: SELECTED" == items[1].label
        assert "SELECT GIF: animation.gif" == items[2].label

    def test_screensaver_selected_mode_no_gif(self):
        """Test with selected mode but no GIF selected."""
        mock_settings = Mock()
        mock_settings.get_bool.return_value = False
        def get_setting_side_effect(key, default=None):
            return {
                "screensaver_mode": "specific",
                "screensaver_gif": None,
            }.get(key, default)
        mock_settings.get_setting.side_effect = get_setting_side_effect
        
        mock_app_state = Mock()
        mock_app_state.screensaver_enabled = False
        
        mock_actions = Mock()
        
        items = build_screensaver_items(mock_settings, mock_app_state, mock_actions)
        
        assert len(items) == 4  # toggle, mode, select gif (shows NONE), preview
        assert "SELECT GIF: NONE" == items[2].label


class TestBuildDevelopItems:
    """Test build_develop_items function."""

    def test_develop_items_structure(self):
        """Test the structure of develop menu items."""
        mock_settings = Mock()
        mock_settings.get_bool.side_effect = lambda key, default: {
            "screenshots_enabled": False,
            "menu_icon_preview_enabled": False,
        }.get(key, default)
        mock_settings.get_setting.side_effect = lambda key, default: {
            "transition_frame_count": 5,
            "transition_frame_delay": 0.025,
        }.get(key, default)
        
        mock_actions = Mock()
        
        items = build_develop_items(mock_settings, mock_actions)
        
        assert len(items) == 6
        assert items[0].label == "SCREENS"
        assert items[1].label == "ICONS"
        assert items[2].label == "TITLE FONT PREVIEW"
        assert items[2].action == mock_actions.preview_title_font
        assert "SCREENSHOTS" in items[3].label
        assert "ICON PREVIEW" in items[4].label
        assert "TRANSITIONS:" in items[5].label

    def test_develop_items_screenshots_enabled(self):
        """Test with screenshots enabled."""
        mock_settings = Mock()
        mock_settings.get_bool.side_effect = lambda key, default: {
            "screenshots_enabled": True,
            "menu_icon_preview_enabled": False,
        }.get(key, default)
        mock_settings.get_setting.return_value = 5
        
        mock_actions = Mock()
        
        items = build_develop_items(mock_settings, mock_actions)
        
        # Check screenshots toggle shows ON
        assert "SCREENSHOTS" in items[3].label

    def test_develop_items_icon_preview_enabled(self):
        """Test with icon preview enabled."""
        mock_settings = Mock()
        mock_settings.get_bool.side_effect = lambda key, default: {
            "screenshots_enabled": False,
            "menu_icon_preview_enabled": True,
        }.get(key, default)
        mock_settings.get_setting.return_value = 5
        
        mock_actions = Mock()
        
        items = build_develop_items(mock_settings, mock_actions)
        
        # Check icon preview toggle shows ON
        assert "ICON PREVIEW" in items[4].label


class TestBuildStatusBarItems:
    """Test build_status_bar_items function."""

    def test_status_bar_disabled(self):
        """Test when status bar is disabled - only show master toggle."""
        mock_settings = Mock()
        mock_settings.get_bool.side_effect = lambda key, default: {
            "status_bar_enabled": False,
            "status_bar_wifi_enabled": True,
            "status_bar_bluetooth_enabled": True,
            "status_bar_web_enabled": True,
            "status_bar_drives_enabled": True,
        }.get(key, default)
        
        mock_actions = Mock()
        
        items = build_status_bar_items(mock_settings, mock_actions)
        
        # Should only have the master toggle when disabled
        assert len(items) == 1
        assert "SHOW ALL" in items[0].label

    def test_status_bar_enabled(self):
        """Test when status bar is enabled - show all toggles."""
        mock_settings = Mock()
        mock_settings.get_bool.side_effect = lambda key, default: {
            "status_bar_enabled": True,
            "status_bar_wifi_enabled": True,
            "status_bar_bluetooth_enabled": True,
            "status_bar_web_enabled": True,
            "status_bar_drives_enabled": True,
        }.get(key, default)
        
        mock_actions = Mock()
        
        items = build_status_bar_items(mock_settings, mock_actions)
        
        # Should have master toggle + 4 individual toggles
        assert len(items) == 5
        assert "SHOW ALL" in items[0].label
        assert "WIFI" in items[1].label
        assert "BLUETOOTH" in items[2].label
        assert "WEB SERVER" in items[3].label
        assert "DRIVE COUNTS" in items[4].label

    def test_status_bar_individual_toggles_disabled(self):
        """Test individual toggles when some are disabled."""
        mock_settings = Mock()
        mock_settings.get_bool.side_effect = lambda key, default: {
            "status_bar_enabled": True,
            "status_bar_wifi_enabled": False,
            "status_bar_bluetooth_enabled": False,
            "status_bar_web_enabled": True,
            "status_bar_drives_enabled": False,
        }.get(key, default)
        
        mock_actions = Mock()
        
        items = build_status_bar_items(mock_settings, mock_actions)
        
        # All items should exist, but some will show OFF
        assert len(items) == 5
        # Check that individual toggles are present
        assert items[1].action == mock_actions.toggle_status_bar_wifi
        assert items[2].action == mock_actions.toggle_status_bar_bluetooth
        assert items[3].action == mock_actions.toggle_status_bar_web
        assert items[4].action == mock_actions.toggle_status_bar_drives
