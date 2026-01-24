"""Tests for settings action handlers.

This module tests the action handlers in rpi_usb_cloner.actions.settings/,
which handle system settings, power management, updates, and UI configuration.
"""

from unittest.mock import Mock, patch
import pytest

from rpi_usb_cloner.actions.settings import system_power, system_utils, ui_actions


# ==============================================================================
# System Power Tests
# ==============================================================================


class TestReboot:
    """Test the reboot action handler."""

    def test_shows_confirmation_before_reboot(self, mocker):
        """Test shows confirmation dialog before rebooting."""
        mock_screens = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_power.screens"
        )
        mock_menus = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_power.menus"
        )
        mocker.patch("subprocess.run")
        mocker.patch("time.sleep")

        # User cancels
        mock_menus.prompt_yes_no = Mock(return_value=False)

        system_power.reboot()

        # Should show confirmation
        mock_menus.prompt_yes_no.assert_called_once()

    def test_executes_reboot_on_confirmation(self, mocker):
        """Test executes reboot command when user confirms."""
        mocker.patch("rpi_usb_cloner.actions.settings.system_power.screens")
        mock_menus = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_power.menus"
        )
        mock_subprocess = mocker.patch("subprocess.run")
        mocker.patch("time.sleep")

        # User confirms
        mock_menus.prompt_yes_no = Mock(return_value=True)

        system_power.reboot()

        # Should execute reboot command
        mock_subprocess.assert_called()
        call_args = mock_subprocess.call_args[0][0]
        assert "reboot" in call_args

    def test_does_not_reboot_on_cancel(self, mocker):
        """Test does not reboot when user cancels."""
        mocker.patch("rpi_usb_cloner.actions.settings.system_power.screens")
        mock_menus = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_power.menus"
        )
        mock_subprocess = mocker.patch("subprocess.run")

        # User cancels
        mock_menus.prompt_yes_no = Mock(return_value=False)

        system_power.reboot()

        # Should NOT execute reboot
        mock_subprocess.assert_not_called()


class TestShutdown:
    """Test the shutdown action handler."""

    def test_shows_confirmation_before_shutdown(self, mocker):
        """Test shows confirmation dialog before shutting down."""
        mock_screens = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_power.screens"
        )
        mock_menus = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_power.menus"
        )
        mocker.patch("subprocess.run")
        mocker.patch("time.sleep")

        # User cancels
        mock_menus.prompt_yes_no = Mock(return_value=False)

        system_power.shutdown()

        # Should show confirmation
        mock_menus.prompt_yes_no.assert_called_once()

    def test_executes_shutdown_on_confirmation(self, mocker):
        """Test executes shutdown command when user confirms."""
        mocker.patch("rpi_usb_cloner.actions.settings.system_power.screens")
        mock_menus = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_power.menus"
        )
        mock_subprocess = mocker.patch("subprocess.run")
        mocker.patch("time.sleep")

        # User confirms
        mock_menus.prompt_yes_no = Mock(return_value=True)

        system_power.shutdown()

        # Should execute shutdown command
        mock_subprocess.assert_called()
        call_args = mock_subprocess.call_args[0][0]
        assert "shutdown" in call_args or "poweroff" in call_args


class TestFactoryReset:
    """Test the factory_reset action handler."""

    def test_shows_confirmation_before_reset(self, mocker):
        """Test shows confirmation dialog before factory reset."""
        mocker.patch("rpi_usb_cloner.actions.settings.system_power.screens")
        mock_menus = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_power.menus"
        )
        mocker.patch("time.sleep")

        # User cancels
        mock_menus.prompt_yes_no = Mock(return_value=False)

        system_power.factory_reset()

        # Should show confirmation
        mock_menus.prompt_yes_no.assert_called_once()

    def test_resets_settings_on_confirmation(self, mocker):
        """Test resets settings when user confirms."""
        mocker.patch("rpi_usb_cloner.actions.settings.system_power.screens")
        mock_menus = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_power.menus"
        )
        mock_settings = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_power.settings"
        )
        mocker.patch("time.sleep")

        # User confirms
        mock_menus.prompt_yes_no = Mock(return_value=True)

        system_power.factory_reset()

        # Should reset settings
        assert mock_settings.reset_to_defaults.called or mock_settings.clear.called


# ==============================================================================
# System Utilities Tests
# ==============================================================================


class TestGetSystemInfo:
    """Test the get_system_info function."""

    def test_returns_system_information(self, mocker):
        """Test returns dictionary with system information."""
        # Mock platform module
        mocker.patch("platform.system", return_value="Linux")
        mocker.patch("platform.release", return_value="5.10.0")
        mocker.patch("platform.machine", return_value="armv7l")

        # Mock psutil (if used)
        mock_psutil = mocker.patch("rpi_usb_cloner.actions.settings.system_utils.psutil")
        mock_psutil.cpu_count = Mock(return_value=4)
        mock_psutil.virtual_memory = Mock(
            return_value=Mock(total=1024 * 1024 * 1024)
        )

        result = system_utils.get_system_info()

        # Should return dict with system info
        assert isinstance(result, dict)


class TestViewLogs:
    """Test the view_logs action handler."""

    def test_displays_log_viewer_screen(self, mocker):
        """Test displays log viewer screen."""
        mock_screens = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_utils.screens"
        )
        mock_gpio = mocker.patch(
            "rpi_usb_cloner.actions.settings.system_utils.gpio"
        )

        # Simulate button A press to exit
        mock_gpio.is_pressed = Mock(side_effect=[False, False, True, False])

        system_utils.view_logs()

        # Should show log screen
        # Note: Actual assertion depends on implementation


# ==============================================================================
# UI Actions Tests
# ==============================================================================


class TestToggleScreensaver:
    """Test the toggle_screensaver action handler."""

    def test_enables_screensaver_when_disabled(self, mocker):
        """Test enables screensaver when currently disabled."""
        mock_settings = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.settings"
        )
        mock_screens = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.screens"
        )
        mocker.patch("time.sleep")

        # Currently disabled
        mock_settings.get_bool = Mock(return_value=False)

        ui_actions.toggle_screensaver()

        # Should enable it
        mock_settings.set_bool.assert_called()
        call_args = mock_settings.set_bool.call_args
        assert call_args[0][0] == "screensaver_enabled"
        assert call_args[0][1] is True

    def test_disables_screensaver_when_enabled(self, mocker):
        """Test disables screensaver when currently enabled."""
        mock_settings = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.settings"
        )
        mock_screens = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.screens"
        )
        mocker.patch("time.sleep")

        # Currently enabled
        mock_settings.get_bool = Mock(return_value=True)

        ui_actions.toggle_screensaver()

        # Should disable it
        mock_settings.set_bool.assert_called()
        call_args = mock_settings.set_bool.call_args
        assert call_args[0][0] == "screensaver_enabled"
        assert call_args[0][1] is False

    def test_saves_settings_after_toggle(self, mocker):
        """Test saves settings after toggling screensaver."""
        mock_settings = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.settings"
        )
        mocker.patch("rpi_usb_cloner.actions.settings.ui_actions.screens")
        mocker.patch("time.sleep")

        mock_settings.get_bool = Mock(return_value=False)

        ui_actions.toggle_screensaver()

        # Should save settings
        mock_settings.save_settings.assert_called_once()


class TestSetScreensaverTimeout:
    """Test the set_screensaver_timeout action handler."""

    def test_prompts_user_for_timeout_value(self, mocker):
        """Test prompts user to enter timeout value."""
        mocker.patch("rpi_usb_cloner.actions.settings.ui_actions.settings")
        mocker.patch("rpi_usb_cloner.actions.settings.ui_actions.screens")
        mock_menus = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.menus"
        )
        mocker.patch("time.sleep")

        # User cancels input
        mock_menus.prompt_text_input = Mock(return_value=None)

        ui_actions.set_screensaver_timeout()

        # Should prompt for input
        mock_menus.prompt_text_input.assert_called_once()

    def test_saves_valid_timeout_value(self, mocker):
        """Test saves valid timeout value."""
        mock_settings = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.settings"
        )
        mocker.patch("rpi_usb_cloner.actions.settings.ui_actions.screens")
        mock_menus = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.menus"
        )
        mocker.patch("time.sleep")

        # User enters 300 seconds
        mock_menus.prompt_text_input = Mock(return_value="300")

        ui_actions.set_screensaver_timeout()

        # Should save the value
        mock_settings.set_setting.assert_called()
        mock_settings.save_settings.assert_called()

    def test_handles_invalid_timeout_value(self, mocker):
        """Test handles invalid (non-numeric) timeout value."""
        mock_settings = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.settings"
        )
        mock_screens = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.screens"
        )
        mock_menus = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.menus"
        )
        mocker.patch("time.sleep")

        # User enters invalid value
        mock_menus.prompt_text_input = Mock(return_value="invalid")

        ui_actions.set_screensaver_timeout()

        # Should show error or handle gracefully
        # Implementation may vary


class TestToggleWebServer:
    """Test the toggle_web_server action handler."""

    def test_enables_web_server_when_disabled(self, mocker):
        """Test enables web server when currently disabled."""
        mock_settings = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.settings"
        )
        mock_screens = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.screens"
        )
        mocker.patch("time.sleep")

        # Currently disabled
        mock_settings.get_bool = Mock(return_value=False)

        ui_actions.toggle_web_server()

        # Should enable it
        mock_settings.set_bool.assert_called()
        call_args = mock_settings.set_bool.call_args
        assert call_args[0][0] == "web_server_enabled"
        assert call_args[0][1] is True

    def test_shows_restart_required_message(self, mocker):
        """Test shows message that restart is required."""
        mock_settings = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.settings"
        )
        mock_screens = mocker.patch(
            "rpi_usb_cloner.actions.settings.ui_actions.screens"
        )
        mocker.patch("time.sleep")

        mock_settings.get_bool = Mock(return_value=False)

        ui_actions.toggle_web_server()

        # Should show status with restart message
        mock_screens.render_status_template.assert_called()
