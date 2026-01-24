"""Tests for drive action handlers.

This module tests the action handlers in rpi_usb_cloner.actions.drive_actions,
which handle user-facing drive operations like cloning, erasing, formatting, etc.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from rpi_usb_cloner.actions import drive_actions
from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.domain import CloneMode


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def mock_app_state():
    """Fixture providing a mock AppState."""
    state = app_state.AppState()
    state.run_once = 0
    state.lcdstart = datetime.now()
    return state


@pytest.fixture
def mock_gpio(mocker):
    """Fixture providing mocked GPIO module."""
    gpio_mock = mocker.patch("rpi_usb_cloner.actions.drive_actions.gpio")
    gpio_mock.PIN_L = 27
    gpio_mock.PIN_R = 23
    gpio_mock.PIN_A = 5
    gpio_mock.PIN_B = 6
    gpio_mock.PIN_C = 13
    gpio_mock.is_pressed = Mock(return_value=False)
    return gpio_mock


@pytest.fixture
def mock_screens(mocker):
    """Fixture providing mocked screen rendering functions."""
    screens_mock = mocker.patch("rpi_usb_cloner.actions.drive_actions.screens")
    screens_mock.render_error_screen = Mock()
    screens_mock.render_confirmation_screen = Mock()
    screens_mock.render_status_template = Mock()
    return screens_mock


@pytest.fixture
def mock_menus(mocker):
    """Fixture providing mocked menu utilities."""
    menus_mock = mocker.patch("rpi_usb_cloner.actions.drive_actions.menus")
    menus_mock.wait_for_buttons_release = Mock()
    menus_mock.select_clone_mode = Mock(return_value="smart")
    return menus_mock


@pytest.fixture
def mock_time_sleep(mocker):
    """Fixture providing mocked time.sleep to avoid actual delays."""
    return mocker.patch("time.sleep")


@pytest.fixture
def mock_devices_list(mocker, mock_usb_device):
    """Fixture providing mocked list_usb_disks function."""
    # Create two different USB devices
    device1 = mock_usb_device.copy()
    device1["name"] = "sda"
    device1["path"] = "/dev/sda"

    device2 = mock_usb_device.copy()
    device2["name"] = "sdb"
    device2["path"] = "/dev/sdb"

    mock = mocker.patch(
        "rpi_usb_cloner.actions.drive_actions.list_usb_disks",
        return_value=[device1, device2]
    )
    return mock


@pytest.fixture
def mock_clone_device_v2(mocker):
    """Fixture providing mocked clone_device_v2 function."""
    return mocker.patch(
        "rpi_usb_cloner.actions.drive_actions.clone_device_v2",
        return_value=True
    )


@pytest.fixture
def mock_erase_device(mocker):
    """Fixture providing mocked erase_device function."""
    return mocker.patch(
        "rpi_usb_cloner.actions.drive_actions.erase_device"
    )


# ==============================================================================
# Helper Functions Tests
# ==============================================================================


class TestLogDebug:
    """Test the _log_debug helper function."""

    def test_logs_when_callback_provided(self):
        """Test logging when callback is provided."""
        log_callback = Mock()
        drive_actions._log_debug(log_callback, "Test message")
        log_callback.assert_called_once_with("Test message")

    def test_no_error_when_callback_is_none(self):
        """Test no error when callback is None."""
        # Should not raise any exception
        drive_actions._log_debug(None, "Test message")


class TestHandleScreenshot:
    """Test the _handle_screenshot helper function."""

    def test_returns_false_when_screenshots_disabled(self, mocker):
        """Test returns False when screenshots are disabled."""
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.settings.get_bool",
            return_value=False
        )
        result = drive_actions._handle_screenshot()
        assert result is False

    def test_returns_true_when_screenshots_enabled(self, mocker):
        """Test returns True when screenshots are enabled and succeeds."""
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.settings.get_bool",
            return_value=True
        )
        mock_screens = mocker.patch("rpi_usb_cloner.actions.drive_actions.screens")
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display")
        mock_display.take_screenshot = Mock(return_value=Path("/tmp/screenshot.png"))

        result = drive_actions._handle_screenshot()
        assert result is True
        mock_display.take_screenshot.assert_called_once()


class TestPickSourceTarget:
    """Test the _pick_source_target helper function."""

    def test_returns_none_when_less_than_two_devices(self, mocker):
        """Test returns None when less than 2 USB devices available."""
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks",
            return_value=[{"name": "sda"}]
        )

        get_selected = Mock(return_value=None)
        source, target = drive_actions._pick_source_target(get_selected)

        assert source is None
        assert target is None

    def test_returns_source_and_target_when_two_devices_available(
        self, mocker, mock_usb_device
    ):
        """Test returns source and target when 2 devices available."""
        device1 = mock_usb_device.copy()
        device1["name"] = "sda"
        device2 = mock_usb_device.copy()
        device2["name"] = "sdb"

        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks",
            return_value=[device1, device2]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.devices.is_root_device",
            return_value=False
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=[]
        )

        # First call returns None (no specific selection), so it picks first two
        get_selected = Mock(return_value=None)

        source, target = drive_actions._pick_source_target(get_selected)

        assert source == device1
        assert target == device2

    def test_returns_selected_as_source(self, mocker, mock_usb_device):
        """Test returns selected device as source when specified."""
        device1 = mock_usb_device.copy()
        device1["name"] = "sda"
        device2 = mock_usb_device.copy()
        device2["name"] = "sdb"

        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks",
            return_value=[device1, device2]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.devices.is_root_device",
            return_value=False
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=[]
        )

        # User selected sdb, so it should be source
        get_selected = Mock(return_value="sdb")

        source, target = drive_actions._pick_source_target(get_selected)

        assert source == device2  # sdb is source
        assert target == device1  # sda is target


class TestCollectMountpoints:
    """Test the _collect_mountpoints helper function."""

    def test_returns_empty_set_for_unmounted_device(self, mock_usb_device):
        """Test returns empty set when device has no mountpoints."""
        device = mock_usb_device.copy()
        device["mountpoint"] = None
        device["children"] = []

        mountpoints = drive_actions._collect_mountpoints(device)
        assert mountpoints == set()

    def test_returns_device_mountpoint(self, mock_usb_device):
        """Test returns device's own mountpoint."""
        device = mock_usb_device.copy()
        device["mountpoint"] = "/media/usb"
        device["children"] = []

        mountpoints = drive_actions._collect_mountpoints(device)
        assert mountpoints == {"/media/usb"}

    def test_returns_partition_mountpoints(self, mock_usb_device):
        """Test returns all partition mountpoints."""
        device = mock_usb_device.copy()
        device["mountpoint"] = None
        device["children"] = [
            {
                "name": "sda1",
                "mountpoint": "/media/usb1",
            },
            {
                "name": "sda2",
                "mountpoint": "/media/usb2",
            },
        ]

        mountpoints = drive_actions._collect_mountpoints(device)
        assert mountpoints == {"/media/usb1", "/media/usb2"}

    def test_filters_none_mountpoints(self, mock_usb_device):
        """Test filters out None mountpoints."""
        device = mock_usb_device.copy()
        device["mountpoint"] = None
        device["children"] = [
            {"name": "sda1", "mountpoint": "/media/usb1"},
            {"name": "sda2", "mountpoint": None},
            {"name": "sda3", "mountpoint": "/media/usb3"},
        ]

        mountpoints = drive_actions._collect_mountpoints(device)
        assert mountpoints == {"/media/usb1", "/media/usb3"}


class TestEnsureRootForErase:
    """Test the _ensure_root_for_erase helper function."""

    def test_returns_true_when_running_as_root(self, mocker):
        """Test returns True when running as root (uid=0)."""
        mocker.patch("os.geteuid", return_value=0)

        result = drive_actions._ensure_root_for_erase()
        assert result is True

    def test_returns_false_and_shows_error_when_not_root(self, mocker):
        """Test returns False and shows error when not running as root."""
        mocker.patch("os.geteuid", return_value=1000)
        mocker.patch("time.sleep")
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display")

        result = drive_actions._ensure_root_for_erase()

        assert result is False
        mock_display.display_lines.assert_called_once()


# ==============================================================================
# copy_drive Tests
# ==============================================================================


class TestCopyDrive:
    """Test the copy_drive action handler."""

    def test_shows_error_when_less_than_two_devices(
        self,
        mock_app_state,
        mock_gpio,
        mock_screens,
        mock_time_sleep,
        mocker,
    ):
        """Test shows error when less than 2 USB devices available."""
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks",
            return_value=[{"name": "sda"}]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.devices.is_root_device",
            return_value=False
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=[]
        )

        get_selected = Mock(return_value=None)

        drive_actions.copy_drive(
            state=mock_app_state,
            clone_mode="smart",
            log_debug=None,
            get_selected_usb_name=get_selected,
        )

        # Should show error screen
        mock_screens.render_error_screen.assert_called_once()
        call_kwargs = mock_screens.render_error_screen.call_args[1]
        assert "NEED 2 USBS" in call_kwargs["message"]

        # Should sleep after error
        mock_time_sleep.assert_called_once_with(1)

    # Note: copy_drive has complex GPIO polling loops that are difficult to mock
    # The function would benefit from refactoring to make it more testable
    # For now, we test the error case above and rely on integration tests


# ==============================================================================
# erase_drive Tests
# ==============================================================================


class TestEraseDrive:
    """Test the erase_drive action handler."""

    def test_shows_error_when_no_devices(
        self,
        mock_app_state,
        mocker,
    ):
        """Test shows error when no USB devices found."""
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks",
            return_value=[]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=[]
        )
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display")
        mocker.patch("time.sleep")

        get_selected = Mock(return_value=None)

        drive_actions.erase_drive(
            state=mock_app_state,
            log_debug=None,
            get_selected_usb_name=get_selected,
        )

        # Should show "No USB found" message
        mock_display.display_lines.assert_called()
        call_args = mock_display.display_lines.call_args[0][0]
        assert "No USB" in " ".join(call_args) or "No USB found" in str(call_args)

    # Note: Full erase_drive testing requires mocking complex GPIO loops
    # and threading - beyond scope of unit tests


# ==============================================================================
# unmount_drive Tests
# ==============================================================================


class TestUnmountDrive:
    """Test the unmount_drive action handler."""

    def test_shows_error_when_no_device_selected(
        self,
        mock_app_state,
        mocker,
    ):
        """Test shows error when no device selected."""
        mocker.patch("time.sleep")
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display")

        get_selected = Mock(return_value=None)

        drive_actions.unmount_drive(
            state=mock_app_state,
            log_debug=None,
            get_selected_usb_name=get_selected,
        )

        # Should show "NO DRIVE SELECTED" message
        mock_display.display_lines.assert_called()
        call_args = mock_display.display_lines.call_args[0][0]
        assert "NO DRIVE" in " ".join(call_args) or "SELECTED" in " ".join(call_args)

    def test_shows_error_when_device_not_found(
        self,
        mock_app_state,
        mocker,
    ):
        """Test shows error when selected device not found."""
        mocker.patch("time.sleep")
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display")
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks",
            return_value=[]  # No devices
        )

        get_selected = Mock(return_value="sda")

        drive_actions.unmount_drive(
            state=mock_app_state,
            log_debug=None,
            get_selected_usb_name=get_selected,
        )

        # Should show "DRIVE NOT FOUND" message
        mock_display.display_lines.assert_called()

    # Note: Full unmount_drive testing requires mocking GPIO loops
    # and complex UI interactions - beyond scope of unit tests
