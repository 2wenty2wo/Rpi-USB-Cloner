"""Tests for ImageUSB .BIN file restoration operations.

Covers:
- restore_imageusb_file function
- restore_imageusb_file_simple function
- Validation and error handling
- Progress callback integration

Platform-specific notes:
- Tests requiring os.geteuid() are skipped on Windows
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch

import pytest

from rpi_usb_cloner.storage.imageusb.restore import (
    restore_imageusb_file,
    restore_imageusb_file_simple,
)


# Skip tests requiring POSIX features on Windows
skip_windows = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Requires POSIX features (geteuid)",
)


class TestRestoreImageUSBFile:
    """Test restore_imageusb_file function."""

    @pytest.fixture
    def mock_bin_file(self, tmp_path):
        """Create a temporary ImageUSB .BIN file."""
        bin_path = tmp_path / "test.bin"
        # Create content with at least 512 bytes header + some data
        bin_path.write_bytes(b"IMGUSB" + b"\x00" * 506 + b"disk data" * 100)
        return bin_path

    @skip_windows
    def test_not_root_raises_permission_error(self, mock_bin_file):
        """Test that non-root execution raises PermissionError."""
        with patch("os.geteuid", return_value=1000), pytest.raises(
            PermissionError, match="Must run as root"
        ):
            restore_imageusb_file(mock_bin_file, "sda")

    @skip_windows
    def test_invalid_image_file_raises(self, tmp_path):
        """Test that invalid image file raises RuntimeError."""
        invalid_file = tmp_path / "invalid.bin"
        invalid_file.write_text("not a valid imageusb file")

        with patch("os.geteuid", return_value=0), pytest.raises(
            RuntimeError, match="Invalid ImageUSB file"
        ):
            restore_imageusb_file(invalid_file, "sda")

    @skip_windows
    def test_device_not_found_raises(self, mock_bin_file):
        """Test that missing target device raises RuntimeError."""
        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.imageusb.restore.validate_imageusb_file",
            return_value=None,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.resolve_device_node",
            return_value="/dev/sda",
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.devices.get_device_by_name",
            return_value=None,
        ), pytest.raises(
            RuntimeError, match="Target device not found"
        ):
            restore_imageusb_file(mock_bin_file, "sda")

    @skip_windows
    def test_non_removable_device_raises(self, mock_bin_file):
        """Test that non-removable device raises RuntimeError."""
        device_info = {"name": "sda", "rm": "0"}
        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.imageusb.restore.validate_imageusb_file",
            return_value=None,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.resolve_device_node",
            return_value="/dev/sda",
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.devices.get_device_by_name",
            return_value=device_info,
        ), pytest.raises(
            RuntimeError, match="not removable"
        ):
            restore_imageusb_file(mock_bin_file, "sda")

    @skip_windows
    def test_removable_device_with_rm_one(self, mock_bin_file):
        """Test that removable device (rm=1) is accepted."""
        device_info = {"name": "sda", "rm": "1"}
        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.imageusb.restore.validate_imageusb_file",
            return_value=None,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.resolve_device_node",
            return_value="/dev/sda",
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.devices.get_device_by_name",
            return_value=device_info,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.devices.unmount_device",
            return_value=True,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.shutil.which",
            return_value=None,  # Will fail on dd not found
        ), pytest.raises(
            RuntimeError, match="dd command not found"
        ):
            restore_imageusb_file(mock_bin_file, "sda")

    @skip_windows
    def test_unmount_failure_raises(self, mock_bin_file):
        """Test that unmount failure raises RuntimeError."""
        device_info = {"name": "sda", "rm": "1"}
        progress_calls = []

        def progress_callback(messages, progress):
            progress_calls.append((messages, progress))

        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.imageusb.restore.validate_imageusb_file",
            return_value=None,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.resolve_device_node",
            return_value="/dev/sda",
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.devices.get_device_by_name",
            return_value=device_info,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.devices.unmount_device",
            return_value=False,
        ), pytest.raises(
            RuntimeError, match="Failed to unmount"
        ):
            restore_imageusb_file(
                mock_bin_file,
                "sda",
                progress_callback=progress_callback,
            )

    @skip_windows
    def test_dd_not_found_raises(self, mock_bin_file):
        """Test that missing dd command raises RuntimeError."""
        device_info = {"name": "sda", "rm": "1"}
        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.imageusb.restore.validate_imageusb_file",
            return_value=None,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.resolve_device_node",
            return_value="/dev/sda",
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.devices.get_device_by_name",
            return_value=device_info,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.devices.unmount_device",
            return_value=True,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.shutil.which",
            return_value=None,
        ), pytest.raises(
            RuntimeError, match="dd command not found"
        ):
            restore_imageusb_file(mock_bin_file, "sda")

    @skip_windows
    def test_successful_restore(self, mock_bin_file, mocker):
        """Test successful ImageUSB restore with progress callback."""
        device_info = {"name": "sda", "rm": "1"}
        progress_calls = []

        def progress_callback(messages, progress):
            progress_calls.append((messages, progress))

        with patch("os.geteuid", return_value=0):
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.validate_imageusb_file",
                return_value=None,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.resolve_device_node",
                return_value="/dev/sda",
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.devices.get_device_by_name",
                return_value=device_info,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.devices.unmount_device",
                return_value=True,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.shutil.which",
                return_value="/bin/dd",
            )
            mock_run = mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.run_checked_with_streaming_progress"
            )

            restore_imageusb_file(
                mock_bin_file, "sda", progress_callback=progress_callback
            )

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args.kwargs["title"] == "Restoring test.bin"
            assert call_args.kwargs["subtitle"] == "to sda"

    @skip_windows
    def test_restore_called_process_error(self, mock_bin_file, mocker):
        """Test handling of CalledProcessError during restore."""
        device_info = {"name": "sda", "rm": "1"}

        with patch("os.geteuid", return_value=0):
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.validate_imageusb_file",
                return_value=None,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.resolve_device_node",
                return_value="/dev/sda",
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.devices.get_device_by_name",
                return_value=device_info,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.devices.unmount_device",
                return_value=True,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.shutil.which",
                return_value="/bin/dd",
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.run_checked_with_streaming_progress",
                side_effect=subprocess.CalledProcessError(
                    1, ["dd"], stderr="dd failed"
                ),
            )

            with pytest.raises(RuntimeError, match="dd command failed"):
                restore_imageusb_file(mock_bin_file, "sda")

    @skip_windows
    def test_restore_generic_exception(self, mock_bin_file, mocker):
        """Test handling of generic Exception during restore."""
        device_info = {"name": "sda", "rm": "1"}

        with patch("os.geteuid", return_value=0):
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.validate_imageusb_file",
                return_value=None,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.resolve_device_node",
                return_value="/dev/sda",
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.devices.get_device_by_name",
                return_value=device_info,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.devices.unmount_device",
                return_value=True,
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.shutil.which",
                return_value="/bin/dd",
            )
            mocker.patch(
                "rpi_usb_cloner.storage.imageusb.restore.run_checked_with_streaming_progress",
                side_effect=OSError("disk error"),
            )

            with pytest.raises(RuntimeError, match="Restoration failed"):
                restore_imageusb_file(mock_bin_file, "sda")

    @skip_windows
    def test_cannot_read_file_size(self, tmp_path):
        """Test handling of OSError when reading file size."""

        # Create a mock that raises OSError on stat()
        class MockPath:
            def stat(self):
                raise OSError("Permission denied")

        device_info = {"name": "sda", "rm": "1"}
        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.imageusb.restore.validate_imageusb_file",
            return_value=None,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.resolve_device_node",
            return_value="/dev/sda",
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.devices.get_device_by_name",
            return_value=device_info,
        ), pytest.raises(
            RuntimeError, match="Cannot read file size"
        ):
            restore_imageusb_file(MockPath(), "sda")

    @skip_windows
    def test_rm_value_none_defaults_to_not_removable(self, mock_bin_file):
        """Test that rm=None defaults to non-removable."""
        device_info = {"name": "sda", "rm": None}
        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.imageusb.restore.validate_imageusb_file",
            return_value=None,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.resolve_device_node",
            return_value="/dev/sda",
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.devices.get_device_by_name",
            return_value=device_info,
        ), pytest.raises(
            RuntimeError, match="not removable"
        ):
            restore_imageusb_file(mock_bin_file, "sda")

    @skip_windows
    def test_rm_value_invalid_string_defaults_to_not_removable(self, mock_bin_file):
        """Test that rm='invalid' defaults to non-removable."""
        device_info = {"name": "sda", "rm": "invalid"}
        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.imageusb.restore.validate_imageusb_file",
            return_value=None,
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.resolve_device_node",
            return_value="/dev/sda",
        ), patch(
            "rpi_usb_cloner.storage.imageusb.restore.devices.get_device_by_name",
            return_value=device_info,
        ), pytest.raises(
            RuntimeError, match="not removable"
        ):
            restore_imageusb_file(mock_bin_file, "sda")


class TestRestoreImageUSBFileSimple:
    """Test restore_imageusb_file_simple function."""

    def test_simple_api_calls_full_api(self, tmp_path, mocker):
        """Test that simple API calls the full API with no callback."""
        bin_path = tmp_path / "test.bin"
        bin_path.write_bytes(b"IMGUSB" + b"\x00" * 506 + b"data")

        mock_restore = mocker.patch(
            "rpi_usb_cloner.storage.imageusb.restore.restore_imageusb_file"
        )

        restore_imageusb_file_simple(bin_path, "sda")

        mock_restore.assert_called_once_with(bin_path, "sda", progress_callback=None)
