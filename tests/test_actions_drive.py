"""Tests for drive action handlers.

This module tests the action handlers in rpi_usb_cloner.actions.drives,
which handle user-facing drive operations like cloning, erasing, formatting, etc.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from rpi_usb_cloner.actions import drive_actions
from rpi_usb_cloner.actions.drives import _utils as drive_utils
from rpi_usb_cloner.actions.drives import clone_actions
from rpi_usb_cloner.actions.drives import erase_actions
from rpi_usb_cloner.actions.drives import unmount_actions
from rpi_usb_cloner.actions.drives import repo_actions
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
    """Fixture providing mocked GPIO module for clone_actions."""
    gpio_mock = mocker.patch("rpi_usb_cloner.actions.drives.clone_actions.gpio")
    gpio_mock.PIN_L = 27
    gpio_mock.PIN_R = 23
    gpio_mock.PIN_A = 5
    gpio_mock.PIN_B = 6
    gpio_mock.PIN_C = 13
    gpio_mock.is_pressed = Mock(return_value=False)
    return gpio_mock


@pytest.fixture
def mock_gpio_repo(mocker):
    """Fixture providing mocked GPIO module for repo_actions."""
    gpio_mock = mocker.patch("rpi_usb_cloner.actions.drives.repo_actions.gpio")
    gpio_mock.PIN_L = 27
    gpio_mock.PIN_R = 23
    gpio_mock.PIN_A = 5
    gpio_mock.PIN_B = 6
    gpio_mock.PIN_C = 13
    gpio_mock.is_pressed = Mock(return_value=False)
    return gpio_mock


@pytest.fixture
def mock_screens_clone(mocker):
    """Fixture providing mocked screen rendering functions for clone_actions."""
    screens_mock = mocker.patch("rpi_usb_cloner.actions.drives.clone_actions.screens")
    screens_mock.render_error_screen = Mock()
    screens_mock.render_confirmation_screen = Mock()
    screens_mock.render_status_template = Mock()
    return screens_mock


@pytest.fixture
def mock_screens_repo(mocker):
    """Fixture providing mocked screen rendering functions for repo_actions."""
    screens_mock = mocker.patch("rpi_usb_cloner.actions.drives.repo_actions.screens")
    screens_mock.render_error_screen = Mock()
    screens_mock.render_confirmation_screen = Mock()
    screens_mock.render_status_template = Mock()
    return screens_mock


@pytest.fixture
def mock_time_sleep(mocker):
    """Fixture providing mocked time.sleep to avoid actual delays."""
    return mocker.patch("time.sleep")


# ==============================================================================
# Helper Functions Tests
# ==============================================================================


class TestHandleScreenshot:
    """Test the handle_screenshot helper function."""

    def test_returns_false_when_screenshots_disabled(self, mocker):
        """Test returns False when screenshots are disabled."""
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.settings.get_bool", return_value=False
        )
        result = drive_utils.handle_screenshot()
        assert result is False

    def test_returns_true_when_screenshots_enabled(self, mocker):
        """Test returns True when screenshots are enabled and succeeds."""
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.settings.get_bool", return_value=True
        )
        mocker.patch("rpi_usb_cloner.actions.drives._utils.screens")
        mock_display = mocker.patch("rpi_usb_cloner.actions.drives._utils.display")
        mock_display.capture_screenshot = Mock(return_value=Path("/tmp/screenshot.png"))
        mocker.patch("time.sleep")

        result = drive_utils.handle_screenshot()
        assert result is True
        mock_display.capture_screenshot.assert_called_once()


class TestApplyConfirmationSelection:
    """Test confirmation selection toggling."""

    def test_selects_yes_on_right(self):
        """Test moving right switches to YES."""
        result = drive_utils.apply_confirmation_selection(
            app_state.CONFIRM_NO, "right"
        )
        assert result == app_state.CONFIRM_YES

    def test_selects_no_on_left(self):
        """Test moving left switches to NO."""
        result = drive_utils.apply_confirmation_selection(
            app_state.CONFIRM_YES, "left"
        )
        assert result == app_state.CONFIRM_NO

    def test_ignores_redundant_moves(self):
        """Test redundant directions leave selection unchanged."""
        assert (
            drive_utils.apply_confirmation_selection(app_state.CONFIRM_NO, "left")
            == app_state.CONFIRM_NO
        )
        assert (
            drive_utils.apply_confirmation_selection(app_state.CONFIRM_YES, "right")
            == app_state.CONFIRM_YES
        )


class TestConfirmCopyPrompt:
    """Test confirmation prompt flow for copy drive."""

    def test_confirms_yes_after_right_and_b(
        self, mock_app_state, mock_gpio, mock_screens_clone
    ):
        """Test confirmation returns True when selecting YES and confirming."""
        mock_wait = Mock()

        def poll_button_events(callbacks, poll_interval, loop_callback):
            loop_callback()
            callbacks[mock_gpio.PIN_R]()
            return callbacks[mock_gpio.PIN_B]()

        result = clone_actions._confirm_copy_prompt(
            state=mock_app_state,
            title="COPY",
            prompt="Clone sda to sdb?",
            poll_button_events=poll_button_events,
            wait_for_buttons_release=mock_wait,
            render_confirmation_screen=mock_screens_clone.render_confirmation_screen,
        )

        assert result is True
        mock_wait.assert_called_once()

    def test_cancel_returns_false(self, mock_app_state, mock_gpio, mock_screens_clone):
        """Test cancellation returns False."""
        mock_wait = Mock()

        def poll_button_events(callbacks, poll_interval, loop_callback):
            loop_callback()
            return callbacks[mock_gpio.PIN_A]()

        result = clone_actions._confirm_copy_prompt(
            state=mock_app_state,
            title="COPY",
            prompt="Clone sda to sdb?",
            poll_button_events=poll_button_events,
            wait_for_buttons_release=mock_wait,
            render_confirmation_screen=mock_screens_clone.render_confirmation_screen,
        )

        assert result is False
        mock_wait.assert_called_once()


class TestExecuteCopyOperation:
    """Test executing copy operations with injected dependencies."""

    def test_returns_cancelled_when_mode_not_selected(self, mock_usb_device):
        """Test cancelled flow returns Cancelled and avoids execution."""
        source = mock_usb_device.copy()
        target = mock_usb_device.copy()
        execute_clone_job = Mock()

        success, status = clone_actions.execute_copy_operation(
            source,
            target,
            "smart",
            select_clone_mode=Mock(return_value=None),
            execute_clone_job=execute_clone_job,
        )

        assert success is False
        assert status == "Cancelled"
        execute_clone_job.assert_not_called()


class TestPickSourceTarget:
    """Test the _pick_source_target helper function."""

    def test_returns_none_when_less_than_two_devices(self, mocker):
        """Test returns None when less than 2 USB devices available."""
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.list_usb_disks",
            return_value=[{"name": "sda"}],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.devices.is_root_device",
            return_value=False,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.drives._get_repo_device_names",
            return_value=[],
        )

        get_selected = Mock(return_value=None)
        source, target = clone_actions._pick_source_target(get_selected)

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
            "rpi_usb_cloner.actions.drives.clone_actions.list_usb_disks",
            return_value=[device1, device2],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.devices.is_root_device",
            return_value=False,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.drives._get_repo_device_names",
            return_value=[],
        )

        get_selected = Mock(return_value=None)

        source, target = clone_actions._pick_source_target(get_selected)

        assert source == device1
        assert target == device2

    def test_returns_selected_as_source(self, mocker, mock_usb_device):
        """Test returns selected device as source when specified."""
        device1 = mock_usb_device.copy()
        device1["name"] = "sda"
        device2 = mock_usb_device.copy()
        device2["name"] = "sdb"

        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.list_usb_disks",
            return_value=[device1, device2],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.devices.is_root_device",
            return_value=False,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.drives._get_repo_device_names",
            return_value=[],
        )

        get_selected = Mock(return_value="sdb")

        source, target = clone_actions._pick_source_target(get_selected)

        assert source == device2  # sdb is source
        assert target == device1  # sda is target


class TestExecuteCloneJob:
    """Test clone job execution helper."""

    def test_returns_invalid_params_for_bad_mode(self, mocker, mock_usb_device):
        """Test invalid mode triggers invalid params result."""
        source = mock_usb_device.copy()
        source["name"] = "sda"
        target = mock_usb_device.copy()
        target["name"] = "sdb"

        clone_mock = mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.clone_device_v2"
        )
        mock_logger = Mock()
        mock_logger.info = Mock()
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.get_logger",
            return_value=mock_logger,
        )

        success, status = clone_actions._execute_clone_job(
            source, target, "invalid", job_id="clone-test"
        )

        assert success is False
        assert status == "Invalid params"
        clone_mock.assert_not_called()

    def test_returns_success_when_clone_completes(self, mocker, mock_usb_device):
        """Test successful clone returns complete status."""
        source = mock_usb_device.copy()
        source["name"] = "sda"
        target = mock_usb_device.copy()
        target["name"] = "sdb"

        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.clone_device_v2", return_value=True
        )
        mock_logger = Mock()
        mock_logger.info = Mock()
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.get_logger",
            return_value=mock_logger,
        )

        success, status = clone_actions._execute_clone_job(
            source, target, "smart", job_id="clone-test"
        )

        assert success is True
        assert status == "Complete."

    def test_returns_failed_status_when_clone_fails(self, mocker, mock_usb_device):
        """Test failed clone returns check logs status."""
        source = mock_usb_device.copy()
        source["name"] = "sda"
        target = mock_usb_device.copy()
        target["name"] = "sdb"

        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.clone_device_v2",
            return_value=False,
        )
        mock_logger = Mock()
        mock_logger.info = Mock()
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.get_logger",
            return_value=mock_logger,
        )

        success, status = clone_actions._execute_clone_job(
            source, target, "smart", job_id="clone-test"
        )

        assert success is False
        assert status == "Check logs."


class TestSelectTargetDevice:
    """Test selection logic for target devices."""

    def test_selects_matching_device(self, mock_usb_device):
        """Test selected device is returned when present."""
        device1 = mock_usb_device.copy()
        device1["name"] = "sda"
        device2 = mock_usb_device.copy()
        device2["name"] = "sdb"

        devices, target = drive_utils.select_target_device(
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

        devices, target = drive_utils.select_target_device(
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
            "rpi_usb_cloner.actions.drives._utils.drives.get_active_drive_label",
            return_value="ACTIVE LABEL",
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.format_device_label",
            return_value="FALLBACK LABEL",
        )

        status_line = drive_utils.build_status_line(
            [device], device, selected_name="sda"
        )

        assert status_line == "ACTIVE LABEL"

    def test_falls_back_to_device_label(self, mocker, mock_usb_device):
        """Test falls back to formatted device label when selection differs."""
        device = mock_usb_device.copy()
        device["name"] = "sda"
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.drives.get_active_drive_label",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives._utils.format_device_label",
            return_value="FALLBACK LABEL",
        )

        status_line = drive_utils.build_status_line(
            [device], device, selected_name="sdb"
        )

        assert status_line == "FALLBACK LABEL"


class TestCollectMountpoints:
    """Test the collect_mountpoints helper function."""

    def test_returns_empty_set_for_unmounted_device(self, mock_usb_device):
        """Test returns empty set when device has no mountpoints."""
        device = mock_usb_device.copy()
        device["mountpoint"] = None
        device["children"] = []

        mountpoints = drive_utils.collect_mountpoints(device)
        assert mountpoints == set()

    def test_returns_device_mountpoint(self, mock_usb_device):
        """Test returns device's own mountpoint."""
        device = mock_usb_device.copy()
        device["mountpoint"] = "/media/usb"
        device["children"] = []

        mountpoints = drive_utils.collect_mountpoints(device)
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

        mountpoints = drive_utils.collect_mountpoints(device)
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

        mountpoints = drive_utils.collect_mountpoints(device)
        assert mountpoints == {"/media/usb1", "/media/usb3"}


class TestEnsureRoot:
    """Test the ensure_root helper function."""

    def test_returns_true_when_running_as_root(self, mocker):
        """Test returns True when running as root (uid=0)."""
        # Skip on non-POSIX systems (Windows doesn't have geteuid)
        import os
        if not hasattr(os, 'geteuid'):
            pytest.skip("geteuid not available on this platform")
        
        mocker.patch("os.geteuid", return_value=0)

        result = drive_utils.ensure_root()
        assert result is True

    def test_returns_false_and_shows_error_when_not_root(self, mocker):
        """Test returns False and shows error when not running as root."""
        # Skip on non-POSIX systems (Windows doesn't have geteuid)
        import os
        if not hasattr(os, 'geteuid'):
            pytest.skip("geteuid not available on this platform")
        
        mocker.patch("os.geteuid", return_value=1000)
        mocker.patch("time.sleep")
        mock_display = mocker.patch("rpi_usb_cloner.actions.drives._utils.display")

        result = drive_utils.ensure_root()

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
        mock_screens_clone,
        mock_time_sleep,
        mocker,
    ):
        """Test shows error when less than 2 USB devices available."""
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.list_usb_disks",
            return_value=[{"name": "sda"}],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.devices.is_root_device",
            return_value=False,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.drives._get_repo_device_names",
            return_value=[],
        )

        get_selected = Mock(return_value=None)

        clone_actions.copy_drive(
            state=mock_app_state,
            clone_mode="smart",
            get_selected_usb_name=get_selected,
        )

        mock_screens_clone.render_error_screen.assert_called_once()
        call_kwargs = mock_screens_clone.render_error_screen.call_args[1]
        assert "NEED 2 USBS" in call_kwargs["message"]

        mock_time_sleep.assert_called_once_with(1)

    def test_runs_copy_when_confirmed(
        self,
        mock_app_state,
        mock_gpio,
        mock_screens_clone,
        mock_time_sleep,
        mocker,
        mock_usb_device,
    ):
        """Test confirms and executes clone operation when confirmed."""
        device1 = mock_usb_device.copy()
        device1["name"] = "sda"
        device2 = mock_usb_device.copy()
        device2["name"] = "sdb"

        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.list_usb_disks",
            return_value=[device1, device2],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.devices.is_root_device",
            return_value=False,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.drives._get_repo_device_names",
            return_value=[],
        )

        execute_clone_job = Mock(return_value=(True, "Complete."))

        clone_actions.copy_drive(
            state=mock_app_state,
            clone_mode="smart",
            get_selected_usb_name=Mock(return_value=None),
            confirm_prompt=Mock(return_value=True),
            select_clone_mode=Mock(return_value="smart"),
            execute_clone_job=execute_clone_job,
        )

        execute_clone_job.assert_called_once()
        mock_screens_clone.render_status_template.assert_called()

    def test_skips_copy_when_cancelled(
        self,
        mock_app_state,
        mock_gpio,
        mock_screens_clone,
        mocker,
        mock_usb_device,
    ):
        """Test cancellation avoids clone execution."""
        device1 = mock_usb_device.copy()
        device1["name"] = "sda"
        device2 = mock_usb_device.copy()
        device2["name"] = "sdb"

        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.list_usb_disks",
            return_value=[device1, device2],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.devices.is_root_device",
            return_value=False,
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.clone_actions.drives._get_repo_device_names",
            return_value=[],
        )

        execute_clone_job = Mock()

        clone_actions.copy_drive(
            state=mock_app_state,
            clone_mode="smart",
            get_selected_usb_name=Mock(return_value=None),
            confirm_prompt=Mock(return_value=False),
            select_clone_mode=Mock(return_value="smart"),
            execute_clone_job=execute_clone_job,
        )

        execute_clone_job.assert_not_called()


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
            "rpi_usb_cloner.actions.drives.erase_actions.list_usb_disks", return_value=[]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.erase_actions.drives._get_repo_device_names",
            return_value=[],
        )
        mock_display = mocker.patch("rpi_usb_cloner.actions.drives.erase_actions.display")
        mocker.patch("time.sleep")

        get_selected = Mock(return_value=None)

        erase_actions.erase_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        mock_display.display_lines.assert_called()
        call_args = mock_display.display_lines.call_args[0][0]
        assert "No USB" in " ".join(call_args) or "No USB found" in str(call_args)


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
        mock_display = mocker.patch("rpi_usb_cloner.actions.drives.unmount_actions.display")

        get_selected = Mock(return_value=None)

        unmount_actions.unmount_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

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
        mock_display = mocker.patch("rpi_usb_cloner.actions.drives.unmount_actions.display")
        mocker.patch(
            "rpi_usb_cloner.actions.drives.unmount_actions.list_usb_disks",
            return_value=[],
        )

        get_selected = Mock(return_value="sda")

        unmount_actions.unmount_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        mock_display.display_lines.assert_called()


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
            "rpi_usb_cloner.actions.drives.repo_actions.list_usb_disks", return_value=[]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.repo_actions.drives._get_repo_device_names",
            return_value=set(),
        )
        mock_display = mocker.patch("rpi_usb_cloner.actions.drives.repo_actions.display")
        mocker.patch("time.sleep")

        get_selected = Mock(return_value=None)

        repo_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

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
            "rpi_usb_cloner.actions.drives.repo_actions.list_usb_disks", return_value=[device]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.repo_actions.drives._get_repo_device_names",
            return_value={"sda"},
        )
        mock_display = mocker.patch("rpi_usb_cloner.actions.drives.repo_actions.display")
        mocker.patch("time.sleep")

        get_selected = Mock(return_value=None)

        repo_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        mock_display.display_lines.assert_called()
        call_args = mock_display.display_lines.call_args[0][0]
        assert "CREATE REPO" in call_args or "No USB" in " ".join(call_args)

    def test_shows_no_partitions_error(
        self,
        mock_app_state,
        mock_usb_device,
        mock_gpio_repo,
        mock_screens_repo,
        mocker,
    ):
        """Test shows error when device has no partitions."""
        device = mock_usb_device.copy()
        device["name"] = "sda"
        device["children"] = []

        mocker.patch(
            "rpi_usb_cloner.actions.drives.repo_actions.list_usb_disks", return_value=[device]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.repo_actions.drives._get_repo_device_names",
            return_value=set(),
        )
        mock_menus = mocker.patch("rpi_usb_cloner.actions.drives.repo_actions.menus")
        mock_menus.wait_for_buttons_release = Mock()
        mock_menus.BUTTON_POLL_DELAY = 0.02

        mock_gpio_repo.poll_button_events = Mock(return_value=True)

        mocker.patch("time.sleep")

        get_selected = Mock(return_value="sda")

        repo_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        mock_screens_repo.render_error_screen.assert_called()
        call_kwargs = mock_screens_repo.render_error_screen.call_args[1]
        assert "No partitions" in call_kwargs["message"]

    def test_creates_flag_file_successfully(
        self,
        mock_app_state,
        mock_usb_device,
        mock_gpio_repo,
        mock_screens_repo,
        mocker,
        tmp_path,
    ):
        """Test successfully creates flag file on mounted partition."""
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
            "rpi_usb_cloner.actions.drives.repo_actions.list_usb_disks", return_value=[device]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.repo_actions.drives._get_repo_device_names",
            return_value=set(),
        )
        mock_invalidate = mocker.patch(
            "rpi_usb_cloner.actions.drives.repo_actions.drives.invalidate_repo_cache"
        )
        mock_menus = mocker.patch("rpi_usb_cloner.actions.drives.repo_actions.menus")
        mock_menus.wait_for_buttons_release = Mock()
        mock_menus.BUTTON_POLL_DELAY = 0.02
        mocker.patch("rpi_usb_cloner.actions.drives.repo_actions.display")

        mock_gpio_repo.poll_button_events = Mock(return_value=True)

        mocker.patch("time.sleep")

        get_selected = Mock(return_value="sda")

        repo_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        flag_path = mount_path / ".rpi-usb-cloner-image-repo"
        assert flag_path.exists()

        mock_invalidate.assert_called_once()

        mock_screens_repo.render_status_template.assert_called()

    def test_cancellation_does_not_create_flag_file(
        self,
        mock_app_state,
        mock_usb_device,
        mock_gpio_repo,
        mock_screens_repo,
        mocker,
        tmp_path,
    ):
        """Test cancelling does not create flag file."""
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
            "rpi_usb_cloner.actions.drives.repo_actions.list_usb_disks", return_value=[device]
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.repo_actions.drives._get_repo_device_names",
            return_value=set(),
        )
        mock_menus = mocker.patch("rpi_usb_cloner.actions.drives.repo_actions.menus")
        mock_menus.wait_for_buttons_release = Mock()
        mock_menus.BUTTON_POLL_DELAY = 0.02

        mock_gpio_repo.poll_button_events = Mock(return_value=False)

        mocker.patch("time.sleep")

        get_selected = Mock(return_value="sda")

        repo_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        flag_path = mount_path / ".rpi-usb-cloner-image-repo"
        assert not flag_path.exists()

    def test_uses_selected_device(
        self,
        mock_app_state,
        mock_usb_device,
        mock_gpio_repo,
        mock_screens_repo,
        mocker,
        tmp_path,
    ):
        """Test uses the selected device when specified."""
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
            "rpi_usb_cloner.actions.drives.repo_actions.list_usb_disks",
            return_value=[device_a, device_b],
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.repo_actions.drives._get_repo_device_names",
            return_value=set(),
        )
        mocker.patch(
            "rpi_usb_cloner.actions.drives.repo_actions.drives.invalidate_repo_cache"
        )
        mock_menus = mocker.patch("rpi_usb_cloner.actions.drives.repo_actions.menus")
        mock_menus.wait_for_buttons_release = Mock()
        mock_menus.BUTTON_POLL_DELAY = 0.02
        mocker.patch("rpi_usb_cloner.actions.drives.repo_actions.display")

        mock_gpio_repo.poll_button_events = Mock(return_value=True)

        mocker.patch("time.sleep")

        get_selected = Mock(return_value="sdb")

        repo_actions.create_repo_drive(
            state=mock_app_state,
            get_selected_usb_name=get_selected,
        )

        flag_path_a = mount_path_a / ".rpi-usb-cloner-image-repo"
        flag_path_b = mount_path_b / ".rpi-usb-cloner-image-repo"
        assert not flag_path_a.exists()
        assert flag_path_b.exists()


# ==============================================================================
# Backward Compatibility Tests
# ==============================================================================


class TestBackwardCompatibility:
    """Test that backward-compatible imports still work."""

    def test_drive_actions_exports_all_functions(self):
        """Test that drive_actions module exports all expected functions."""
        assert hasattr(drive_actions, "copy_drive")
        assert hasattr(drive_actions, "erase_drive")
        assert hasattr(drive_actions, "format_drive")
        assert hasattr(drive_actions, "drive_info")
        assert hasattr(drive_actions, "unmount_drive")
        assert hasattr(drive_actions, "create_repo_drive")
        assert hasattr(drive_actions, "prepare_copy_operation")
        assert hasattr(drive_actions, "execute_copy_operation")
