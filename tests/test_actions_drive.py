"""Tests for drive action handlers.

This module tests the action handlers in rpi_usb_cloner.actions.drive_actions,
which handle user-facing drive operations like cloning, erasing, formatting, etc.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from rpi_usb_cloner.actions import drive_actions
from rpi_usb_cloner.app import state as app_state


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

    return mocker.patch(
        "rpi_usb_cloner.actions.drive_actions.list_usb_disks",
        return_value=[device1, device2],
    )


@pytest.fixture
def mock_clone_device_v2(mocker):
    """Fixture providing mocked clone_device_v2 function."""
    return mocker.patch(
        "rpi_usb_cloner.actions.drive_actions.clone_device_v2", return_value=True
    )


@pytest.fixture
def mock_erase_device(mocker):
    """Fixture providing mocked erase_device function."""
    return mocker.patch("rpi_usb_cloner.actions.drive_actions.erase_device")


# ==============================================================================
# Helper Functions Tests
# ==============================================================================


class TestHandleScreenshot:
    """Test the _handle_screenshot helper function."""

    def test_returns_false_when_screenshots_disabled(self, mocker):
        """Test returns False when screenshots are disabled."""
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.settings.get_bool", return_value=False
        )
        result = drive_actions._handle_screenshot()
        assert result is False

    def test_returns_true_when_screenshots_enabled(self, mocker):
        """Test returns True when screenshots are enabled and succeeds."""
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.settings.get_bool", return_value=True
        )
        mocker.patch("rpi_usb_cloner.actions.drive_actions.screens")
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display")
        # Correct method name: capture_screenshot (not take_screenshot)
        mock_display.capture_screenshot = Mock(return_value=Path("/tmp/screenshot.png"))
        mocker.patch("time.sleep")

        result = drive_actions._handle_screenshot()
        assert result is True
        mock_display.capture_screenshot.assert_called_once()


class TestPickSourceTarget:
    """Test the _pick_source_target helper function."""

    def test_returns_none_when_less_than_two_devices(self, mocker):
        """Test returns None when less than 2 USB devices available."""
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks",
            return_value=[{"name": "sda"}],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.devices.is_root_device",
            return_value=False,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=[],
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
            return_value=[device1, device2],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.devices.is_root_device",
            return_value=False,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=[],
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
            return_value=[device1, device2],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.devices.is_root_device",
            return_value=False,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=[],
        )

        # User selected sdb, so it should be source
        get_selected = Mock(return_value="sdb")

        source, target = drive_actions._pick_source_target(get_selected)

        assert source == device2  # sdb is source
        assert target == device1  # sda is target


class TestSelectTargetDevice:
    """Test selection logic for target devices."""

    def test_selects_matching_device(self, mock_usb_device):
        """Test selected device is returned when present."""
        device1 = mock_usb_device.copy()
        device1["name"] = "sda"
        device2 = mock_usb_device.copy()
        device2["name"] = "sdb"

        devices, target = drive_actions._select_target_device(
            [device2, device1], selected_name="sda"
        )

        assert devices[0]["name"] == "sda"
        assert target == device1

    def test_falls_back_to_last_device(self, mock_usb_device):
        """Test fallback to last device when selection missing."""
        device1 = mock_usb_device.copy()
        device1["name"] = "sda"
        device2 = mock_usb_device.copy()
        device2["name"] = "sdb"

        devices, target = drive_actions._select_target_device(
            [device1, device2], selected_name="sdc"
        )

        assert target == devices[-1]
        assert target["name"] == "sdb"


class TestBuildStatusLine:
    """Test status line formatting for selected devices."""

    def test_prefers_active_drive_label(self, mocker, mock_usb_device):
        """Test uses active drive label when selection matches."""
        device = mock_usb_device.copy()
        device["name"] = "sda"
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives.get_active_drive_label",
            return_value="ACTIVE LABEL",
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.format_device_label",
            return_value="FALLBACK LABEL",
        )

        status_line = drive_actions._build_status_line(
            [device], device, selected_name="sda"
        )

        assert status_line == "ACTIVE LABEL"

    def test_falls_back_to_device_label(self, mocker, mock_usb_device):
        """Test falls back to formatted device label when selection differs."""
        device = mock_usb_device.copy()
        device["name"] = "sda"
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives.get_active_drive_label",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.format_device_label",
            return_value="FALLBACK LABEL",
        )

        status_line = drive_actions._build_status_line(
            [device], device, selected_name="sdb"
        )

        assert status_line == "FALLBACK LABEL"


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
            return_value=[{"name": "sda"}],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.devices.is_root_device",
            return_value=False,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=[],
        )

        get_selected = Mock(return_value=None)

        drive_actions.copy_drive(
            state=mock_app_state,
            clone_mode="smart",
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
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks", return_value=[]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=[],
        )
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display")
        mocker.patch("time.sleep")

        get_selected = Mock(return_value=None)

        drive_actions.erase_drive(
            state=mock_app_state,
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
            return_value=[],  # No devices
        )

        get_selected = Mock(return_value="sda")

        drive_actions.unmount_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        # Should show "DRIVE NOT FOUND" message
        mock_display.display_lines.assert_called()

    # Note: Full unmount_drive testing requires mocking GPIO loops
    # and complex UI interactions - beyond scope of unit tests


# ==============================================================================
# create_repo_drive Tests
# ==============================================================================


class TestCreateRepoDrive:
    """Test the create_repo_drive action handler."""

    def test_shows_error_when_no_devices(
        self,
        mock_app_state,
        mocker,
    ):
        """Test shows error when no USB devices found."""
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks", return_value=[]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=set(),
        )
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display")
        mocker.patch("time.sleep")

        get_selected = Mock(return_value=None)

        drive_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        # Should show "No USB found" message
        mock_display.display_lines.assert_called()
        call_args = mock_display.display_lines.call_args[0][0]
        assert "CREATE REPO" in call_args or "No USB" in " ".join(call_args)

    def test_shows_error_when_all_devices_are_repos(
        self,
        mock_app_state,
        mock_usb_device,
        mocker,
    ):
        """Test shows error when all USB devices are already repos."""
        device = mock_usb_device.copy()
        device["name"] = "sda"

        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks", return_value=[device]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value={"sda"},  # All devices are repos
        )
        mock_display = mocker.patch("rpi_usb_cloner.actions.drive_actions.display")
        mocker.patch("time.sleep")

        get_selected = Mock(return_value=None)

        drive_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        # Should show "No USB found" message
        mock_display.display_lines.assert_called()
        call_args = mock_display.display_lines.call_args[0][0]
        assert "CREATE REPO" in call_args or "No USB" in " ".join(call_args)

    def test_shows_no_partitions_error(
        self,
        mock_app_state,
        mock_usb_device,
        mock_gpio,
        mock_screens,
        mocker,
    ):
        """Test shows error when device has no partitions."""
        device = mock_usb_device.copy()
        device["name"] = "sda"
        device["children"] = []  # No partitions

        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks", return_value=[device]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=set(),
        )
        mock_menus = mocker.patch("rpi_usb_cloner.actions.drive_actions.menus")
        mock_menus.wait_for_buttons_release = Mock()
        mock_menus.BUTTON_POLL_DELAY = 0.02

        # Simulate user confirming the action
        mock_gpio.poll_button_events = Mock(return_value=True)

        mocker.patch("time.sleep")

        get_selected = Mock(return_value="sda")

        drive_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        # Should show error about no partitions
        mock_screens.render_error_screen.assert_called()
        call_kwargs = mock_screens.render_error_screen.call_args[1]
        assert "No partitions" in call_kwargs["message"]

    def test_creates_flag_file_successfully(
        self,
        mock_app_state,
        mock_usb_device,
        mock_gpio,
        mock_screens,
        mocker,
        tmp_path,
    ):
        """Test successfully creates flag file on mounted partition."""
        # Create a temporary mount point
        mount_path = tmp_path / "usb_mount"
        mount_path.mkdir()

        # Create device with partition that has mountpoint
        device = mock_usb_device.copy()
        device["name"] = "sda"
        partition = {
            "name": "sda1",
            "type": "part",
            "mountpoint": str(mount_path),
        }
        device["children"] = [partition]

        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks", return_value=[device]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=set(),
        )
        mock_invalidate = mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives.invalidate_repo_cache"
        )
        mock_menus = mocker.patch("rpi_usb_cloner.actions.drive_actions.menus")
        mock_menus.wait_for_buttons_release = Mock()
        mock_menus.BUTTON_POLL_DELAY = 0.02
        mocker.patch("rpi_usb_cloner.actions.drive_actions.display")

        # Simulate user confirming the action
        mock_gpio.poll_button_events = Mock(return_value=True)

        mocker.patch("time.sleep")

        get_selected = Mock(return_value="sda")

        drive_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        # Check flag file was created
        flag_path = mount_path / ".rpi-usb-cloner-image-repo"
        assert flag_path.exists()

        # Check repo cache was invalidated
        mock_invalidate.assert_called_once()

        # Check success screen was shown
        mock_screens.render_status_template.assert_called()
        mock_screens.render_status_template.assert_called()

    def test_cancellation_does_not_create_flag_file(
        self,
        mock_app_state,
        mock_usb_device,
        mock_gpio,
        mock_screens,
        mocker,
        tmp_path,
    ):
        """Test cancelling does not create flag file."""
        # Create a temporary mount point
        mount_path = tmp_path / "usb_mount"
        mount_path.mkdir()

        device = mock_usb_device.copy()
        device["name"] = "sda"
        partition = {
            "name": "sda1",
            "type": "part",
            "mountpoint": str(mount_path),
        }
        device["children"] = [partition]

        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks", return_value=[device]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=set(),
        )
        mock_menus = mocker.patch("rpi_usb_cloner.actions.drive_actions.menus")
        mock_menus.wait_for_buttons_release = Mock()
        mock_menus.BUTTON_POLL_DELAY = 0.02

        # Simulate user cancelling the action
        mock_gpio.poll_button_events = Mock(return_value=False)

        mocker.patch("time.sleep")

        get_selected = Mock(return_value="sda")

        drive_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        # Check flag file was NOT created
        flag_path = mount_path / ".rpi-usb-cloner-image-repo"
        assert not flag_path.exists()

    def test_uses_selected_device(
        self,
        mock_app_state,
        mock_usb_device,
        mock_gpio,
        mock_screens,
        mocker,
        tmp_path,
    ):
        """Test uses the selected device when specified."""
        # Create two devices
        mount_path_a = tmp_path / "usb_mount_a"
        mount_path_a.mkdir()
        mount_path_b = tmp_path / "usb_mount_b"
        mount_path_b.mkdir()

        device_a = mock_usb_device.copy()
        device_a["name"] = "sda"
        device_a["children"] = [
            {
                "name": "sda1",
                "type": "part",
                "mountpoint": str(mount_path_a),
            }
        ]

        device_b = mock_usb_device.copy()
        device_b["name"] = "sdb"
        device_b["children"] = [
            {
                "name": "sdb1",
                "type": "part",
                "mountpoint": str(mount_path_b),
            }
        ]

        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.list_usb_disks",
            return_value=[device_a, device_b],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives._get_repo_device_names",
            return_value=set(),
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drive_actions.drives.invalidate_repo_cache"
        )
        mock_menus = mocker.patch("rpi_usb_cloner.actions.drive_actions.menus")
        mock_menus.wait_for_buttons_release = Mock()
        mock_menus.BUTTON_POLL_DELAY = 0.02
        mocker.patch("rpi_usb_cloner.actions.drive_actions.display")

        # Simulate user confirming
        mock_gpio.poll_button_events = Mock(return_value=True)

        mocker.patch("time.sleep")

        # Select sdb specifically
        get_selected = Mock(return_value="sdb")

        drive_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        # Check flag file was created on sdb, not sda
        flag_path_a = mount_path_a / ".rpi-usb-cloner-image-repo"
        flag_path_b = mount_path_b / ".rpi-usb-cloner-image-repo"
        assert not flag_path_a.exists()
        assert flag_path_b.exists()
