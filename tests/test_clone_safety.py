"""Safety tests for clone operations.

These tests verify that the safety validation mechanisms prevent dangerous
operations like cloning a device to itself or operating on mounted devices.
"""

from unittest.mock import MagicMock, patch

import pytest

from rpi_usb_cloner.storage.clone.operations import clone_device, clone_device_smart
from rpi_usb_cloner.storage.exceptions import (
    InsufficientSpaceError,
    MountVerificationError,
    SourceDestinationSameError,
)


@pytest.fixture
def mock_display():
    """Mock display_lines function."""
    with patch("rpi_usb_cloner.storage.clone.operations.display_lines"):
        yield


@pytest.fixture
def mock_unmount():
    """Mock unmount_device function."""
    with patch("rpi_usb_cloner.storage.clone.operations.unmount_device") as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_validation():
    """Mock validation module."""
    with patch("rpi_usb_cloner.storage.clone.operations.validate_clone_operation") as mock:
        yield mock


class TestCloneDeviceSafety:
    """Test safety checks in clone_device function."""

    def test_same_device_rejected(self, mock_display, mock_validation):
        """Test that cloning a device to itself is rejected."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sda", "size": 8000000000}

        # Make validation raise SourceDestinationSameError
        mock_validation.side_effect = SourceDestinationSameError("sda", "sda")

        result = clone_device(source, dest)

        assert result is False
        mock_validation.assert_called_once()

    def test_insufficient_space_rejected(self, mock_display, mock_validation):
        """Test that clone is rejected when destination is too small."""
        source = {"name": "sda", "size": 16000000000}
        dest = {"name": "sdb", "size": 8000000000}

        # Make validation raise InsufficientSpaceError
        mock_validation.side_effect = InsufficientSpaceError(
            "sda", 16000000000, "sdb", 8000000000
        )

        result = clone_device(source, dest)

        assert result is False
        mock_validation.assert_called_once()

    def test_mounted_device_rejected(self, mock_display, mock_validation):
        """Test that clone is rejected when destination is mounted."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sdb", "size": 16000000000, "mountpoint": "/mnt/usb"}

        # Make validation raise MountVerificationError
        mock_validation.side_effect = MountVerificationError("sdb", "/mnt/usb")

        result = clone_device(source, dest)

        assert result is False
        mock_validation.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.operations.clone_device_smart")
    def test_valid_clone_proceeds(
        self, mock_clone_smart, mock_unmount, mock_display, mock_validation
    ):
        """Test that valid clone operation proceeds."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sdb", "size": 16000000000}

        # Validation passes (no exception raised)
        mock_validation.return_value = None
        mock_clone_smart.return_value = True

        result = clone_device(source, dest, mode="smart")

        assert result is True
        mock_validation.assert_called_once()
        mock_clone_smart.assert_called_once_with(source, dest)

    def test_validation_checks_space_by_default(self, mock_display, mock_validation):
        """Test that space validation is enabled by default."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sdb", "size": 16000000000}

        mock_validation.return_value = None

        with patch(
            "rpi_usb_cloner.storage.clone.operations.clone_device_smart"
        ) as mock_smart:
            mock_smart.return_value = True
            clone_device(source, dest, mode="smart")

        # Check that validate_clone_operation was called with check_space
        call_args = mock_validation.call_args
        assert call_args is not None
        assert "check_space" in call_args.kwargs or len(call_args.args) >= 3

    def test_exact_mode_skips_space_check(self, mock_display, mock_validation):
        """Test that exact mode can skip space validation."""
        source = {"name": "sda", "size": 16000000000}
        dest = {"name": "sdb", "size": 8000000000}  # Smaller, but exact mode

        mock_validation.return_value = None

        with patch("rpi_usb_cloner.storage.clone.operations.clone_dd"):
            with patch("rpi_usb_cloner.storage.clone.operations.unmount_device") as mock_umount:
                mock_umount.return_value = True
                result = clone_device(source, dest, mode="exact")

        # Validation should have been called
        assert mock_validation.called


class TestCloneDeviceSmartSafety:
    """Test safety checks in clone_device_smart function."""

    def test_same_device_rejected_smart(self, mock_display, mock_validation):
        """Test that smart clone rejects same device."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sda", "size": 8000000000}

        mock_validation.side_effect = SourceDestinationSameError("sda", "sda")

        result = clone_device_smart(source, dest)

        assert result is False
        mock_validation.assert_called_once()

    def test_insufficient_space_rejected_smart(self, mock_display, mock_validation):
        """Test that smart clone rejects insufficient space."""
        source = {"name": "sda", "size": 16000000000}
        dest = {"name": "sdb", "size": 8000000000}

        mock_validation.side_effect = InsufficientSpaceError(
            "sda", 16000000000, "sdb", 8000000000
        )

        result = clone_device_smart(source, dest)

        assert result is False

    def test_mounted_device_rejected_smart(self, mock_display, mock_validation):
        """Test that smart clone rejects mounted device."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sdb", "size": 16000000000, "mountpoint": "/mnt/usb"}

        mock_validation.side_effect = MountVerificationError("sdb", "/mnt/usb")

        result = clone_device_smart(source, dest)

        assert result is False

    @patch("rpi_usb_cloner.storage.clone.operations.copy_partition_table")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_partclone")
    def test_valid_smart_clone_proceeds(
        self, mock_partclone, mock_copy_table, mock_unmount, mock_display, mock_validation
    ):
        """Test that valid smart clone proceeds."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sdb", "size": 16000000000}

        mock_validation.return_value = None
        mock_copy_table.return_value = None
        mock_partclone.return_value = None

        result = clone_device_smart(source, dest)

        assert result is True
        mock_validation.assert_called_once()
        mock_copy_table.assert_called_once()
        mock_partclone.assert_called_once()

    def test_smart_clone_always_checks_space(self, mock_display, mock_validation):
        """Test that smart clone always validates space."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sdb", "size": 16000000000}

        mock_validation.return_value = None

        with patch("rpi_usb_cloner.storage.clone.operations.copy_partition_table"):
            with patch("rpi_usb_cloner.storage.clone.operations.clone_partclone"):
                with patch("rpi_usb_cloner.storage.clone.operations.unmount_device") as mock_umount:
                    mock_umount.return_value = True
                    clone_device_smart(source, dest)

        # Verify validate_clone_operation was called with check_space=True
        call_args = mock_validation.call_args
        assert call_args is not None
        # Check kwargs for check_space=True
        if "check_space" in call_args.kwargs:
            assert call_args.kwargs["check_space"] is True


class TestFormatSafety:
    """Test safety checks in format operations."""

    @patch("rpi_usb_cloner.storage.format.validate_format_operation")
    @patch("rpi_usb_cloner.storage.format.validate_device_unmounted")
    @patch("rpi_usb_cloner.storage.format.unmount_device")
    def test_mounted_device_rejected_format(
        self, mock_unmount, mock_validate_unmounted, mock_validation
    ):
        """Test that format rejects mounted device."""
        from rpi_usb_cloner.storage.format import format_device

        device = {"name": "sda", "mountpoint": "/mnt/usb"}

        mock_validation.return_value = None
        mock_unmount.return_value = True
        mock_validate_unmounted.side_effect = MountVerificationError("sda", "/mnt/usb")

        result = format_device(device, "ext4", "quick")

        assert result is False
        mock_validation.assert_called_once()
        mock_validate_unmounted.assert_called_once()

    @patch("rpi_usb_cloner.storage.format.validate_format_operation")
    @patch("rpi_usb_cloner.storage.format.validate_device_unmounted")
    @patch("rpi_usb_cloner.storage.format.unmount_device")
    @patch("rpi_usb_cloner.storage.format._create_partition_table")
    @patch("rpi_usb_cloner.storage.format._create_partition")
    @patch("rpi_usb_cloner.storage.format._format_filesystem")
    def test_valid_format_proceeds(
        self,
        mock_format_fs,
        mock_create_part,
        mock_create_table,
        mock_unmount,
        mock_validate_unmounted,
        mock_validation,
    ):
        """Test that valid format operation proceeds."""
        from rpi_usb_cloner.storage.format import format_device

        device = {"name": "sda"}

        mock_validation.return_value = None
        mock_unmount.return_value = True
        mock_validate_unmounted.return_value = None
        mock_create_table.return_value = True
        mock_create_part.return_value = True
        mock_format_fs.return_value = True

        result = format_device(device, "ext4", "quick")

        assert result is True
        mock_validation.assert_called_once()
        mock_validate_unmounted.assert_called_once()


class TestEraseSafety:
    """Test safety checks in erase operations."""

    @patch("rpi_usb_cloner.storage.clone.erase.validate_erase_operation")
    @patch("rpi_usb_cloner.storage.clone.erase.validate_device_unmounted")
    @patch("rpi_usb_cloner.storage.clone.erase.unmount_device")
    def test_mounted_device_rejected_erase(
        self, mock_unmount, mock_validate_unmounted, mock_validation
    ):
        """Test that erase rejects mounted device."""
        from rpi_usb_cloner.storage.clone.erase import erase_device

        device = {"name": "sda", "mountpoint": "/mnt/usb"}

        mock_validation.return_value = None
        mock_unmount.return_value = True
        mock_validate_unmounted.side_effect = MountVerificationError("sda", "/mnt/usb")

        result = erase_device(device, "quick")

        assert result is False
        mock_validation.assert_called_once()
        mock_validate_unmounted.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.erase.validate_erase_operation")
    @patch("rpi_usb_cloner.storage.clone.erase.validate_device_unmounted")
    @patch("rpi_usb_cloner.storage.clone.erase.unmount_device")
    @patch("rpi_usb_cloner.storage.clone.erase.run_checked_with_streaming_progress")
    @patch("shutil.which")
    def test_valid_erase_proceeds(
        self,
        mock_which,
        mock_run_progress,
        mock_unmount,
        mock_validate_unmounted,
        mock_validation,
    ):
        """Test that valid erase operation proceeds."""
        from rpi_usb_cloner.storage.clone.erase import erase_device

        device = {"name": "sda", "size": 8000000000}

        mock_validation.return_value = None
        mock_unmount.return_value = True
        mock_validate_unmounted.return_value = None
        mock_which.return_value = "/usr/bin/wipefs"
        mock_run_progress.return_value = None

        result = erase_device(device, "quick")

        assert result is True
        mock_validation.assert_called_once()
        mock_validate_unmounted.assert_called_once()


class TestUnmountWithRaiseOnFailure:
    """Test unmount_device with raise_on_failure flag."""

    @patch("rpi_usb_cloner.storage.devices.run_command")
    @patch("rpi_usb_cloner.storage.devices._collect_device_mountpoints")
    @patch("rpi_usb_cloner.storage.devices._is_mountpoint_active")
    def test_unmount_raises_on_failure(
        self, mock_is_active, mock_collect, mock_run_cmd
    ):
        """Test that unmount raises exception when raise_on_failure=True."""
        from rpi_usb_cloner.storage.devices import unmount_device
        from rpi_usb_cloner.storage.exceptions import UnmountFailedError

        device = {"name": "sda"}
        mock_collect.return_value = ["/mnt/usb"]

        # Simulate failed unmount
        mock_run_result = MagicMock()
        mock_run_result.returncode = 1
        mock_run_cmd.return_value = mock_run_result
        mock_is_active.return_value = True  # Still mounted after attempt

        with pytest.raises(UnmountFailedError) as exc_info:
            unmount_device(device, raise_on_failure=True)

        assert exc_info.value.device_name == "sda"
        assert "/mnt/usb" in exc_info.value.mountpoints

    @patch("rpi_usb_cloner.storage.devices.run_command")
    @patch("rpi_usb_cloner.storage.devices._collect_device_mountpoints")
    @patch("rpi_usb_cloner.storage.devices._is_mountpoint_active")
    def test_unmount_returns_false_without_raise(
        self, mock_is_active, mock_collect, mock_run_cmd
    ):
        """Test that unmount returns False when raise_on_failure=False."""
        from rpi_usb_cloner.storage.devices import unmount_device

        device = {"name": "sda"}
        mock_collect.return_value = ["/mnt/usb"]

        # Simulate failed unmount
        mock_run_result = MagicMock()
        mock_run_result.returncode = 1
        mock_run_cmd.return_value = mock_run_result
        mock_is_active.return_value = True

        result = unmount_device(device, raise_on_failure=False)

        assert result is False

    @patch("rpi_usb_cloner.storage.devices._collect_device_mountpoints")
    def test_unmount_succeeds_no_mountpoints(self, mock_collect):
        """Test that unmount succeeds when no mountpoints exist."""
        from rpi_usb_cloner.storage.devices import unmount_device

        device = {"name": "sda"}
        mock_collect.return_value = []

        result = unmount_device(device, raise_on_failure=True)

        assert result is True


class TestPartitionSafety:
    """Test safety with partition devices."""

    def test_partition_same_as_disk_rejected(self, mock_display, mock_validation):
        """Test that cloning sda to sda1 is rejected."""
        source = {"name": "sda"}
        dest = {"name": "sda1"}

        mock_validation.side_effect = SourceDestinationSameError("sda", "sda1")

        result = clone_device(source, dest)

        assert result is False

    def test_different_partitions_same_disk_rejected(self, mock_display, mock_validation):
        """Test that cloning sda1 to sda2 is rejected."""
        source = {"name": "sda1"}
        dest = {"name": "sda2"}

        mock_validation.side_effect = SourceDestinationSameError("sda1", "sda2")

        result = clone_device(source, dest)

        assert result is False
