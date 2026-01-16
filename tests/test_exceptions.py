"""Tests for storage exception classes."""

import pytest

from rpi_usb_cloner.storage.exceptions import (
    CloneError,
    CloneOperationError,
    DeviceBusyError,
    DeviceError,
    DeviceNotFoundError,
    DeviceValidationError,
    EraseError,
    EraseOperationError,
    FormatError,
    FormatOperationError,
    InsufficientSpaceError,
    MountError,
    MountVerificationError,
    SourceDestinationSameError,
    StorageError,
    UnmountFailedError,
)


class TestExceptionHierarchy:
    """Test exception inheritance hierarchy."""

    def test_storage_error_is_base_exception(self):
        """Test that StorageError is base exception."""
        error = StorageError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"

    def test_device_error_inherits_from_storage_error(self):
        """Test DeviceError inheritance."""
        error = DeviceError("test")
        assert isinstance(error, StorageError)
        assert isinstance(error, Exception)

    def test_mount_error_inherits_from_storage_error(self):
        """Test MountError inheritance."""
        error = MountError("test")
        assert isinstance(error, StorageError)

    def test_clone_error_inherits_from_storage_error(self):
        """Test CloneError inheritance."""
        error = CloneError("test")
        assert isinstance(error, StorageError)

    def test_format_error_inherits_from_storage_error(self):
        """Test FormatError inheritance."""
        error = FormatError("test")
        assert isinstance(error, StorageError)

    def test_erase_error_inherits_from_storage_error(self):
        """Test EraseError inheritance."""
        error = EraseError("test")
        assert isinstance(error, StorageError)


class TestDeviceExceptions:
    """Test device-related exceptions."""

    def test_device_not_found_error(self):
        """Test DeviceNotFoundError exception."""
        error = DeviceNotFoundError("sda")
        assert isinstance(error, DeviceError)
        assert error.device_name == "sda"
        assert "sda" in str(error)
        assert "not found" in str(error).lower()

    def test_device_busy_error_without_reason(self):
        """Test DeviceBusyError without reason."""
        error = DeviceBusyError("sdb")
        assert isinstance(error, DeviceError)
        assert error.device_name == "sdb"
        assert error.reason == ""
        assert "sdb" in str(error)
        assert "busy" in str(error).lower()

    def test_device_busy_error_with_reason(self):
        """Test DeviceBusyError with reason."""
        error = DeviceBusyError("sdc", "mounted at /mnt")
        assert error.device_name == "sdc"
        assert error.reason == "mounted at /mnt"
        assert "sdc" in str(error)
        assert "mounted at /mnt" in str(error)

    def test_device_validation_error(self):
        """Test DeviceValidationError exception."""
        error = DeviceValidationError("sdd", "not removable")
        assert isinstance(error, DeviceError)
        assert error.device_name == "sdd"
        assert error.reason == "not removable"
        assert "sdd" in str(error)
        assert "not removable" in str(error)


class TestMountExceptions:
    """Test mount-related exceptions."""

    def test_unmount_failed_error(self):
        """Test UnmountFailedError exception."""
        mountpoints = ["/mnt/usb1", "/mnt/usb2"]
        error = UnmountFailedError("sda", mountpoints)
        assert isinstance(error, MountError)
        assert error.device_name == "sda"
        assert error.mountpoints == mountpoints
        assert "sda" in str(error)
        assert "/mnt/usb1" in str(error)
        assert "/mnt/usb2" in str(error)

    def test_mount_verification_error(self):
        """Test MountVerificationError exception."""
        error = MountVerificationError("sdb", "/mnt/backup")
        assert isinstance(error, MountError)
        assert error.device_name == "sdb"
        assert error.mountpoint == "/mnt/backup"
        assert "sdb" in str(error)
        assert "/mnt/backup" in str(error)
        assert "still mounted" in str(error).lower()


class TestCloneExceptions:
    """Test clone-related exceptions."""

    def test_source_destination_same_error(self):
        """Test SourceDestinationSameError exception."""
        error = SourceDestinationSameError("sda", "sda")
        assert isinstance(error, CloneError)
        assert error.source_name == "sda"
        assert error.destination_name == "sda"
        assert "sda" in str(error)
        assert "same" in str(error).lower()

    def test_insufficient_space_error(self):
        """Test InsufficientSpaceError exception."""
        error = InsufficientSpaceError("sda", 16000000000, "sdb", 8000000000)
        assert isinstance(error, CloneError)
        assert error.source_name == "sda"
        assert error.source_size == 16000000000
        assert error.destination_name == "sdb"
        assert error.destination_size == 8000000000
        assert "sda" in str(error)
        assert "sdb" in str(error)
        assert "too small" in str(error).lower()

    def test_clone_operation_error_minimal(self):
        """Test CloneOperationError with minimal args."""
        error = CloneOperationError("clone failed")
        assert isinstance(error, CloneError)
        assert error.source is None
        assert error.destination is None
        assert str(error) == "clone failed"

    def test_clone_operation_error_full(self):
        """Test CloneOperationError with all args."""
        error = CloneOperationError("clone failed", source="sda", destination="sdb")
        assert error.source == "sda"
        assert error.destination == "sdb"
        assert str(error) == "clone failed"


class TestFormatExceptions:
    """Test format-related exceptions."""

    def test_format_operation_error_minimal(self):
        """Test FormatOperationError with minimal args."""
        error = FormatOperationError("format failed")
        assert isinstance(error, FormatError)
        assert error.device is None
        assert str(error) == "format failed"

    def test_format_operation_error_with_device(self):
        """Test FormatOperationError with device."""
        error = FormatOperationError("format failed", device="sdc")
        assert error.device == "sdc"
        assert str(error) == "format failed"


class TestEraseExceptions:
    """Test erase-related exceptions."""

    def test_erase_operation_error_minimal(self):
        """Test EraseOperationError with minimal args."""
        error = EraseOperationError("erase failed")
        assert isinstance(error, EraseError)
        assert error.device is None
        assert str(error) == "erase failed"

    def test_erase_operation_error_with_device(self):
        """Test EraseOperationError with device."""
        error = EraseOperationError("erase failed", device="sdd")
        assert error.device == "sdd"
        assert str(error) == "erase failed"


class TestExceptionRaising:
    """Test that exceptions can be raised and caught properly."""

    def test_raise_and_catch_source_destination_same(self):
        """Test raising and catching SourceDestinationSameError."""
        with pytest.raises(SourceDestinationSameError) as exc_info:
            raise SourceDestinationSameError("sda", "sda")
        assert exc_info.value.source_name == "sda"
        assert exc_info.value.destination_name == "sda"

    def test_catch_as_storage_error(self):
        """Test catching specific exception as base StorageError."""
        with pytest.raises(StorageError):
            raise DeviceNotFoundError("sda")

    def test_catch_as_device_error(self):
        """Test catching specific exception as DeviceError."""
        with pytest.raises(DeviceError):
            raise DeviceNotFoundError("sda")
