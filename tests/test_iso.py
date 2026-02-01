"""Tests for ISO image writing functionality.

Platform-specific notes:
- Tests requiring os.geteuid() are skipped on Windows
- Tests requiring blockdev are skipped on Windows

Covers:
- restore_iso_image function
- _get_blockdev_size_bytes helper
- _get_device_size_bytes helper
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rpi_usb_cloner.storage.iso import (
    _get_blockdev_size_bytes,
    _get_device_size_bytes,
    restore_iso_image,
)


# Skip tests requiring POSIX features on Windows
skip_windows = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Requires POSIX features (geteuid, blockdev)",
)


class TestRestoreIsoImage:
    """Test restore_iso_image function."""

    @pytest.fixture
    def mock_iso_file(self, tmp_path):
        """Create a temporary ISO file."""
        iso_path = tmp_path / "test.iso"
        iso_path.write_bytes(b"fake iso content" * 100)
        return iso_path

    @skip_windows
    def test_not_root_raises(self, mock_iso_file):
        """Test that non-root execution raises RuntimeError."""
        with patch("os.geteuid", return_value=1000), pytest.raises(
            RuntimeError, match="Run as root"
        ):
            restore_iso_image(mock_iso_file, "sda")

    @skip_windows
    def test_iso_file_not_found(self):
        """Test that missing ISO file raises RuntimeError."""
        with patch("os.geteuid", return_value=0), pytest.raises(
            RuntimeError, match="ISO file not found"
        ):
            restore_iso_image(Path("/nonexistent.iso"), "sda")

    @skip_windows
    def test_target_device_too_small(self, mock_iso_file):
        """Test that too-small target device raises RuntimeError."""
        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.iso.resolve_device_node",
            return_value="/dev/sda",
        ), patch(
            "rpi_usb_cloner.storage.iso.devices.get_device_by_name",
            return_value={"name": "sda", "size": 100},
        ), patch(
            "rpi_usb_cloner.storage.iso.devices.unmount_device",
            return_value=True,
        ), pytest.raises(
            RuntimeError, match="Target device too small"
        ):
            restore_iso_image(mock_iso_file, "sda")

    @skip_windows
    def test_dd_not_found(self, mock_iso_file):
        """Test that missing dd command raises RuntimeError."""
        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.iso.resolve_device_node",
            return_value="/dev/sda",
        ), patch(
            "rpi_usb_cloner.storage.iso.devices.get_device_by_name",
            return_value=None,
        ), patch(
            "rpi_usb_cloner.storage.iso.shutil.which",
            return_value=None,
        ), pytest.raises(
            RuntimeError, match="dd not found"
        ):
            restore_iso_image(mock_iso_file, "sda")

    @skip_windows
    def test_unmount_failure_raises(self, mock_iso_file):
        """Test that unmount failure raises RuntimeError."""
        device_info = {"name": "sda", "size": 1000000000}
        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.iso.resolve_device_node",
            return_value="/dev/sda",
        ), patch(
            "rpi_usb_cloner.storage.iso.devices.get_device_by_name",
            return_value=device_info,
        ), patch(
            "rpi_usb_cloner.storage.iso.devices.unmount_device",
            return_value=False,
        ), pytest.raises(
            RuntimeError, match="Failed to unmount target device"
        ):
            restore_iso_image(mock_iso_file, "sda")

    @skip_windows
    def test_successful_iso_restore(self, mock_iso_file, mocker):
        """Test successful ISO restore with progress callback."""
        device_info = {"name": "sda", "size": 1000000000}
        progress_calls = []

        def progress_callback(messages, progress):
            progress_calls((messages, progress))

        with patch("os.geteuid", return_value=0):
            mocker.patch(
                "rpi_usb_cloner.storage.iso.resolve_device_node",
                return_value="/dev/sda",
            )
            mocker.patch(
                "rpi_usb_cloner.storage.iso.devices.get_device_by_name",
                return_value=device_info,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.iso.devices.unmount_device",
                return_value=True,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.iso.shutil.which",
                side_effect=lambda cmd: f"/usr/bin/{cmd}" if cmd == "dd" else None,
            )
            mock_run = mocker.patch(
                "rpi_usb_cloner.storage.iso.clone.run_checked_with_streaming_progress"
            )

            restore_iso_image(mock_iso_file, "sda", progress_callback=progress_callback)

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert "test.iso" in call_args.kwargs["title"]
            assert call_args.kwargs["total_bytes"] == mock_iso_file.stat().st_size

    @skip_windows
    def test_iso_restore_with_device_size_from_blockdev(self, mock_iso_file, mocker):
        """Test ISO restore when device size comes from blockdev."""
        with patch("os.geteuid", return_value=0):
            mocker.patch(
                "rpi_usb_cloner.storage.iso.resolve_device_node",
                return_value="/dev/sda",
            )
            mocker.patch(
                "rpi_usb_cloner.storage.iso.devices.get_device_by_name",
                return_value=None,  # No device info, will use blockdev
            )
            mocker.patch(
                "rpi_usb_cloner.storage.iso.devices.unmount_device",
                return_value=True,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.iso.shutil.which",
                side_effect=lambda cmd: (
                    f"/usr/bin/{cmd}" if cmd in ["dd", "blockdev"] else None
                ),
            )
            mocker.patch(
                "rpi_usb_cloner.storage.iso.subprocess.run",
                return_value=Mock(returncode=0, stdout="1000000000"),
            )
            mock_run = mocker.patch(
                "rpi_usb_cloner.storage.iso.clone.run_checked_with_streaming_progress"
            )

            restore_iso_image(mock_iso_file, "sda")

            mock_run.assert_called_once()


class TestGetBlockdevSizeBytes:
    """Test _get_blockdev_size_bytes function."""

    def test_blockdev_success(self):
        """Test successful blockdev size retrieval."""
        with patch(
            "rpi_usb_cloner.storage.iso.shutil.which", return_value="/sbin/blockdev"
        ), patch(
            "rpi_usb_cloner.storage.iso.subprocess.run",
            return_value=Mock(returncode=0, stdout="1073741824\n"),
        ) as mock_run:
            result = _get_blockdev_size_bytes("/dev/sda")
            assert result == 1073741824
            mock_run.assert_called_once_with(
                ["/sbin/blockdev", "--getsize64", "/dev/sda"],
                capture_output=True,
                text=True,
            )

    def test_blockdev_not_found(self):
        """Test when blockdev command is not available."""
        with patch("rpi_usb_cloner.storage.iso.shutil.which", return_value=None):
            result = _get_blockdev_size_bytes("/dev/sda")
            assert result is None

    def test_blockdev_failure(self):
        """Test when blockdev command fails."""
        with patch(
            "rpi_usb_cloner.storage.iso.shutil.which", return_value="/sbin/blockdev"
        ), patch(
            "rpi_usb_cloner.storage.iso.subprocess.run",
            return_value=Mock(returncode=1, stdout=""),
        ):
            result = _get_blockdev_size_bytes("/dev/sda")
            assert result is None

    def test_blockdev_invalid_output(self):
        """Test when blockdev returns non-numeric output."""
        with patch(
            "rpi_usb_cloner.storage.iso.shutil.which", return_value="/sbin/blockdev"
        ), patch(
            "rpi_usb_cloner.storage.iso.subprocess.run",
            return_value=Mock(returncode=0, stdout="not a number"),
        ):
            result = _get_blockdev_size_bytes("/dev/sda")
            assert result is None


class TestGetDeviceSizeBytes:
    """Test _get_device_size_bytes function."""

    def test_from_device_info(self):
        """Test getting size from device info dict."""
        device_info = {"name": "sda", "size": "500000000"}
        result = _get_device_size_bytes(device_info, "/dev/sda")
        assert result == 500000000

    def test_from_device_info_int(self):
        """Test getting size from device info with int size."""
        device_info = {"name": "sda", "size": 500000000}
        result = _get_device_size_bytes(device_info, "/dev/sda")
        assert result == 500000000

    def test_fallback_to_blockdev(self):
        """Test fallback to blockdev when device info has no size."""
        device_info = {"name": "sda"}
        with patch(
            "rpi_usb_cloner.storage.iso._get_blockdev_size_bytes",
            return_value=1073741824,
        ) as mock_blockdev:
            result = _get_device_size_bytes(device_info, "/dev/sda")
            assert result == 1073741824
            mock_blockdev.assert_called_once_with("/dev/sda")

    def test_none_device_info_uses_blockdev(self):
        """Test using blockdev when device info is None."""
        with patch(
            "rpi_usb_cloner.storage.iso._get_blockdev_size_bytes",
            return_value=1073741824,
        ) as mock_blockdev:
            result = _get_device_size_bytes(None, "/dev/sda")
            assert result == 1073741824
            mock_blockdev.assert_called_once_with("/dev/sda")
