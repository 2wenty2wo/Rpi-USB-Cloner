"""Extended tests for device erasure operations.

Tests cover:
- Different erase modes (quick, zero, secure, discard)
- Error handling
- Progress callback integration
"""

from __future__ import annotations

from unittest.mock import Mock, patch, MagicMock

import pytest

from rpi_usb_cloner.storage.clone.erase import erase_device
from rpi_usb_cloner.storage.exceptions import DeviceBusyError, MountVerificationError


class TestEraseDeviceValidation:
    """Test erase device validation."""

    def test_erase_validation_failure(self, mocker):
        """Test abort when validation fails."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            side_effect=DeviceBusyError("Device is busy"),
        )
        mock_display = mocker.patch("rpi_usb_cloner.storage.clone.erase.display_lines")

        result = erase_device(target, "quick")

        assert result is False
        mock_display.assert_called_once()

    def test_erase_unmount_failure(self, mocker):
        """Test abort when unmount fails."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=False,
        )
        mock_display = mocker.patch("rpi_usb_cloner.storage.clone.erase.display_lines")

        result = erase_device(target, "quick")

        assert result is False
        mock_display.assert_called_once()


class TestEraseQuickMode:
    """Test quick erase mode."""

    def test_quick_erase_success(self, mocker):
        """Test successful quick erase."""
        target = {"name": "sda", "size": 1000000, "model": "Test Drive"}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.shutil.which",
            side_effect=["/sbin/wipefs", "/bin/dd"],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.run_checked_with_streaming_progress",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.app_state.QUICK_WIPE_MIB",
            100,
        )

        result = erase_device(target, "quick")

        assert result is True

    def test_quick_erase_wipefs_failure(self, mocker):
        """Test handling wipefs failure."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.shutil.which",
            side_effect=["/sbin/wipefs", "/bin/dd"],
        )

        def side_effect(cmd, **kwargs):
            if "wipefs" in cmd[0]:
                raise Exception("wipefs failed")
            return None

        mock_run = mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.run_checked_with_streaming_progress",
            side_effect=side_effect,
        )

        result = erase_device(target, "quick")

        assert result is False

    def test_quick_erase_no_wipefs(self, mocker):
        """Test error when wipefs not available."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.shutil.which",
            side_effect=[None, "/bin/dd"],  # wipefs not found
        )
        mock_display = mocker.patch("rpi_usb_cloner.storage.clone.erase.display_lines")

        result = erase_device(target, "quick")

        assert result is False

    def test_quick_erase_no_dd(self, mocker):
        """Test error when dd not available."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.shutil.which",
            side_effect=["/sbin/wipefs", None],  # dd not found
        )

        result = erase_device(target, "quick")

        assert result is False


class TestEraseZeroMode:
    """Test zero-fill erase mode."""

    def test_zero_erase_success(self, mocker):
        """Test successful zero-fill erase."""
        target = {"name": "sda", "size": 1024 * 1024 * 100}  # 100MB

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.shutil.which",
            return_value="/bin/dd",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.run_checked_with_streaming_progress",
            return_value=None,
        )

        result = erase_device(target, "zero")

        assert result is True

    def test_zero_erase_no_dd(self, mocker):
        """Test error when dd not available."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.shutil.which",
            return_value=None,
        )

        result = erase_device(target, "zero")

        assert result is False


class TestEraseSecureMode:
    """Test secure erase mode with shred."""

    def test_secure_erase_success(self, mocker):
        """Test successful secure erase."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.shutil.which",
            return_value="/usr/bin/shred",
        )
        mock_run = mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.run_checked_with_streaming_progress",
            return_value=None,
        )

        result = erase_device(target, "secure")

        assert result is True
        # Verify shred was called with correct flags
        call_args = mock_run.call_args[0][0]
        assert "shred" in call_args[0]
        assert "-n" in call_args  # Number of passes
        assert "-z" in call_args  # Final zero fill

    def test_secure_erase_no_shred(self, mocker):
        """Test error when shred not available."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.shutil.which",
            return_value=None,
        )

        result = erase_device(target, "secure")

        assert result is False


class TestEraseDiscardMode:
    """Test discard (TRIM) erase mode."""

    def test_discard_erase_success(self, mocker):
        """Test successful discard erase."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.shutil.which",
            return_value="/sbin/blkdiscard",
        )
        mock_run = mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.run_checked_with_streaming_progress",
            return_value=None,
        )

        result = erase_device(target, "discard")

        assert result is True
        # Verify blkdiscard was called
        call_args = mock_run.call_args[0][0]
        assert "blkdiscard" in call_args[0]
        assert "/dev/sda" in call_args

    def test_discard_erase_no_blkdiscard(self, mocker):
        """Test error when blkdiscard not available."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.shutil.which",
            return_value=None,
        )

        result = erase_device(target, "discard")

        assert result is False


class TestEraseUnknownMode:
    """Test handling unknown erase modes."""

    def test_unknown_mode(self, mocker):
        """Test error for unknown erase mode."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )

        result = erase_device(target, "unknown_mode")

        assert result is False

    def test_empty_mode(self, mocker):
        """Test error for empty erase mode."""
        target = {"name": "sda", "size": 1000000}

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )

        result = erase_device(target, "")

        assert result is False


class TestEraseProgressCallback:
    """Test progress callback integration."""

    def test_progress_callback_called(self, mocker):
        """Test progress callback is invoked."""
        target = {"name": "sda", "size": 1000000}
        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.get_device_by_name",
            return_value=target,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_device_unmounted",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.shutil.which",
            side_effect=["/sbin/wipefs", "/bin/dd"],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.run_checked_with_streaming_progress",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.app_state.QUICK_WIPE_MIB",
            100,
        )

        result = erase_device(target, "quick", progress_callback=progress_cb)

        assert result is True

    def test_progress_callback_on_validation_error(self, mocker):
        """Test progress callback on validation failure."""
        target = {"name": "sda", "size": 1000000}
        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            side_effect=DeviceBusyError("Device busy"),
        )

        result = erase_device(target, "quick", progress_callback=progress_cb)

        assert result is False
        assert len(progress_calls) == 1
        assert progress_calls[0][0][0] == "ERROR"

    def test_progress_callback_on_unmount_error(self, mocker):
        """Test progress callback on unmount failure."""
        target = {"name": "sda", "size": 1000000}
        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.validate_erase_operation",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.device_operation",
            return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clone.erase.unmount_device",
            return_value=False,
        )

        result = erase_device(target, "quick", progress_callback=progress_cb)

        assert result is False
        assert len(progress_calls) == 1
        assert progress_calls[0][0][0] == "ERROR"
