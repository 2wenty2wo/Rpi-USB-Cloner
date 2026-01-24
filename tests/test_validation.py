"""Tests for storage validation functions."""

from unittest.mock import mock_open, patch

import pytest

from rpi_usb_cloner.storage.exceptions import (
    DeviceNotFoundError,
    DeviceValidationError,
    InsufficientSpaceError,
    MountVerificationError,
    SourceDestinationSameError,
)
from rpi_usb_cloner.storage.validation import (
    validate_clone_operation,
    validate_device_exists,
    validate_device_unmounted,
    validate_devices_different,
    validate_erase_operation,
    validate_format_operation,
    validate_sufficient_space,
)


@pytest.fixture
def mock_proc_mounts_empty():
    """Mock /proc/mounts with no mounts."""
    with patch("builtins.open", mock_open(read_data="")):
        yield


@pytest.fixture
def mock_proc_mounts_with_mount():
    """Mock /proc/mounts with a mount at /mnt/usb."""
    mount_data = "/dev/sda1 /mnt/usb vfat rw,relatime 0 0\n"
    with patch("builtins.open", mock_open(read_data=mount_data)):
        yield


class TestDeviceNameExtraction:
    """Test helper functions for device name extraction."""

    def test_get_device_name_from_dict(self):
        """Test extracting device name from dict."""
        from rpi_usb_cloner.storage.validation import _get_device_name

        device = {"name": "sda"}
        assert _get_device_name(device) == "sda"

    def test_get_device_name_from_string(self):
        """Test extracting device name from string."""
        from rpi_usb_cloner.storage.validation import _get_device_name

        assert _get_device_name("sdb") == "sdb"

    def test_get_device_path_from_dict(self):
        """Test getting device path from dict."""
        from rpi_usb_cloner.storage.validation import _get_device_path

        device = {"name": "sda"}
        assert _get_device_path(device) == "/dev/sda"

    def test_get_device_path_from_string(self):
        """Test getting device path from string."""
        from rpi_usb_cloner.storage.validation import _get_device_path

        assert _get_device_path("sdc") == "/dev/sdc"

    def test_get_device_path_already_prefixed(self):
        """Test getting device path when already prefixed."""
        from rpi_usb_cloner.storage.validation import _get_device_path

        assert _get_device_path("/dev/sdd") == "/dev/sdd"


class TestValidateDeviceExists:
    """Test validate_device_exists function."""

    def test_validate_device_exists_with_empty_name(self):
        """Test validation fails for empty device name."""
        with pytest.raises(DeviceNotFoundError) as exc_info:
            validate_device_exists("")
        assert "(empty name)" in str(exc_info.value)

    def test_validate_device_exists_with_none_name(self):
        """Test validation fails for None device name."""
        with pytest.raises(DeviceNotFoundError):
            validate_device_exists({"name": None})

    @patch("rpi_usb_cloner.storage.validation.get_device_by_name")
    def test_validate_device_exists_not_found(self, mock_get_device):
        """Test validation fails when device not found."""
        mock_get_device.return_value = None
        with pytest.raises(DeviceNotFoundError) as exc_info:
            validate_device_exists("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    @patch("rpi_usb_cloner.storage.validation.get_device_by_name")
    def test_validate_device_exists_found(self, mock_get_device):
        """Test validation passes when device found."""
        mock_get_device.return_value = {"name": "sda", "size": 8000000000}
        validate_device_exists("sda")  # Should not raise

    @patch("rpi_usb_cloner.storage.validation.Path.exists")
    def test_validate_device_exists_path_not_found(self, mock_exists):
        """Test validation fails when device path doesn't exist."""
        mock_exists.return_value = False
        with pytest.raises(DeviceNotFoundError):
            validate_device_exists("/dev/sdb")

    @patch("rpi_usb_cloner.storage.validation.Path.exists")
    def test_validate_device_exists_path_found(self, mock_exists):
        """Test validation passes when device path exists."""
        mock_exists.return_value = True
        validate_device_exists("/dev/sdc")  # Should not raise


class TestValidateDevicesDifferent:
    """Test validate_devices_different function."""

    def test_same_device_name_raises_error(self):
        """Test that same device name raises error."""
        with pytest.raises(SourceDestinationSameError) as exc_info:
            validate_devices_different("sda", "sda")
        assert exc_info.value.source_name == "sda"
        assert exc_info.value.destination_name == "sda"

    def test_same_device_dict_raises_error(self):
        """Test that same device dict raises error."""
        source = {"name": "sdb"}
        dest = {"name": "sdb"}
        with pytest.raises(SourceDestinationSameError):
            validate_devices_different(source, dest)

    def test_different_devices_pass(self):
        """Test that different devices pass validation."""
        validate_devices_different("sda", "sdb")  # Should not raise
        validate_devices_different({"name": "sdc"}, {"name": "sdd"})

    def test_same_device_with_dev_prefix(self):
        """Test same device with /dev/ prefix."""
        with pytest.raises(SourceDestinationSameError):
            validate_devices_different("/dev/sda", "sda")

    def test_same_base_device_different_partitions(self):
        """Test same base device with different partitions raises error."""
        with pytest.raises(SourceDestinationSameError):
            validate_devices_different("sda1", "sda2")

    def test_nvme_same_base_device(self):
        """Test NVMe devices with same base device."""
        with pytest.raises(SourceDestinationSameError):
            validate_devices_different("nvme0n1p1", "nvme0n1p2")

    def test_nvme_different_devices(self):
        """Test different NVMe devices pass validation."""
        validate_devices_different("nvme0n1", "nvme1n1")  # Should not raise

    def test_mmcblk_same_base_device(self):
        """Test MMC devices with same base device."""
        with pytest.raises(SourceDestinationSameError):
            validate_devices_different("mmcblk0p1", "mmcblk0p2")

    def test_mmcblk_different_devices(self):
        """Test different MMC devices pass validation."""
        # mmcblk0 and mmcblk1 are different physical devices
        validate_devices_different("mmcblk0", "mmcblk1")  # Should not raise


class TestValidateDeviceUnmounted:
    """Test validate_device_unmounted function."""

    @patch("rpi_usb_cloner.storage.validation.get_device_by_name")
    def test_device_not_found_passes(self, mock_get_device):
        """Test validation passes when device not found (can't verify)."""
        mock_get_device.return_value = None
        validate_device_unmounted("nonexistent")  # Should not raise

    @patch("rpi_usb_cloner.storage.validation.get_device_by_name")
    @patch("rpi_usb_cloner.storage.validation._is_mountpoint_active")
    def test_device_with_active_mountpoint_raises(
        self, mock_is_active, mock_get_device
    ):
        """Test validation fails when device has active mountpoint."""
        mock_get_device.return_value = {
            "name": "sda",
            "mountpoint": "/mnt/usb",
            "children": [],
        }
        mock_is_active.return_value = True

        with pytest.raises(MountVerificationError) as exc_info:
            validate_device_unmounted("sda")
        assert exc_info.value.device_name == "sda"
        assert exc_info.value.mountpoint == "/mnt/usb"

    @patch("rpi_usb_cloner.storage.validation.get_device_by_name")
    @patch("rpi_usb_cloner.storage.validation._is_mountpoint_active")
    def test_device_with_inactive_mountpoint_passes(
        self, mock_is_active, mock_get_device
    ):
        """Test validation passes when mountpoint is not active."""
        mock_get_device.return_value = {
            "name": "sda",
            "mountpoint": "/mnt/usb",
            "children": [],
        }
        mock_is_active.return_value = False
        validate_device_unmounted("sda")  # Should not raise

    @patch("rpi_usb_cloner.storage.validation.get_device_by_name")
    @patch("rpi_usb_cloner.storage.validation._is_mountpoint_active")
    @patch("rpi_usb_cloner.storage.validation.get_children")
    def test_partition_with_active_mountpoint_raises(
        self, mock_get_children, mock_is_active, mock_get_device
    ):
        """Test validation fails when partition has active mountpoint."""
        mock_get_device.return_value = {"name": "sda", "mountpoint": None}
        mock_get_children.return_value = [
            {"name": "sda1", "mountpoint": "/mnt/usb1"},
        ]
        mock_is_active.return_value = True

        with pytest.raises(MountVerificationError) as exc_info:
            validate_device_unmounted("sda")
        assert exc_info.value.device_name == "sda"
        assert exc_info.value.mountpoint == "/mnt/usb1"

    @patch("rpi_usb_cloner.storage.validation.get_device_by_name")
    @patch("rpi_usb_cloner.storage.validation._is_mountpoint_active")
    @patch("rpi_usb_cloner.storage.validation.get_children")
    def test_device_with_no_mountpoints_passes(
        self, mock_get_children, mock_is_active, mock_get_device
    ):
        """Test validation passes when device has no mountpoints."""
        mock_get_device.return_value = {"name": "sda", "mountpoint": None}
        mock_get_children.return_value = []
        validate_device_unmounted("sda")  # Should not raise


class TestValidateSufficientSpace:
    """Test validate_sufficient_space function."""

    def test_sufficient_space_passes(self):
        """Test validation passes when destination is large enough."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sdb", "size": 16000000000}
        validate_sufficient_space(source, dest)  # Should not raise

    def test_equal_space_passes(self):
        """Test validation passes when sizes are equal."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sdb", "size": 8000000000}
        validate_sufficient_space(source, dest)  # Should not raise

    def test_insufficient_space_raises(self):
        """Test validation fails when destination is too small."""
        source = {"name": "sda", "size": 16000000000}
        dest = {"name": "sdb", "size": 8000000000}
        with pytest.raises(InsufficientSpaceError) as exc_info:
            validate_sufficient_space(source, dest)
        assert exc_info.value.source_size == 16000000000
        assert exc_info.value.destination_size == 8000000000

    def test_missing_source_size_raises(self):
        """Test validation fails when source size is missing."""
        source = {"name": "sda"}
        dest = {"name": "sdb", "size": 8000000000}
        with pytest.raises(DeviceValidationError) as exc_info:
            validate_sufficient_space(source, dest)
        assert "source" in str(exc_info.value).lower()

    def test_missing_dest_size_raises(self):
        """Test validation fails when destination size is missing."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sdb"}
        with pytest.raises(DeviceValidationError) as exc_info:
            validate_sufficient_space(source, dest)
        assert "destination" in str(exc_info.value).lower()


class TestValidateCloneOperation:
    """Test validate_clone_operation function."""

    @patch("rpi_usb_cloner.storage.validation.validate_device_exists")
    @patch("rpi_usb_cloner.storage.validation.validate_devices_different")
    @patch("rpi_usb_cloner.storage.validation.validate_device_unmounted")
    @patch("rpi_usb_cloner.storage.validation.validate_sufficient_space")
    def test_full_validation_with_space_check(
        self, mock_space, mock_unmount, mock_different, mock_exists
    ):
        """Test full clone validation with space check."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sdb", "size": 16000000000}

        validate_clone_operation(source, dest, check_space=True)

        # Verify all validation functions were called
        assert mock_exists.call_count == 2
        mock_different.assert_called_once()
        mock_unmount.assert_called_once()
        mock_space.assert_called_once()

    @patch("rpi_usb_cloner.storage.validation.validate_device_exists")
    @patch("rpi_usb_cloner.storage.validation.validate_devices_different")
    @patch("rpi_usb_cloner.storage.validation.validate_device_unmounted")
    @patch("rpi_usb_cloner.storage.validation.validate_sufficient_space")
    def test_validation_without_space_check(
        self, mock_space, mock_unmount, mock_different, mock_exists
    ):
        """Test clone validation without space check."""
        source = {"name": "sda", "size": 8000000000}
        dest = {"name": "sdb", "size": 16000000000}

        validate_clone_operation(source, dest, check_space=False)

        # Space check should not be called
        mock_space.assert_not_called()

    @patch("rpi_usb_cloner.storage.validation.validate_device_exists")
    def test_validation_fails_on_nonexistent_source(self, mock_exists):
        """Test validation fails when source doesn't exist."""
        mock_exists.side_effect = [DeviceNotFoundError("sda"), None]

        with pytest.raises(DeviceNotFoundError):
            validate_clone_operation("sda", "sdb")

    @patch("rpi_usb_cloner.storage.validation.validate_device_exists")
    @patch("rpi_usb_cloner.storage.validation.validate_devices_different")
    def test_validation_fails_on_same_device(self, mock_different, mock_exists):
        """Test validation fails when devices are the same."""
        mock_different.side_effect = SourceDestinationSameError("sda", "sda")

        with pytest.raises(SourceDestinationSameError):
            validate_clone_operation("sda", "sda")


class TestValidateFormatOperation:
    """Test validate_format_operation function."""

    @patch("rpi_usb_cloner.storage.validation.validate_device_exists")
    @patch("rpi_usb_cloner.storage.validation.validate_device_unmounted")
    def test_format_validation_success(self, mock_unmount, mock_exists):
        """Test successful format validation."""
        device = {"name": "sda"}
        validate_format_operation(device)

        mock_exists.assert_called_once()
        mock_unmount.assert_called_once()

    @patch("rpi_usb_cloner.storage.validation.validate_device_exists")
    @patch("rpi_usb_cloner.storage.validation.validate_device_unmounted")
    def test_format_validation_skip_unmounted(self, mock_unmount, mock_exists):
        """Test format validation without unmounted check."""
        device = {"name": "sda"}

        validate_format_operation(device, check_unmounted=False)

        mock_exists.assert_called_once()
        mock_unmount.assert_not_called()

    @patch("rpi_usb_cloner.storage.validation.validate_device_exists")
    def test_format_validation_fails_on_nonexistent(self, mock_exists):
        """Test format validation fails when device doesn't exist."""
        mock_exists.side_effect = DeviceNotFoundError("sda")

        with pytest.raises(DeviceNotFoundError):
            validate_format_operation("sda")


class TestValidateEraseOperation:
    """Test validate_erase_operation function."""

    @patch("rpi_usb_cloner.storage.validation.validate_device_exists")
    @patch("rpi_usb_cloner.storage.validation.validate_device_unmounted")
    def test_erase_validation_success(self, mock_unmount, mock_exists):
        """Test successful erase validation."""
        device = {"name": "sda"}
        validate_erase_operation(device)

        mock_exists.assert_called_once()
        mock_unmount.assert_called_once()

    @patch("rpi_usb_cloner.storage.validation.validate_device_exists")
    @patch("rpi_usb_cloner.storage.validation.validate_device_unmounted")
    def test_erase_validation_skip_unmounted(self, mock_unmount, mock_exists):
        """Test erase validation without unmounted check."""
        device = {"name": "sda"}

        validate_erase_operation(device, check_unmounted=False)

        mock_exists.assert_called_once()
        mock_unmount.assert_not_called()

    @patch("rpi_usb_cloner.storage.validation.validate_device_exists")
    def test_erase_validation_fails_on_nonexistent(self, mock_exists):
        """Test erase validation fails when device doesn't exist."""
        mock_exists.side_effect = DeviceNotFoundError("sda")

        with pytest.raises(DeviceNotFoundError):
            validate_erase_operation("sda")


class TestIsMountpointActive:
    """Test _is_mountpoint_active helper function."""

    def test_mountpoint_active_in_proc_mounts(self, mock_proc_mounts_with_mount):
        """Test detecting active mountpoint from /proc/mounts."""
        from rpi_usb_cloner.storage.validation import _is_mountpoint_active

        assert _is_mountpoint_active("/mnt/usb") is True

    def test_mountpoint_not_active(self, mock_proc_mounts_empty):
        """Test detecting inactive mountpoint."""
        from rpi_usb_cloner.storage.validation import _is_mountpoint_active

        assert _is_mountpoint_active("/mnt/usb") is False

    @patch("os.path.ismount")
    def test_fallback_to_ismount(self, mock_ismount):
        """Test fallback to os.path.ismount when /proc/mounts unavailable."""
        from rpi_usb_cloner.storage.validation import _is_mountpoint_active

        with patch("builtins.open", side_effect=FileNotFoundError):
            mock_ismount.return_value = True
            assert _is_mountpoint_active("/mnt/usb") is True
