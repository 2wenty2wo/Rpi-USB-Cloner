"""Tests for ImageUSB .BIN file detection and restoration."""

from unittest.mock import patch

import pytest

from rpi_usb_cloner.storage.imageusb.detection import (
    IMAGEUSB_HEADER_SIZE,
    IMAGEUSB_SIGNATURE,
    get_imageusb_metadata,
    is_imageusb_file,
    validate_imageusb_file,
)


class TestImageUSBDetection:
    """Test ImageUSB file detection."""

    def test_is_imageusb_file_valid(self, tmp_path):
        """Test detection of valid ImageUSB file."""
        # Create a mock ImageUSB file with correct signature
        bin_file = tmp_path / "test.bin"

        # Write ImageUSB signature + 512 bytes header + some data
        with bin_file.open("wb") as f:
            f.write(IMAGEUSB_SIGNATURE)  # First 16 bytes
            f.write(b"\x00" * (IMAGEUSB_HEADER_SIZE - 16))  # Rest of header
            f.write(b"\x55\xaa" * 256)  # Some dummy MBR data

        assert is_imageusb_file(bin_file) is True

    def test_is_imageusb_file_invalid_signature(self, tmp_path):
        """Test detection rejects file with wrong signature."""
        bin_file = tmp_path / "test.bin"

        # Write wrong signature
        with bin_file.open("wb") as f:
            f.write(b"WRONG_SIGNATURE!")
            f.write(b"\x00" * 496)

        assert is_imageusb_file(bin_file) is False

    def test_is_imageusb_file_nonexistent(self, tmp_path):
        """Test detection handles non-existent file."""
        bin_file = tmp_path / "nonexistent.bin"
        assert is_imageusb_file(bin_file) is False

    def test_is_imageusb_file_directory(self, tmp_path):
        """Test detection handles directory path."""
        assert is_imageusb_file(tmp_path) is False

    def test_validate_imageusb_file_valid(self, tmp_path):
        """Test validation of valid ImageUSB file."""
        bin_file = tmp_path / "test.bin"

        # Create valid file with signature, header, and MBR
        with bin_file.open("wb") as f:
            # Write signature
            f.write(IMAGEUSB_SIGNATURE)
            # Write rest of header (496 bytes)
            f.write(b"\x00" * (IMAGEUSB_HEADER_SIZE - 16))
            # Write MBR (first 512 bytes after header)
            mbr = bytearray(512)
            mbr[510:512] = b"\x55\xaa"  # MBR boot signature
            f.write(bytes(mbr))

        error = validate_imageusb_file(bin_file)
        assert error is None

    def test_validate_imageusb_file_too_small(self, tmp_path):
        """Test validation rejects file smaller than header."""
        bin_file = tmp_path / "test.bin"

        with bin_file.open("wb") as f:
            f.write(IMAGEUSB_SIGNATURE)
            f.write(b"\x00" * 100)  # Only 116 bytes total (< 512)

        error = validate_imageusb_file(bin_file)
        assert error is not None
        assert "too small" in error.lower()

    def test_validate_imageusb_file_invalid_signature(self, tmp_path):
        """Test validation rejects file with invalid signature."""
        bin_file = tmp_path / "test.bin"

        with bin_file.open("wb") as f:
            f.write(b"WRONG!" + b"\x00" * 10)
            f.write(b"\x00" * (IMAGEUSB_HEADER_SIZE - 16))
            f.write(b"\x00" * 512)

        error = validate_imageusb_file(bin_file)
        assert error is not None
        assert "signature" in error.lower()

    def test_validate_imageusb_file_nonexistent(self, tmp_path):
        """Test validation handles non-existent file."""
        bin_file = tmp_path / "nonexistent.bin"

        error = validate_imageusb_file(bin_file)
        assert error is not None
        assert "does not exist" in error.lower()

    def test_get_imageusb_metadata_valid(self, tmp_path):
        """Test metadata extraction from valid file."""
        bin_file = tmp_path / "test.bin"

        # Create valid file
        total_size = 1024 * 1024  # 1 MB
        with bin_file.open("wb") as f:
            f.write(IMAGEUSB_SIGNATURE)
            f.write(b"\x00" * (total_size - 16))

        metadata = get_imageusb_metadata(bin_file)

        assert metadata["name"] == "test.bin"
        assert metadata["size_bytes"] == total_size
        assert metadata["data_size_bytes"] == total_size - IMAGEUSB_HEADER_SIZE
        assert metadata["valid"] is True
        assert metadata["error"] is None

    def test_get_imageusb_metadata_invalid(self, tmp_path):
        """Test metadata extraction from invalid file."""
        bin_file = tmp_path / "test.bin"

        # Create invalid file (wrong signature)
        with bin_file.open("wb") as f:
            f.write(b"WRONG!")
            f.write(b"\x00" * 1000)

        metadata = get_imageusb_metadata(bin_file)

        assert metadata["name"] == "test.bin"
        assert metadata["valid"] is False
        assert metadata["error"] is not None


class TestImageUSBRestore:
    """Test ImageUSB file restoration."""

    @pytest.fixture
    def mock_device(self):
        """Create a mock USB device."""
        return {
            "name": "sdb",
            "size": 8 * 1024**3,  # 8 GB
            "rm": "1",  # Removable
            "vendor": "Test",
            "model": "Drive",
        }

    @pytest.fixture
    def valid_bin_file(self, tmp_path):
        """Create a valid ImageUSB .BIN file."""
        bin_file = tmp_path / "test.bin"

        # Create valid file with signature, header, and MBR
        total_size = 1024 * 1024  # 1 MB
        with bin_file.open("wb") as f:
            # Write signature
            f.write(IMAGEUSB_SIGNATURE)
            # Write rest of header
            f.write(b"\x00" * (IMAGEUSB_HEADER_SIZE - 16))
            # Write MBR
            mbr = bytearray(512)
            mbr[510:512] = b"\x55\xaa"
            f.write(bytes(mbr))
            # Write remaining data
            remaining = total_size - IMAGEUSB_HEADER_SIZE - 512
            f.write(b"\x00" * remaining)

        return bin_file

    def test_restore_not_root(self, valid_bin_file, mock_device):
        """Test restoration fails if not running as root."""
        import os

        if not hasattr(os, "geteuid"):
            pytest.skip("geteuid not available on this platform")

        from rpi_usb_cloner.storage.imageusb.restore import restore_imageusb_file

        with patch("os.geteuid", return_value=1000), pytest.raises(
            PermissionError, match="Must run as root"
        ):
            restore_imageusb_file(valid_bin_file, "sdb")

    def test_restore_invalid_file(self, tmp_path, mock_device):
        """Test restoration fails with invalid file."""
        import os

        if not hasattr(os, "geteuid"):
            pytest.skip("geteuid not available on this platform")

        from rpi_usb_cloner.storage.imageusb.restore import restore_imageusb_file

        # Create invalid file
        invalid_file = tmp_path / "invalid.bin"
        with invalid_file.open("wb") as f:
            f.write(b"NOT_IMAGEUSB")

        with patch("os.geteuid", return_value=0), pytest.raises(
            RuntimeError, match="Invalid ImageUSB file"
        ):
            restore_imageusb_file(invalid_file, "sdb")

    def test_restore_non_removable_device(self, valid_bin_file):
        """Test restoration fails on non-removable device."""
        import os

        if not hasattr(os, "geteuid"):
            pytest.skip("geteuid not available on this platform")

        from rpi_usb_cloner.storage.imageusb.restore import restore_imageusb_file

        # Mock non-removable device
        non_removable = {
            "name": "sda",
            "size": 500 * 1024**3,
            "rm": "0",  # Not removable
        }

        with patch("os.geteuid", return_value=0), patch(
            "rpi_usb_cloner.storage.devices.get_device_by_name",
            return_value=non_removable,
        ), patch(
            "rpi_usb_cloner.storage.clone.models.resolve_device_node",
            return_value="/dev/sda",
        ), pytest.raises(
            RuntimeError, match="not removable"
        ):
            restore_imageusb_file(valid_bin_file, "sda")

    def test_restore_success(self, valid_bin_file, mock_device, mocker):
        """Test successful restoration."""
        import os

        if not hasattr(os, "geteuid"):
            pytest.skip("geteuid not available on this platform")

        from rpi_usb_cloner.storage.imageusb.restore import restore_imageusb_file

        # Mock all dependencies
        mocker.patch("os.geteuid", return_value=0)
        mocker.patch(
            "rpi_usb_cloner.storage.clone.models.resolve_device_node",
            return_value="/dev/sdb",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.devices.get_device_by_name",
            return_value=mock_device,
        )
        mocker.patch("rpi_usb_cloner.storage.devices.unmount_device", return_value=True)
        mocker.patch("shutil.which", return_value="/usr/bin/dd")

        # Mock the run_checked_with_streaming_progress function
        mock_run = mocker.patch(
            "rpi_usb_cloner.storage.imageusb.restore.run_checked_with_streaming_progress"
        )

        # Call restore
        restore_imageusb_file(valid_bin_file, "sdb")

        # Verify dd command was called correctly
        mock_run.assert_called_once()
        args = mock_run.call_args
        # command is the first positional argument
        command = args[0][0]

        # Check command contains correct parameters
        assert "dd" in command[0]
        assert f"if={valid_bin_file}" in command
        assert "of=/dev/sdb" in command
        assert "bs=512" in command
        assert "skip=1" in command
        assert "status=progress" in command
        assert "conv=fsync" in command

    def test_restore_unmount_failure(self, valid_bin_file, mock_device, mocker):
        """Test restoration fails if unmount fails."""
        import os

        if not hasattr(os, "geteuid"):
            pytest.skip("geteuid not available on this platform")

        from rpi_usb_cloner.storage.imageusb.restore import restore_imageusb_file

        mocker.patch("os.geteuid", return_value=0)
        mocker.patch(
            "rpi_usb_cloner.storage.clone.models.resolve_device_node",
            return_value="/dev/sdb",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.devices.get_device_by_name",
            return_value=mock_device,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.devices.unmount_device", return_value=False
        )

        with pytest.raises(RuntimeError, match="Failed to unmount"):
            restore_imageusb_file(valid_bin_file, "sdb")

    def test_restore_with_progress_callback(self, valid_bin_file, mock_device, mocker):
        """Test restoration with progress callback."""
        import os

        if not hasattr(os, "geteuid"):
            pytest.skip("geteuid not available on this platform")

        from rpi_usb_cloner.storage.imageusb.restore import restore_imageusb_file

        # Mock dependencies
        mocker.patch("os.geteuid", return_value=0)
        mocker.patch(
            "rpi_usb_cloner.storage.clone.models.resolve_device_node",
            return_value="/dev/sdb",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.devices.get_device_by_name",
            return_value=mock_device,
        )
        mocker.patch("rpi_usb_cloner.storage.devices.unmount_device", return_value=True)
        mocker.patch("shutil.which", return_value="/usr/bin/dd")
        mocker.patch(
            "rpi_usb_cloner.storage.imageusb.restore.run_checked_with_streaming_progress"
        )

        # Create progress callback
        progress_calls = []

        def progress_callback(lines, ratio):
            progress_calls.append((lines, ratio))

        # Call restore with callback
        restore_imageusb_file(
            valid_bin_file, "sdb", progress_callback=progress_callback
        )

        # Verify progress callback was called
        assert len(progress_calls) > 0
