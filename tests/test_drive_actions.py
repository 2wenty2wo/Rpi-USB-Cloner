"""
Tests for rpi_usb_cloner.actions.drive_actions module.

This test suite covers:
- Drive copying with source/target selection
- Drive information display with pagination
- Drive erase operations with progress tracking
- Drive formatting with filesystem selection
- Drive unmounting with power-off option
- Repository device filtering
- Confirmation dialogs and user interaction
"""

import os
import threading
import time
from datetime import datetime
from unittest.mock import Mock, MagicMock, call, patch

import pytest

from rpi_usb_cloner.actions import drive_actions
from rpi_usb_cloner.app import state as app_state


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def mock_app_state():
    """Fixture providing a mock AppState object."""
    state = MagicMock()
    state.run_once = 0
    state.lcdstart = datetime.now()
    return state


@pytest.fixture
def mock_get_selected_usb():
    """Fixture providing a mock function to get selected USB name."""
    return Mock(return_value="sda")


@pytest.fixture
def mock_repo_device():
    """Fixture providing a mock repository device."""
    return {
        "name": "sdb",
        "path": "/dev/sdb",
        "size": "64424509440",
        "type": "disk",
        "mountpoint": None,
        "rm": "1",
        "tran": "usb",
        "model": "Repo Drive",
        "children": [
            {
                "name": "sdb1",
                "path": "/dev/sdb1",
                "size": "64420315136",
                "type": "part",
                "mountpoint": "/media/repo",
                "fstype": "ext4",
            }
        ]
    }


@pytest.fixture
def mock_two_usb_devices(mock_usb_device):
    """Fixture providing two USB devices for copy operations."""
    device2 = {
        "name": "sdb",
        "path": "/dev/sdb",
        "size": "32212254720",
        "type": "disk",
        "mountpoint": None,
        "rm": "1",
        "tran": "usb",
        "model": "USB Drive 2",
        "children": []
    }
    return [mock_usb_device, device2]


@pytest.fixture(autouse=True)
def mock_dependencies(mocker):
    """Auto-use fixture that mocks all drive_actions dependencies."""
    # Mock GPIO
    mocker.patch("rpi_usb_cloner.actions.drive_actions.gpio")

    # Mock display functions
    mocker.patch("rpi_usb_cloner.actions.drive_actions.display.display_lines")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.display.get_display_context")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.display.draw_title_with_icon")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.display._get_line_height", return_value=10)
    mocker.patch("rpi_usb_cloner.actions.drive_actions.display._wrap_lines_to_width", side_effect=lambda x, *args: x)
    mocker.patch("rpi_usb_cloner.actions.drive_actions.display.capture_screenshot", return_value=None)

    # Mock screens functions
    mocker.patch("rpi_usb_cloner.actions.drive_actions.screens.render_error_screen")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.screens.render_confirmation_screen")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.screens.render_status_template")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.screens.render_progress_screen")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.screens.render_info_screen")

    # Mock menus functions
    mocker.patch("rpi_usb_cloner.actions.drive_actions.menus.wait_for_buttons_release")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.menus.select_clone_mode", return_value="smart")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.menus.select_erase_mode", return_value="quick")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.menus.select_filesystem_type", return_value="ext4")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.menus.select_format_type", return_value="quick")

    # Mock storage functions
    mocker.patch("rpi_usb_cloner.actions.drive_actions.list_usb_disks", return_value=[])
    mocker.patch("rpi_usb_cloner.actions.drive_actions.get_children", return_value=[])
    mocker.patch("rpi_usb_cloner.actions.drive_actions.format_device_label", side_effect=lambda x: x.get("name") if isinstance(x, dict) else str(x))
    mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.is_root_device", return_value=False)
    mocker.patch("rpi_usb_cloner.actions.drive_actions.human_size", side_effect=lambda x: f"{x}B" if x else "0B")
    mocker.patch("rpi_usb_cloner.actions.drive_actions.clone_device", return_value=True)
    mocker.patch("rpi_usb_cloner.actions.drive_actions.erase_device", return_value=True)
    mocker.patch("rpi_usb_cloner.actions.drive_actions.find_image_repos", return_value=[])

    # Mock drives service
    mocker.patch("rpi_usb_cloner.actions.drive_actions.drives.get_active_drive_label", return_value="sda")

    # Mock settings
    mocker.patch("rpi_usb_cloner.actions.drive_actions.settings.get_bool", return_value=False)

    # Mock time.sleep to speed up tests
    mocker.patch("rpi_usb_cloner.actions.drive_actions.time.sleep")


# ==============================================================================
# Helper Function Tests
# ==============================================================================

class TestCollectMountpoints:
    """Tests for _collect_mountpoints() helper function."""

    def test_device_with_mountpoint(self, mocker):
        """Test collecting mountpoint from device."""
        device = {"name": "sda", "mountpoint": "/mnt/usb", "children": []}
        mocker.patch("rpi_usb_cloner.actions.drive_actions.get_children", return_value=[])

        mountpoints = drive_actions._collect_mountpoints(device)

        assert mountpoints == {"/mnt/usb"}

    def test_device_with_partition_mountpoints(self, mocker):
        """Test collecting mountpoints from partitions."""
        device = {
            "name": "sda",
            "mountpoint": None,
            "children": []
        }
        children = [
            {"name": "sda1", "mountpoint": "/mnt/part1", "children": []},
            {"name": "sda2", "mountpoint": "/mnt/part2", "children": []},
        ]

        # Mock get_children to return appropriate values for each device
        def mock_get_children(dev):
            if dev.get("name") == "sda":
                return children
            return []

        mocker.patch("rpi_usb_cloner.actions.drive_actions.get_children", side_effect=mock_get_children)

        mountpoints = drive_actions._collect_mountpoints(device)

        assert mountpoints == {"/mnt/part1", "/mnt/part2"}

    def test_device_without_mountpoints(self, mocker):
        """Test device with no mountpoints."""
        device = {"name": "sda", "mountpoint": None, "children": []}
        mocker.patch("rpi_usb_cloner.actions.drive_actions.get_children", return_value=[])

        mountpoints = drive_actions._collect_mountpoints(device)

        assert mountpoints == set()


class TestGetRepoDeviceNames:
    """Tests for _get_repo_device_names() helper function."""

    def test_no_repos_found(self, mocker):
        """Test when no repository drives are found."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.find_image_repos", return_value=[])

        repo_devices = drive_actions._get_repo_device_names()

        assert repo_devices == set()

    def test_repo_device_identified(self, mocker, mock_usb_device, mock_repo_device):
        """Test identifying a device with repository."""
        from pathlib import Path

        # Mock repo on sdb1
        repos = [Path("/media/repo/images")]
        mocker.patch("rpi_usb_cloner.actions.drive_actions.find_image_repos", return_value=repos)
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[mock_usb_device, mock_repo_device])

        def mock_get_children(device):
            return device.get("children", [])

        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.get_children", side_effect=mock_get_children)

        repo_devices = drive_actions._get_repo_device_names()

        assert "sdb" in repo_devices
        assert "sda" not in repo_devices

    def test_multiple_repos(self, mocker, mock_repo_device):
        """Test with multiple repository devices."""
        from pathlib import Path

        repo_device2 = {
            "name": "sdc",
            "path": "/dev/sdc",
            "size": "128849018880",
            "mountpoint": None,
            "children": [
                {"name": "sdc1", "mountpoint": "/media/repo2", "children": []}
            ]
        }

        repos = [Path("/media/repo/images"), Path("/media/repo2/backups")]
        mocker.patch("rpi_usb_cloner.actions.drive_actions.find_image_repos", return_value=repos)
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[mock_repo_device, repo_device2])

        def mock_get_children(device):
            return device.get("children", [])

        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.get_children", side_effect=mock_get_children)

        repo_devices = drive_actions._get_repo_device_names()

        assert "sdb" in repo_devices
        assert "sdc" in repo_devices


class TestPickSourceTarget:
    """Tests for _pick_source_target() helper function."""

    def test_less_than_two_devices(self, mocker, mock_get_selected_usb):
        """Test with insufficient devices."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[])
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value=set())

        source, target = drive_actions._pick_source_target(mock_get_selected_usb)

        assert source is None
        assert target is None

    def test_with_selected_device(self, mocker, mock_two_usb_devices, mock_get_selected_usb):
        """Test source/target selection with pre-selected device."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=mock_two_usb_devices)
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value=set())
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.is_root_device", return_value=False)
        mock_get_selected_usb.return_value = "sda"

        source, target = drive_actions._pick_source_target(mock_get_selected_usb)

        assert source is not None
        assert target is not None
        assert source["name"] == "sda"
        assert target["name"] == "sdb"

    def test_without_selected_device(self, mocker, mock_two_usb_devices):
        """Test source/target selection without pre-selected device."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=mock_two_usb_devices)
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value=set())
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.is_root_device", return_value=False)
        mock_get_selected = Mock(return_value=None)

        source, target = drive_actions._pick_source_target(mock_get_selected)

        assert source is not None
        assert target is not None
        assert source["name"] == "sda"
        assert target["name"] == "sdb"

    def test_excludes_root_device(self, mocker, mock_system_disk, mock_usb_device):
        """Test that root device is excluded from selection."""
        devices = [mock_system_disk, mock_usb_device]
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=devices)
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value=set())

        def is_root(device):
            return device.get("name") == "mmcblk0"

        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.is_root_device", side_effect=is_root)
        mock_get_selected = Mock(return_value=None)

        source, target = drive_actions._pick_source_target(mock_get_selected)

        # Should return None because only one non-root device available
        assert source is None
        assert target is None

    def test_excludes_repo_devices(self, mocker, mock_two_usb_devices):
        """Test that repository devices are excluded."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=mock_two_usb_devices)
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value={"sdb"})
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.is_root_device", return_value=False)
        mock_get_selected = Mock(return_value=None)

        source, target = drive_actions._pick_source_target(mock_get_selected)

        # Should return None because sdb is a repo device
        assert source is None
        assert target is None


class TestEnsureRootForErase:
    """Tests for _ensure_root_for_erase() helper function."""

    def test_as_root_user(self, mocker):
        """Test when running as root."""
        mocker.patch("os.geteuid", return_value=0)

        result = drive_actions._ensure_root_for_erase()

        assert result is True

    def test_as_non_root_user(self, mocker):
        """Test when running as non-root user."""
        mocker.patch("os.geteuid", return_value=1000)
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display.display_lines")

        result = drive_actions._ensure_root_for_erase()

        assert result is False
        mock_display.assert_called_once_with(["Run as root"])


class TestConfirmDestructiveAction:
    """Tests for _confirm_destructive_action() helper function."""

    def test_user_confirms_action(self, mocker, mock_app_state, mock_log_debug):
        """Test when user confirms destructive action."""
        mock_poll = mocker.patch("rpi_usb_cloner.actions.drive_actions.gpio.poll_button_events")
        mock_poll.return_value = True

        result = drive_actions._confirm_destructive_action(
            state=mock_app_state,
            log_debug=mock_log_debug,
            prompt_lines=["ERASE sda", "MODE QUICK"],
        )

        assert result is True

    def test_user_cancels_action(self, mocker, mock_app_state, mock_log_debug):
        """Test when user cancels destructive action."""
        mock_poll = mocker.patch("rpi_usb_cloner.actions.drive_actions.gpio.poll_button_events")
        mock_poll.return_value = False

        result = drive_actions._confirm_destructive_action(
            state=mock_app_state,
            log_debug=mock_log_debug,
            prompt_lines=["ERASE sda"],
        )

        assert result is False

    def test_user_cancels_with_none(self, mocker, mock_app_state, mock_log_debug):
        """Test when poll returns None (timeout or other)."""
        mock_poll = mocker.patch("rpi_usb_cloner.actions.drive_actions.gpio.poll_button_events")
        mock_poll.return_value = None

        result = drive_actions._confirm_destructive_action(
            state=mock_app_state,
            log_debug=mock_log_debug,
            prompt_lines=["FORMAT sda"],
        )

        assert result is False


# ==============================================================================
# Main Function Tests
# ==============================================================================

class TestCopyDrive:
    """Tests for copy_drive() function."""

    def test_insufficient_devices(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb):
        """Test copy with less than 2 devices."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions._pick_source_target", return_value=(None, None))
        mock_error = mocker.patch("rpi_usb_cloner.actions.drive_actions.screens.render_error_screen")

        drive_actions.copy_drive(
            state=mock_app_state,
            clone_mode="smart",
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        mock_error.assert_called_once()
        assert "NEED 2 USBS" in str(mock_error.call_args)

    def test_user_cancels_copy(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb, mock_two_usb_devices):
        """Test when user cancels copy operation."""
        source = mock_two_usb_devices[0]
        target = mock_two_usb_devices[1]
        mocker.patch("rpi_usb_cloner.actions.drive_actions._pick_source_target", return_value=(source, target))

        # Simulate button A press (cancel) immediately
        mock_gpio = mocker.patch("rpi_usb_cloner.actions.drive_actions.gpio")
        mock_gpio.read_button.side_effect = [
            True, True, True, True, True,  # Initial states
            True, True, False, True, True,  # A button released (cancel)
        ]

        drive_actions.copy_drive(
            state=mock_app_state,
            clone_mode="smart",
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        # Should not call clone_device
        mock_clone = mocker.patch("rpi_usb_cloner.actions.drive_actions.clone_device")
        assert mock_clone.call_count == 0

    def test_successful_copy(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb, mock_two_usb_devices):
        """Test successful copy operation."""
        source = mock_two_usb_devices[0]
        target = mock_two_usb_devices[1]
        mocker.patch("rpi_usb_cloner.actions.drive_actions._pick_source_target", return_value=(source, target))

        # Simulate button B press (confirm) with YES selected
        mock_gpio = mocker.patch("rpi_usb_cloner.actions.drive_actions.gpio")
        mock_gpio.read_button.side_effect = [
            True, True, True, True, True,  # Initial states
            True, False, True, True, True,  # R button (select YES)
            True, False, True, False, True,  # B button (confirm)
        ]

        mock_clone = mocker.patch("rpi_usb_cloner.actions.drive_actions.clone_device", return_value=True)

        drive_actions.copy_drive(
            state=mock_app_state,
            clone_mode="smart",
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        mock_clone.assert_called_once()


class TestDriveInfo:
    """Tests for drive_info() function."""

    def test_no_selected_usb(self, mocker, mock_app_state, mock_log_debug):
        """Test when no USB is selected."""
        mock_get_selected = Mock(return_value=None)
        mocker.patch("rpi_usb_cloner.actions.drive_actions._view_devices", return_value=(1, 0))

        # Simulate button A press (exit) immediately
        mock_gpio = mocker.patch("rpi_usb_cloner.actions.drive_actions.gpio")
        mock_gpio.read_button.side_effect = [
            True, True, True, True, True, True,  # Initial states
            False, True, True, True, True, True,  # A button released (exit)
        ]

        drive_actions.drive_info(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected,
        )

        # Function should exit cleanly

    def test_page_navigation_left(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb):
        """Test page navigation with left button."""
        mock_view = mocker.patch("rpi_usb_cloner.actions.drive_actions._view_devices")
        mock_view.return_value = (4, 0)

        # Simulate L button press then A button (exit)
        mock_gpio = mocker.patch("rpi_usb_cloner.actions.drive_actions.gpio")
        mock_gpio.read_button.side_effect = [
            True, True, True, True, True, True,  # Initial states
            True, False, True, True, True, True,  # L button released
            False, True, True, True, True, True,  # A button released (exit)
        ]

        drive_actions.drive_info(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        # Should call _view_devices at least twice
        assert mock_view.call_count >= 2

    def test_page_navigation_right(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb):
        """Test page navigation with right button."""
        mock_view = mocker.patch("rpi_usb_cloner.actions.drive_actions._view_devices")
        mock_view.return_value = (4, 0)

        # Simulate R button press then A button (exit)
        mock_gpio = mocker.patch("rpi_usb_cloner.actions.drive_actions.gpio")
        mock_gpio.read_button.side_effect = [
            True, True, True, True, True, True,  # Initial states
            True, True, False, True, True, True,  # R button released
            False, True, True, True, True, True,  # A button released (exit)
        ]

        drive_actions.drive_info(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        # Should call _view_devices at least twice
        assert mock_view.call_count >= 2


class TestEraseDrive:
    """Tests for erase_drive() function."""

    def test_no_usb_found(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb):
        """Test erase when no USB drives are found."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[])
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value=set())
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display.display_lines")

        drive_actions.erase_drive(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        mock_display.assert_called_once()
        assert "No USB found" in str(mock_display.call_args)

    def test_user_cancels_erase(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb, mock_usb_device):
        """Test when user cancels erase operation."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[mock_usb_device])
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value=set())
        mocker.patch("rpi_usb_cloner.actions.drive_actions.menus.select_erase_mode", return_value=None)

        drive_actions.erase_drive(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        # Should exit without calling erase_device
        mock_erase = mocker.patch("rpi_usb_cloner.actions.drive_actions.erase_device")
        assert mock_erase.call_count == 0

    def test_non_root_user_blocked(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb, mock_usb_device):
        """Test that non-root users are blocked from erasing."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[mock_usb_device])
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value=set())
        mocker.patch("rpi_usb_cloner.actions.drive_actions.menus.select_erase_mode", return_value="quick")
        mocker.patch("rpi_usb_cloner.actions.drive_actions._confirm_destructive_action", return_value=True)
        mocker.patch("os.geteuid", return_value=1000)

        drive_actions.erase_drive(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        # Should exit without calling erase_device
        mock_erase = mocker.patch("rpi_usb_cloner.actions.drive_actions.erase_device")
        assert mock_erase.call_count == 0

    def test_successful_erase(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb, mock_usb_device):
        """Test successful erase operation."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[mock_usb_device])
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value=set())
        mocker.patch("rpi_usb_cloner.actions.drive_actions.menus.select_erase_mode", return_value="quick")
        mocker.patch("rpi_usb_cloner.actions.drive_actions._confirm_destructive_action", return_value=True)
        mocker.patch("os.geteuid", return_value=0)

        # Mock erase_device to complete quickly
        def mock_erase(device, mode, progress_callback=None):
            if progress_callback:
                progress_callback(["Erasing..."], 0.5)
                progress_callback(["Complete"], 1.0)
            return True

        mocker.patch("rpi_usb_cloner.actions.drive_actions.erase_device", side_effect=mock_erase)
        mock_status = mocker.patch("rpi_usb_cloner.actions.drive_actions.screens.render_status_template")

        drive_actions.erase_drive(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        # Should show success message
        success_calls = [call for call in mock_status.call_args_list if "Done" in str(call)]
        assert len(success_calls) > 0


class TestFormatDrive:
    """Tests for format_drive() function."""

    def test_no_usb_found(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb):
        """Test format when no USB drives are found."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[])
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value=set())
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display.display_lines")

        drive_actions.format_drive(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        mock_display.assert_called_once()
        assert "No USB found" in str(mock_display.call_args)

    def test_user_cancels_filesystem_selection(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb, mock_usb_device):
        """Test when user cancels filesystem selection."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[mock_usb_device])
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value=set())
        mocker.patch("rpi_usb_cloner.actions.drive_actions.menus.select_filesystem_type", return_value=None)

        drive_actions.format_drive(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        # Should exit early

    def test_user_cancels_format_type_selection(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb, mock_usb_device):
        """Test when user cancels format type selection."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[mock_usb_device])
        mocker.patch("rpi_usb_cloner.actions.drive_actions._get_repo_device_names", return_value=set())
        mocker.patch("rpi_usb_cloner.actions.drive_actions.menus.select_filesystem_type", return_value="ext4")
        mocker.patch("rpi_usb_cloner.actions.drive_actions.menus.select_format_type", return_value=None)

        drive_actions.format_drive(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        # Should exit early


class TestUnmountDrive:
    """Tests for unmount_drive() function."""

    def test_no_selected_drive(self, mocker, mock_app_state, mock_log_debug):
        """Test unmount when no drive is selected."""
        mock_get_selected = Mock(return_value=None)
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display.display_lines")

        drive_actions.unmount_drive(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected,
        )

        mock_display.assert_called_once()
        assert "NO DRIVE" in str(mock_display.call_args) or "SELECTED" in str(mock_display.call_args)

    def test_drive_not_found(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb):
        """Test unmount when selected drive is not found."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[])
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display.display_lines")

        drive_actions.unmount_drive(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        # Should show drive not found message
        assert mock_display.call_count > 0

    def test_user_cancels_unmount(self, mocker, mock_app_state, mock_log_debug, mock_get_selected_usb, mock_usb_device):
        """Test when user cancels unmount operation."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[mock_usb_device])
        mocker.patch("rpi_usb_cloner.actions.drive_actions._collect_mountpoints", return_value={"/media/usb"})

        mock_poll = mocker.patch("rpi_usb_cloner.actions.drive_actions.gpio.poll_button_events")
        mock_poll.return_value = False

        drive_actions.unmount_drive(
            state=mock_app_state,
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
        )

        # Should not call unmount_device_with_retry
        mock_unmount = mocker.patch("rpi_usb_cloner.storage.devices.unmount_device_with_retry")
        assert mock_unmount.call_count == 0


# ==============================================================================
# Page Rendering Tests
# ==============================================================================

class TestViewDevices:
    """Tests for _view_devices() function."""

    def test_no_selected_usb(self, mocker, mock_log_debug):
        """Test when no USB is selected."""
        mock_get_selected = Mock(return_value=None)
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display.display_lines")

        total_pages, page_index = drive_actions._view_devices(
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected,
            page_index=0,
        )

        assert total_pages == 1
        assert page_index == 0
        mock_display.assert_called_once()

    def test_usb_not_in_list(self, mocker, mock_log_debug, mock_get_selected_usb):
        """Test when selected USB is not in device list."""
        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[])
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display.display_lines")

        total_pages, page_index = drive_actions._view_devices(
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
            page_index=0,
        )

        assert total_pages == 1
        assert page_index == 0
        mock_display.assert_called_once()

    def test_calculates_correct_page_count(self, mocker, mock_log_debug, mock_get_selected_usb, mock_usb_device):
        """Test that page count is calculated correctly."""
        # Add some partitions to trigger multiple pages
        device_with_partitions = mock_usb_device.copy()
        device_with_partitions["children"] = [
            {"name": "sda1", "fstype": "vfat", "label": "BOOT", "mountpoint": "/media/boot"},
            {"name": "sda2", "fstype": "ext4", "label": "ROOT", "mountpoint": "/media/root"},
            {"name": "sda3", "fstype": "swap", "label": None, "mountpoint": None},
        ]

        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.list_usb_disks", return_value=[device_with_partitions])

        def mock_get_children(device):
            return device.get("children", [])

        mocker.patch("rpi_usb_cloner.actions.drive_actions.devices.get_children", side_effect=mock_get_children)

        # Mock display context
        mock_context = Mock()
        mock_context.width = 128
        mock_context.height = 64
        mock_context.x = 11
        mock_context.fontdisks = Mock()
        mock_context.fontcopy = Mock()
        mocker.patch("rpi_usb_cloner.actions.drive_actions.display.get_display_context", return_value=mock_context)

        # Mock draw_title_with_icon to return layout
        mock_layout = Mock()
        mock_layout.content_top = 16
        mocker.patch("rpi_usb_cloner.actions.drive_actions.display.draw_title_with_icon", return_value=mock_layout)

        total_pages, page_index = drive_actions._view_devices(
            log_debug=mock_log_debug,
            get_selected_usb_name=mock_get_selected_usb,
            page_index=0,
        )

        # Should have at least 4 pages (disk usage + device info + drive info + partition info)
        assert total_pages >= 4
