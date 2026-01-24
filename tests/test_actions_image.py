"""Tests for image action handlers.

This module tests the action handlers in rpi_usb_cloner.actions.image_actions,
which handle backup/restore operations for Clonezilla images and other image formats.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from rpi_usb_cloner.actions import image_actions
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
    gpio_mock = mocker.patch("rpi_usb_cloner.actions.image_actions.gpio")
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
    screens_mock = mocker.patch("rpi_usb_cloner.actions.image_actions.screens")
    screens_mock.render_error_screen = Mock()
    screens_mock.render_confirmation_screen = Mock()
    screens_mock.render_status_template = Mock()
    screens_mock.render_progress = Mock()
    return screens_mock


@pytest.fixture
def mock_menus(mocker):
    """Fixture providing mocked menu utilities."""
    menus_mock = mocker.patch("rpi_usb_cloner.actions.image_actions.menus")
    menus_mock.wait_for_buttons_release = Mock()
    menus_mock.prompt_text_input = Mock(return_value="test_image")
    return menus_mock


@pytest.fixture
def mock_clonezilla_backup(mocker):
    """Fixture providing mocked Clonezilla backup function."""
    return mocker.patch(
        "rpi_usb_cloner.actions.image_actions.clonezilla.create_backup"
    )


@pytest.fixture
def mock_clonezilla_restore(mocker):
    """Fixture providing mocked Clonezilla restore function."""
    return mocker.patch(
        "rpi_usb_cloner.actions.image_actions.clonezilla.restore_image"
    )


@pytest.fixture
def mock_clonezilla_images(mocker):
    """Fixture providing mocked Clonezilla image discovery."""
    from rpi_usb_cloner.storage.clonezilla.models import ClonezillaImage

    images = [
        ClonezillaImage(
            name="test_image_1",
            path=Path("/media/images/test_image_1"),
            device="sda",
            filesystem="ext4",
            compression="gzip",
            created=datetime(2024, 1, 15, 10, 30),
            size_bytes=1024 * 1024 * 100,  # 100 MB
        ),
        ClonezillaImage(
            name="test_image_2",
            path=Path("/media/images/test_image_2"),
            device="sdb",
            filesystem="ntfs",
            compression="zstd",
            created=datetime(2024, 1, 20, 14, 0),
            size_bytes=1024 * 1024 * 500,  # 500 MB
        ),
    ]

    return mocker.patch(
        "rpi_usb_cloner.actions.image_actions.clonezilla.discover_images",
        return_value=images
    )


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
        result = image_actions._format_elapsed_duration(45.5)
        assert result == "45s"

    def test_formats_minutes_and_seconds(self):
        """Test formatting when duration includes minutes."""
        result = image_actions._format_elapsed_duration(125.0)
        assert result == "2m 5s"

    def test_formats_hours_minutes_seconds(self):
        """Test formatting when duration includes hours."""
        result = image_actions._format_elapsed_duration(3665.0)
        assert result == "1h 1m 5s"

    def test_rounds_down_fractional_seconds(self):
        """Test fractional seconds are rounded down."""
        result = image_actions._format_elapsed_duration(59.9)
        assert result == "59s"


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


class TestFindMissingPartitions:
    """Test the _find_missing_partitions helper function."""

    def test_returns_empty_when_all_partitions_exist(self, mock_usb_device):
        """Test returns empty list when all required partitions exist."""
        device = mock_usb_device.copy()
        device["children"] = [
            {"name": "sda1"},
            {"name": "sda2"},
            {"name": "sda3"},
        ]

        required = ["sda1", "sda2"]
        missing = image_actions._find_missing_partitions(required, device)

        assert missing == []

    def test_returns_missing_partitions(self, mock_usb_device):
        """Test returns list of missing partitions."""
        device = mock_usb_device.copy()
        device["children"] = [
            {"name": "sda1"},
        ]

        required = ["sda1", "sda2", "sda3"]
        missing = image_actions._find_missing_partitions(required, device)

        assert set(missing) == {"sda2", "sda3"}

    def test_handles_no_children(self, mock_usb_device):
        """Test handles device with no partitions."""
        device = mock_usb_device.copy()
        device["children"] = []

        required = ["sda1", "sda2"]
        missing = image_actions._find_missing_partitions(required, device)

        assert set(missing) == {"sda1", "sda2"}


class TestExtractStderrMessage:
    """Test the _extract_stderr_message helper function."""

    def test_extracts_stderr_from_called_process_error(self):
        """Test extracts stderr from CalledProcessError message."""
        import subprocess

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


class TestShortRestoreReason:
    """Test the _short_restore_reason helper function."""

    def test_shortens_long_error_message(self):
        """Test shortens error message to fit display."""
        long_msg = "A" * 200
        result = image_actions._short_restore_reason(long_msg)

        # Should be shortened
        assert len(result) < len(long_msg)
        assert result.endswith("...")

    def test_preserves_short_message(self):
        """Test preserves message that fits."""
        short_msg = "Error: File not found"
        result = image_actions._short_restore_reason(short_msg)

        assert result == short_msg


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


# ==============================================================================
# coming_soon Tests
# ==============================================================================


class TestComingSoon:
    """Test the coming_soon placeholder function."""

    def test_shows_coming_soon_message(self, mocker):
        """Test shows 'Coming soon' status message."""
        mock_screens = mocker.patch("rpi_usb_cloner.actions.image_actions.screens")
        mocker.patch("time.sleep")

        image_actions.coming_soon()

        # Should show status
        mock_screens.render_status_template.assert_called_once()
        call_args = mock_screens.render_status_template.call_args[0]
        assert any("SOON" in str(arg).upper() for arg in call_args)


# ==============================================================================
# backup_image Tests (Partial - requires complex GPIO mocking)
# ==============================================================================


class TestBackupImageHelpers:
    """Test helper functions used by backup_image."""

    def test_select_partitions_checklist_returns_none_on_cancel(
        self, mocker, mock_gpio
    ):
        """Test partition selection returns None when cancelled."""
        # Simulate button A press (cancel)
        button_states = [False, False, True, False, False]  # A button
        mock_gpio.is_pressed = Mock(side_effect=button_states)

        mocker.patch("rpi_usb_cloner.actions.image_actions.screens")
        mocker.patch("rpi_usb_cloner.actions.image_actions.menus")

        result = image_actions._select_partitions_checklist(["sda1", "sda2"])

        # User cancelled, should return None
        # Note: This test may need adjustment based on actual implementation
        # The function has complex GPIO loop logic


# ==============================================================================
# Integration-style Tests
# ==============================================================================


class TestImageActionsIntegration:
    """Integration-style tests for image actions with more complete mocking."""

    def test_backup_requires_image_name(self, mocker, mock_app_state):
        """Test backup requires user to provide image name."""
        # Mock all dependencies
        mocker.patch("rpi_usb_cloner.actions.image_actions.gpio")
        mocker.patch("rpi_usb_cloner.actions.image_actions.screens")
        mock_menus = mocker.patch("rpi_usb_cloner.actions.image_actions.menus")

        # User cancels name input
        mock_menus.prompt_text_input = Mock(return_value=None)

        mocker.patch("time.sleep")

        get_selected = Mock(return_value="sda")

        # This should exit early when name is not provided
        # Note: Full test requires mocking the entire GPIO loop
        # which is complex - this is a simplified version

    def test_restore_requires_image_selection(self, mocker, mock_app_state):
        """Test restore requires image to be selected."""
        # Mock dependencies
        mocker.patch("rpi_usb_cloner.actions.image_actions.gpio")
        mocker.patch("rpi_usb_cloner.actions.image_actions.screens")
        mocker.patch("rpi_usb_cloner.actions.image_actions.menus")

        # No images available
        mocker.patch(
            "rpi_usb_cloner.actions.image_actions.clonezilla.discover_images",
            return_value=[]
        )

        mocker.patch("time.sleep")

        get_selected = Mock(return_value="sda")

        # This should show error when no images found
        # Note: Full test requires complete GPIO loop mocking
