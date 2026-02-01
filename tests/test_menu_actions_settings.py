"""Tests for menu actions settings module.

Covers:
- _run_operation helper
- All settings action wrappers
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rpi_usb_cloner.menu.actions import settings


class TestRunOperation:
    """Test _run_operation helper function."""

    def test_run_operation_sets_flags(self):
        """Test that operation flags are set during execution."""
        mock_context = MagicMock()
        mock_app_context = MagicMock()
        mock_context.app_context = mock_app_context
        
        def mock_action():
            assert mock_app_context.operation_active is True
            assert mock_app_context.allow_back_interrupt is False
        
        with patch("rpi_usb_cloner.menu.actions.settings.get_action_context", return_value=mock_context):
            settings._run_operation(mock_action)
        
        # After execution, flags should be reset
        assert mock_app_context.operation_active is False
        assert mock_app_context.allow_back_interrupt is False

    def test_run_operation_with_back_interrupt(self):
        """Test operation with back interrupt enabled."""
        mock_context = MagicMock()
        mock_app_context = MagicMock()
        mock_context.app_context = mock_app_context
        
        def mock_action():
            assert mock_app_context.allow_back_interrupt is True
        
        with patch("rpi_usb_cloner.menu.actions.settings.get_action_context", return_value=mock_context):
            settings._run_operation(mock_action, allow_back_interrupt=True)
        
        assert mock_app_context.operation_active is False

    def test_run_operation_resets_flags_on_exception(self):
        """Test that flags are reset even if action raises exception."""
        mock_context = MagicMock()
        mock_app_context = MagicMock()
        mock_context.app_context = mock_app_context
        
        def failing_action():
            raise ValueError("Test error")
        
        with patch("rpi_usb_cloner.menu.actions.settings.get_action_context", return_value=mock_context):
            with pytest.raises(ValueError, match="Test error"):
                settings._run_operation(failing_action)
        
        # Flags should still be reset
        assert mock_app_context.operation_active is False
        assert mock_app_context.allow_back_interrupt is False


class TestSettingsActions:
    """Test individual settings action wrappers."""

    @pytest.fixture(autouse=True)
    def mock_context(self):
        """Provide mock context for all tests."""
        with patch("rpi_usb_cloner.menu.actions.settings.get_action_context") as mock_get_ctx:
            mock_ctx = MagicMock()
            mock_ctx.app_context = MagicMock()
            mock_get_ctx.return_value = mock_ctx
            yield mock_ctx

    def test_settings_coming_soon(self, mock_context):
        """Test settings_coming_soon wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.settings_coming_soon()
            mock_actions.coming_soon.assert_called_once()

    def test_wifi_settings(self, mock_context):
        """Test wifi_settings wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.wifi_settings()
            mock_actions.wifi_settings.assert_called_once()

    def test_select_restore_partition_mode(self, mock_context):
        """Test select_restore_partition_mode wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.select_restore_partition_mode()
            mock_actions.select_restore_partition_mode.assert_called_once()

    def test_select_transition_speed(self, mock_context):
        """Test select_transition_speed wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.select_transition_speed()
            mock_actions.select_transition_speed.assert_called_once()

    def test_screensaver_settings(self, mock_context):
        """Test screensaver_settings wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.screensaver_settings()
            mock_actions.screensaver_settings.assert_called_once()

    def test_toggle_screensaver_enabled(self, mock_context):
        """Test toggle_screensaver_enabled wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.toggle_screensaver_enabled()
            mock_actions.toggle_screensaver_enabled.assert_called_once()

    def test_toggle_screensaver_mode(self, mock_context):
        """Test toggle_screensaver_mode wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.toggle_screensaver_mode()
            mock_actions.toggle_screensaver_mode.assert_called_once()

    def test_select_screensaver_gif(self, mock_context):
        """Test select_screensaver_gif wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.select_screensaver_gif()
            mock_actions.select_screensaver_gif.assert_called_once()

    def test_preview_screensaver(self, mock_context):
        """Test preview_screensaver wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.preview_screensaver()
            mock_actions.preview_screensaver.assert_called_once()

    def test_keyboard_test(self, mock_context):
        """Test keyboard_test wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.keyboard_test()
            mock_actions.keyboard_test.assert_called_once()

    def test_demo_confirmation_screen(self, mock_context):
        """Test demo_confirmation_screen wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.demo_confirmation_screen()
            mock_actions.demo_confirmation_screen.assert_called_once()

    def test_demo_status_screen(self, mock_context):
        """Test demo_status_screen wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.demo_status_screen()
            mock_actions.demo_status_screen.assert_called_once()

    def test_demo_info_screen(self, mock_context):
        """Test demo_info_screen wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.demo_info_screen()
            mock_actions.demo_info_screen.assert_called_once()

    def test_demo_progress_screen(self, mock_context):
        """Test demo_progress_screen wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.demo_progress_screen()
            mock_actions.demo_progress_screen.assert_called_once()

    def test_lucide_demo(self, mock_context):
        """Test lucide_demo wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.lucide_demo()
            mock_actions.lucide_demo.assert_called_once()

    def test_heroicons_demo(self, mock_context):
        """Test heroicons_demo wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.heroicons_demo()
            mock_actions.heroicons_demo.assert_called_once()

    def test_preview_title_font(self, mock_context):
        """Test preview_title_font wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.preview_title_font()
            mock_actions.preview_title_font.assert_called_once()

    def test_toggle_screenshots(self, mock_context):
        """Test toggle_screenshots wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.toggle_screenshots()
            mock_actions.toggle_screenshots.assert_called_once()

    def test_toggle_menu_icon_preview(self, mock_context):
        """Test toggle_menu_icon_preview wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.toggle_menu_icon_preview()
            mock_actions.toggle_menu_icon_preview.assert_called_once()

    def test_toggle_web_server(self, mock_context):
        """Test toggle_web_server wrapper with app_context."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.toggle_web_server()
            mock_actions.toggle_web_server.assert_called_once_with(
                app_context=mock_context.app_context
            )

    def test_update_version(self, mock_context):
        """Test update_version wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            with patch("rpi_usb_cloner.menu.actions.settings._run_operation") as mock_run:
                settings.update_version()
                mock_run.assert_called_once()

    def test_restart_service(self, mock_context):
        """Test restart_service wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            with patch("rpi_usb_cloner.menu.actions.settings._run_operation") as mock_run:
                settings.restart_service()
                mock_run.assert_called_once()

    def test_stop_service(self, mock_context):
        """Test stop_service wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            with patch("rpi_usb_cloner.menu.actions.settings._run_operation") as mock_run:
                settings.stop_service()
                mock_run.assert_called_once()

    def test_restart_system(self, mock_context):
        """Test restart_system wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            with patch("rpi_usb_cloner.menu.actions.settings._run_operation") as mock_run:
                settings.restart_system()
                mock_run.assert_called_once()

    def test_shutdown_system(self, mock_context):
        """Test shutdown_system wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            with patch("rpi_usb_cloner.menu.actions.settings._run_operation") as mock_run:
                settings.shutdown_system()
                mock_run.assert_called_once()

    def test_show_about_credits(self, mock_context):
        """Test show_about_credits wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.show_about_credits()
            mock_actions.show_about_credits.assert_called_once()


class TestStatusBarToggleActions:
    """Test status bar toggle action wrappers."""

    @pytest.fixture(autouse=True)
    def mock_context(self):
        """Provide mock context for all tests."""
        with patch("rpi_usb_cloner.menu.actions.settings.get_action_context") as mock_get_ctx:
            mock_ctx = MagicMock()
            mock_ctx.app_context = MagicMock()
            mock_get_ctx.return_value = mock_ctx
            yield mock_ctx

    def test_toggle_status_bar_enabled(self, mock_context):
        """Test toggle_status_bar_enabled wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.toggle_status_bar_enabled()
            mock_actions.toggle_status_bar_enabled.assert_called_once()

    def test_toggle_status_bar_wifi(self, mock_context):
        """Test toggle_status_bar_wifi wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.toggle_status_bar_wifi()
            mock_actions.toggle_status_bar_wifi.assert_called_once()

    def test_toggle_status_bar_bluetooth(self, mock_context):
        """Test toggle_status_bar_bluetooth wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.toggle_status_bar_bluetooth()
            mock_actions.toggle_status_bar_bluetooth.assert_called_once()

    def test_toggle_status_bar_web(self, mock_context):
        """Test toggle_status_bar_web wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.toggle_status_bar_web()
            mock_actions.toggle_status_bar_web.assert_called_once()

    def test_toggle_status_bar_drives(self, mock_context):
        """Test toggle_status_bar_drives wrapper."""
        with patch("rpi_usb_cloner.menu.actions.settings.settings_actions") as mock_actions:
            settings.toggle_status_bar_drives()
            mock_actions.toggle_status_bar_drives.assert_called_once()
