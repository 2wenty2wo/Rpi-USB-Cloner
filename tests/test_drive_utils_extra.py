"""Additional tests for drive action utilities.

Tests for uncovered functions in rpi_usb_cloner.actions.drives._utils module.
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from rpi_usb_cloner.actions.drives import _utils as drive_utils
from rpi_usb_cloner.app import state as app_state


class TestConfirmDestructiveAction:
    """Test confirm_destructive_action function."""

    def test_returns_true_when_confirmed(self, mocker):
        """Test returns True when user confirms (selects YES and presses B)."""
        mock_state = Mock()
        mock_state.run_once = 0
        mock_state.lcdstart = datetime.now()

        mock_render = Mock()
        mock_wait = Mock()

        def mock_poll(callbacks, poll_interval, loop_callback):
            # Simulate user pressing right then B
            callbacks[23]()  # PIN_R - move to YES
            return callbacks[6]()  # PIN_B - confirm (returns True when YES selected)

        result = drive_utils.confirm_destructive_action(
            state=mock_state,
            prompt_lines=["Erase all data?"],
            poll_button_events=mock_poll,
            wait_for_buttons_release=mock_wait,
            render_confirmation_screen=mock_render,
            poll_interval=0.01,
        )

        assert result is True
        mock_wait.assert_called_once()
        mock_render.assert_called()

    def test_returns_false_when_cancelled(self, mocker):
        """Test returns False when user cancels (presses A)."""
        mock_state = Mock()
        mock_state.run_once = 0
        mock_state.lcdstart = datetime.now()

        mock_render = Mock()
        mock_wait = Mock()

        def mock_poll(callbacks, poll_interval, loop_callback):
            # Simulate user pressing A to cancel
            return callbacks[5]()  # PIN_A - cancel

        result = drive_utils.confirm_destructive_action(
            state=mock_state,
            prompt_lines=["Erase all data?"],
            poll_button_events=mock_poll,
            wait_for_buttons_release=mock_wait,
            render_confirmation_screen=mock_render,
            poll_interval=0.01,
        )

        assert result is False

    def test_returns_false_on_none_result(self, mocker):
        """Test returns False when poll_button_events returns None."""
        mock_state = Mock()
        mock_state.run_once = 0
        mock_state.lcdstart = datetime.now()

        mock_render = Mock()
        mock_wait = Mock()

        def mock_poll(callbacks, poll_interval, loop_callback):
            # Simulate returning None (e.g., timeout)
            return None

        result = drive_utils.confirm_destructive_action(
            state=mock_state,
            prompt_lines=["Erase all data?"],
            poll_button_events=mock_poll,
            wait_for_buttons_release=mock_wait,
            render_confirmation_screen=mock_render,
            poll_interval=0.01,
        )

        assert result is False

    def test_toggles_selection_with_left_and_right(self, mocker):
        """Test that left/right toggles selection and updates lcdstart."""
        mock_state = Mock()
        mock_state.run_once = 0
        initial_time = datetime.now()
        mock_state.lcdstart = initial_time

        mock_render = Mock()
        mock_wait = Mock()
        selection_changes = []

        def mock_poll(callbacks, poll_interval, loop_callback):
            # First toggle to YES
            callbacks[23]()  # PIN_R
            selection_changes.append("right")
            # Then toggle back to NO
            callbacks[27]()  # PIN_L
            selection_changes.append("left")
            # Confirm with B (but NO is selected, so returns False)
            return callbacks[6]()  # PIN_B

        result = drive_utils.confirm_destructive_action(
            state=mock_state,
            prompt_lines=["Erase all data?"],
            poll_button_events=mock_poll,
            wait_for_buttons_release=mock_wait,
            render_confirmation_screen=mock_render,
            poll_interval=0.01,
        )

        assert "right" in selection_changes
        assert "left" in selection_changes
        assert result is False  # Because NO was selected when B was pressed

    def test_uses_default_dependencies(self, mocker):
        """Test function uses default dependencies when none provided."""
        mock_state = Mock()
        mock_state.run_once = 0
        mock_state.lcdstart = datetime.now()

        # Mock all the default dependencies
        mocker.patch("rpi_usb_cloner.actions.drives._utils.gpio.poll_button_events", return_value=True)
        mocker.patch("rpi_usb_cloner.actions.drives._utils.menus.wait_for_buttons_release")
        mocker.patch("rpi_usb_cloner.actions.drives._utils.screens.render_confirmation_screen")
        mocker.patch("rpi_usb_cloner.actions.drives._utils.handle_screenshot", return_value=False)
        mocker.patch("rpi_usb_cloner.actions.drives._utils.menus.BUTTON_POLL_DELAY", 0.01)

        result = drive_utils.confirm_destructive_action(
            state=mock_state,
            prompt_lines=["Erase all data?"],
        )

        assert result is True


class TestSelectTargetDeviceEdgeCases:
    """Test select_target_device edge cases."""

    def test_empty_devices_list(self):
        """Test returns empty list and None when no devices."""
        devices, target = drive_utils.select_target_device([], None)
        assert devices == []
        assert target is None

    def test_single_device_no_selection(self):
        """Test with single device and no selection."""
        device = {"name": "sda", "size": 1000000}
        devices, target = drive_utils.select_target_device([device], None)
        assert devices == [device]
        assert target == device

    def test_multiple_devices_sorted(self):
        """Test devices are sorted by name."""
        device_c = {"name": "sdc", "size": 1000000}
        device_a = {"name": "sda", "size": 2000000}
        device_b = {"name": "sdb", "size": 1500000}

        devices, target = drive_utils.select_target_device([device_c, device_a, device_b], None)

        assert devices == [device_a, device_b, device_c]
        assert target == device_c  # Last device is selected when no selection specified

    def test_selection_not_found_falls_back_to_last(self):
        """Test falls back to last device when selection not found."""
        device_a = {"name": "sda", "size": 1000000}
        device_b = {"name": "sdb", "size": 2000000}

        devices, target = drive_utils.select_target_device([device_a, device_b], "nonexistent")

        assert target == device_b  # Falls back to last device

    def test_device_without_name_key(self):
        """Test handling device without name key."""
        device_no_name = {"size": 1000000}
        device_with_name = {"name": "sda", "size": 2000000}

        devices, target = drive_utils.select_target_device([device_no_name, device_with_name], None)

        # Should not crash, sorts with empty string for missing name
        assert device_with_name in devices
        assert device_no_name in devices


class TestBuildStatusLineEdgeCases:
    """Test build_status_line edge cases."""

    def test_empty_devices(self, mocker):
        """Test with empty devices list."""
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.drives.get_active_drive_label",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.format_device_label",
            return_value="FORMATTED",
        )

        status_line = drive_utils.build_status_line([], {"name": "sda"}, None)

        # Should fall back to format_device_label since selected_name not in empty target_names
        assert status_line == "FORMATTED"

    def test_target_device_is_none(self, mocker):
        """Test when target device is None."""
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.drives.get_active_drive_label",
            return_value=None,
        )
        # format_device_label should handle None gracefully
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.format_device_label",
            return_value="UNKNOWN",
        )

        status_line = drive_utils.build_status_line([{"name": "sda"}], None, "sda")

        assert status_line == "UNKNOWN"

    def test_active_drive_label_is_empty_string(self, mocker):
        """Test when active drive label is empty string (falsy but not None)."""
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.drives.get_active_drive_label",
            return_value="",
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.format_device_label",
            return_value="FALLBACK",
        )

        device = {"name": "sda"}
        status_line = drive_utils.build_status_line([device], device, "sda")

        # Empty string is falsy, so should fall back
        assert status_line == "FALLBACK"


class TestCollectMountpointsEdgeCases:
    """Test collect_mountpoints edge cases."""

    def test_nested_children(self):
        """Test collecting mountpoints from nested children."""
        device = {
            "name": "sda",
            "mountpoint": None,
            "children": [
                {
                    "name": "sda1",
                    "mountpoint": "/media/part1",
                    "children": [
                        {"name": "sda1p1", "mountpoint": "/media/nested", "children": []}
                    ],
                },
            ],
        }

        mountpoints = drive_utils.collect_mountpoints(device)

        assert mountpoints == {"/media/part1", "/media/nested"}

    def test_device_with_own_mountpoint_and_children(self):
        """Test device with both own mountpoint and children with mountpoints."""
        device = {
            "name": "sda",
            "mountpoint": "/media/device",
            "children": [
                {"name": "sda1", "mountpoint": "/media/part1", "children": []},
                {"name": "sda2", "mountpoint": "/media/part2", "children": []},
            ],
        }

        mountpoints = drive_utils.collect_mountpoints(device)

        assert mountpoints == {"/media/device", "/media/part1", "/media/part2"}

    def test_empty_children_list(self):
        """Test with empty children list."""
        device = {"name": "sda", "mountpoint": "/media/usb", "children": []}

        mountpoints = drive_utils.collect_mountpoints(device)

        assert mountpoints == {"/media/usb"}

    def test_children_without_mountpoint_key(self):
        """Test children missing mountpoint key entirely."""
        device = {
            "name": "sda",
            "mountpoint": None,
            "children": [{"name": "sda1"}, {"name": "sda2", "mountpoint": "/media/part2"}],
        }

        mountpoints = drive_utils.collect_mountpoints(device)

        assert mountpoints == {"/media/part2"}


class TestHandleScreenshotEdgeCases:
    """Test handle_screenshot edge cases."""

    def test_screenshot_disabled(self, mocker):
        """Test returns False when screenshots disabled."""
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.settings.get_bool",
            return_value=False,
        )

        result = drive_utils.handle_screenshot()

        assert result is False

    def test_screenshot_enabled_but_capture_fails(self, mocker):
        """Test returns False when capture_screenshot returns None."""
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.settings.get_bool",
            return_value=True,
        )
        mocker.patch("rpi_usb_cloner.actions.drives._utils.screens")
        mock_display = mocker.patch("rpi_usb_cloner.actions.drives._utils.display")
        mock_display.capture_screenshot.return_value = None

        result = drive_utils.handle_screenshot()

        assert result is False

    def test_screenshot_enabled_and_succeeds(self, mocker, tmp_path):
        """Test returns True when screenshot succeeds."""
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.settings.get_bool",
            return_value=True,
        )
        mock_screens = mocker.patch("rpi_usb_cloner.actions.drives._utils.screens")
        mock_display = mocker.patch("rpi_usb_cloner.actions.drives._utils.display")
        mocker.patch("time.sleep")

        screenshot_path = tmp_path / "screenshot.png"
        mock_display.capture_screenshot.return_value = screenshot_path

        result = drive_utils.handle_screenshot()

        assert result is True
        mock_screens.render_status_template.assert_called_once()


class TestApplyConfirmationSelectionEdgeCases:
    """Test apply_confirmation_selection edge cases."""

    def test_invalid_direction(self):
        """Test invalid direction leaves selection unchanged."""
        result = drive_utils.apply_confirmation_selection(app_state.CONFIRM_NO, "up")
        assert result == app_state.CONFIRM_NO

        result = drive_utils.apply_confirmation_selection(app_state.CONFIRM_YES, "down")
        assert result == app_state.CONFIRM_YES

    def test_already_at_no_pressing_left(self):
        """Test pressing left when already at NO."""
        result = drive_utils.apply_confirmation_selection(app_state.CONFIRM_NO, "left")
        assert result == app_state.CONFIRM_NO

    def test_already_at_yes_pressing_right(self):
        """Test pressing right when already at YES."""
        result = drive_utils.apply_confirmation_selection(app_state.CONFIRM_YES, "right")
        assert result == app_state.CONFIRM_YES

    def test_empty_direction(self):
        """Test empty string direction."""
        result = drive_utils.apply_confirmation_selection(app_state.CONFIRM_NO, "")
        assert result == app_state.CONFIRM_NO

    def test_none_direction(self):
        """Test None direction."""
        result = drive_utils.apply_confirmation_selection(app_state.CONFIRM_YES, None)
        assert result == app_state.CONFIRM_YES
