"""Tests for image action handlers.

This module tests the action handlers in rpi_usb_cloner.actions.image_actions,
which handle backup/restore operations for Clonezilla images and other image formats.
"""

from datetime import datetime
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest

from rpi_usb_cloner.actions import image_actions
from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.domain import ImageRepo


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
    gpio_mock = mocker.patch("rpi_usb_cloner.actions.image_actions.gpio")
    gpio_mock.PIN_L = 27
    gpio_mock.PIN_R = 23
    gpio_mock.PIN_A = 5
    gpio_mock.PIN_B = 6
    return gpio_mock


# ==============================================================================
# Helper Functions Tests
# ==============================================================================


class TestLogDebug:
    """Test the _log_debug helper function."""

    def test_logs_when_callback_provided(self):
        """Test logging when callback is provided."""
        log_callback = Mock()
        image_actions._log_debug(log_callback, "Test message")
        log_callback.assert_called_once_with("Test message")

    def test_no_error_when_callback_is_none(self):
        """Test no error when callback is None."""
        # Should not raise any exception
        image_actions._log_debug(None, "Test message")


class TestFormatElapsedDuration:
    """Test the _format_elapsed_duration helper function."""

    def test_formats_seconds_only(self):
        """Test formatting when duration is less than 1 minute."""
        # Function uses round(), so 45.5 -> 46
        result = image_actions._format_elapsed_duration(45.4)
        assert result == "45s"

    def test_formats_minutes_and_seconds(self):
        """Test formatting when duration includes minutes."""
        result = image_actions._format_elapsed_duration(125.0)
        assert result == "2m 5s"

    def test_formats_hours_minutes_seconds(self):
        """Test formatting when duration includes hours."""
        result = image_actions._format_elapsed_duration(3665.0)
        assert result == "1h 1m 5s"

    def test_rounds_fractional_seconds(self):
        """Test fractional seconds are rounded."""
        # 59.4 rounds to 59
        result = image_actions._format_elapsed_duration(59.4)
        assert result == "59s"
        # 59.5 rounds to 60 which is 1m 0s
        result = image_actions._format_elapsed_duration(59.5)
        assert result == "1m 0s"


class TestImageNameValidation:
    """Test image name validation helper."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("backup_01", True),
            ("backup-01", True),
            ("backup 01", False),
            ("", False),
            ("invalid!", False),
        ],
    )
    def test_is_valid_image_name(self, name, expected):
        """Test image name validation rules."""
        assert image_actions._is_valid_image_name(name) is expected


class TestApplyConfirmationSelection:
    """Test confirmation selection logic."""

    def test_switches_to_yes(self):
        """Test selecting right changes to YES."""
        assert (
            image_actions._apply_confirmation_selection(app_state.CONFIRM_NO, "right")
            == app_state.CONFIRM_YES
        )

    def test_switches_to_no(self):
        """Test selecting left changes to NO."""
        assert (
            image_actions._apply_confirmation_selection(app_state.CONFIRM_YES, "left")
            == app_state.CONFIRM_NO
        )

    def test_ignores_invalid_direction(self):
        """Test invalid moves keep selection unchanged."""
        assert (
            image_actions._apply_confirmation_selection(app_state.CONFIRM_NO, "left")
            == app_state.CONFIRM_NO
        )


class TestConfirmPrompt:
    """Test confirmation prompt with injected poller."""

    def test_confirm_returns_true(
        self,
        mock_gpio,
    ):
        """Test confirmation returns True when selecting YES."""
        mock_wait = Mock()
        mock_render = Mock()

        def poll_button_events(callbacks, poll_interval, loop_callback):
            loop_callback()
            callbacks[mock_gpio.PIN_R]()
            return callbacks[mock_gpio.PIN_B]()

        result = image_actions._confirm_prompt(
            log_debug=None,
            title="CONFIRM",
            prompt_lines=["Line 1"],
            default=app_state.CONFIRM_NO,
            poll_button_events=poll_button_events,
            wait_for_buttons_release=mock_wait,
            render_confirmation_screen=mock_render,
        )

        assert result is True
        mock_wait.assert_called_once()

    def test_cancel_returns_false(self, mock_gpio):
        """Test cancellation returns False."""
        mock_wait = Mock()
        mock_render = Mock()

        def poll_button_events(callbacks, poll_interval, loop_callback):
            loop_callback()
            return callbacks[mock_gpio.PIN_A]()

        result = image_actions._confirm_prompt(
            log_debug=None,
            title="CONFIRM",
            prompt_lines=["Line 1"],
            default=app_state.CONFIRM_NO,
            poll_button_events=poll_button_events,
            wait_for_buttons_release=mock_wait,
            render_confirmation_screen=mock_render,
        )

        assert result is False
        mock_wait.assert_called_once()


class TestRepoDeviceFiltering:
    """Test filtering out repo devices based on mountpoints."""

    def test_detects_repo_devices(self, mock_usb_device):
        """Test repo device detection from mountpoints."""
        repo = ImageRepo(path=PurePosixPath("/media/usb/repo"), drive_name="sda")
        device = mock_usb_device.copy()
        device["name"] = "sda"
        device["children"] = [
            {"name": "sda1", "mountpoint": "/media/usb"},
        ]

        repo_devices = image_actions._find_repo_device_names([device], [repo])

        assert repo_devices == {"sda"}

    def test_filters_non_repo_devices(self, mock_usb_device):
        """Test filtering returns only non-repo devices."""
        repo = ImageRepo(path=PurePosixPath("/media/usb/repo"), drive_name="sda")
        repo_device = mock_usb_device.copy()
        repo_device["name"] = "sda"
        repo_device["children"] = [
            {"name": "sda1", "mountpoint": "/media/usb"},
        ]
        other_device = mock_usb_device.copy()
        other_device["name"] = "sdb"
        other_device["children"] = [
            {"name": "sdb1", "mountpoint": "/media/other"},
        ]

        filtered = image_actions._filter_non_repo_devices(
            [repo_device, other_device], [repo]
        )

        assert [device["name"] for device in filtered] == ["sdb"]


class TestRepoDriveDetection:
    """Test repo drive safety checks."""

    def test_detects_repo_drive_by_mountpoint(self, mock_usb_device):
        """Test repo drive detection when mountpoint matches repo path."""
        repo_path = PurePosixPath("/media/usb/repo")
        device = mock_usb_device.copy()
        device["children"] = [
            {"name": "sda1", "mountpoint": "/media/usb"},
        ]

        assert image_actions._is_repo_drive(device, repo_path) is True

    def test_returns_false_for_non_repo_mountpoints(self, mock_usb_device):
        """Test repo drive detection returns False for unrelated mountpoints."""
        repo_path = PurePosixPath("/media/other/repo")
        device = mock_usb_device.copy()
        device["children"] = [
            {"name": "sda1", "mountpoint": "/media/usb"},
        ]

        assert image_actions._is_repo_drive(device, repo_path) is False

    def test_returns_false_when_unmounted(self, mock_usb_device):
        """Test repo drive detection returns False for unmounted devices."""
        repo_path = PurePosixPath("/media/usb/repo")
        device = mock_usb_device.copy()
        device["mountpoint"] = None
        device["children"] = []

        assert image_actions._is_repo_drive(device, repo_path) is False


class TestCollectMountpoints:
    """Test the _collect_mountpoints helper function."""

    def test_returns_empty_set_for_unmounted_device(self, mock_usb_device):
        """Test returns empty set when device has no mountpoints."""
        device = mock_usb_device.copy()
        device["mountpoint"] = None
        device["children"] = []

        mountpoints = image_actions._collect_mountpoints(device)
        assert mountpoints == set()

    def test_returns_device_mountpoint(self, mock_usb_device):
        """Test returns device's own mountpoint."""
        device = mock_usb_device.copy()
        device["mountpoint"] = "/media/usb"
        device["children"] = []

        mountpoints = image_actions._collect_mountpoints(device)
        assert mountpoints == {"/media/usb"}

    def test_returns_partition_mountpoints(self, mock_usb_device):
        """Test returns all partition mountpoints."""
        device = mock_usb_device.copy()
        device["mountpoint"] = None
        device["children"] = [
            {"name": "sda1", "mountpoint": "/media/usb1"},
            {"name": "sda2", "mountpoint": "/media/usb2"},
        ]

        mountpoints = image_actions._collect_mountpoints(device)
        assert mountpoints == {"/media/usb1", "/media/usb2"}


class TestExtractStderrMessage:
    """Test the _extract_stderr_message helper function."""

    def test_extracts_stderr_from_called_process_error(self):
        """Test extracts stderr from CalledProcessError message."""
        error_msg = "Command failed with stderr: Permission denied"
        result = image_actions._extract_stderr_message(error_msg)

        # Should extract the part after "stderr:"
        assert result is not None
        assert "Permission denied" in result

    def test_returns_none_when_no_stderr_in_message(self):
        """Test returns None when message doesn't contain stderr."""
        result = image_actions._extract_stderr_message("Generic error message")
        assert result is None

    def test_handles_empty_message(self):
        """Test handles empty message gracefully."""
        result = image_actions._extract_stderr_message("")
        assert result is None


class TestFormatRestoreErrorLines:
    """Test the _format_restore_error_lines helper function."""

    def test_formats_generic_exception(self):
        """Test formats generic exception."""
        error = Exception("Test error message")
        lines = image_actions._format_restore_error_lines(error)

        assert isinstance(lines, list)
        assert len(lines) > 0
        assert any("Test error message" in line for line in lines)

    def test_formats_runtime_error(self):
        """Test formats RuntimeError."""
        error = RuntimeError("Runtime error occurred")
        lines = image_actions._format_restore_error_lines(error)

        assert isinstance(lines, list)
        assert any("Runtime error occurred" in line for line in lines)


class TestComingSoon:
    """Test the coming_soon placeholder function."""

    def test_shows_coming_soon_message(self, mocker):
        """Test shows 'Coming soon' status message."""
        mock_screens = mocker.patch("rpi_usb_cloner.actions.image_actions.screens")

        image_actions.coming_soon()

        # Should call show_coming_soon
        mock_screens.show_coming_soon.assert_called_once()


# Note: Many image action functions like backup_image() and restore_image()
# have complex GPIO polling loops and threading patterns that are difficult
# to unit test. These require integration or end-to-end testing with
# sophisticated mocking of GPIO button sequences and progress tracking.
#
# The tests above cover the testable helper functions that handle formatting,
# error extraction, and simple validation logic.
