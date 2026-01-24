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
