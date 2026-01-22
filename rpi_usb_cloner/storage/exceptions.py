"""Custom exceptions for storage operations.

This module defines a hierarchy of exceptions for storage operations to provide
more specific error handling and better error messages.

Exception Hierarchy:
    StorageError (base)
        ├── DeviceError
        │   ├── DeviceNotFoundError
        │   ├── DeviceBusyError
        │   └── DeviceValidationError
        ├── MountError
        │   ├── UnmountFailedError
        │   └── MountVerificationError
        ├── CloneError
        │   ├── SourceDestinationSameError
        │   ├── InsufficientSpaceError
        │   └── CloneOperationError
        ├── FormatError
        │   └── FormatOperationError
        └── EraseError
            └── EraseOperationError

Usage:
    from rpi_usb_cloner.storage.exceptions import SourceDestinationSameError

    if source_device == destination_device:
        raise SourceDestinationSameError(source_device, destination_device)
"""


class StorageError(Exception):
    """Base exception for all storage operations."""



class DeviceError(StorageError):
    """Base exception for device-related errors."""



class DeviceNotFoundError(DeviceError):
    """Device was not found or does not exist."""

    def __init__(self, device_name: str):
        self.device_name = device_name
        super().__init__(f"Device not found: {device_name}")


class DeviceBusyError(DeviceError):
    """Device is currently in use or mounted."""

    def __init__(self, device_name: str, reason: str = ""):
        self.device_name = device_name
        self.reason = reason
        msg = f"Device {device_name} is busy"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class DeviceValidationError(DeviceError):
    """Device failed validation checks."""

    def __init__(self, device_name: str, reason: str):
        self.device_name = device_name
        self.reason = reason
        super().__init__(f"Device validation failed for {device_name}: {reason}")


class MountError(StorageError):
    """Base exception for mount-related errors."""



class UnmountFailedError(MountError):
    """Failed to unmount device or partition."""

    def __init__(self, device_name: str, mountpoints: list[str]):
        self.device_name = device_name
        self.mountpoints = mountpoints
        mounts_str = ", ".join(mountpoints)
        super().__init__(
            f"Failed to unmount {device_name}. " f"Active mountpoints: {mounts_str}"
        )


class MountVerificationError(MountError):
    """Device is still mounted after unmount operation."""

    def __init__(self, device_name: str, mountpoint: str):
        self.device_name = device_name
        self.mountpoint = mountpoint
        super().__init__(
            f"Device {device_name} still mounted at {mountpoint} "
            f"after unmount operation"
        )


class CloneError(StorageError):
    """Base exception for clone operations."""



class SourceDestinationSameError(CloneError):
    """Source and destination devices are the same."""

    def __init__(self, source_name: str, destination_name: str):
        self.source_name = source_name
        self.destination_name = destination_name
        super().__init__(
            f"Source and destination cannot be the same device: "
            f"{source_name} == {destination_name}"
        )


class InsufficientSpaceError(CloneError):
    """Destination device is too small for source data."""

    def __init__(
        self,
        source_name: str,
        source_size: int,
        destination_name: str,
        destination_size: int,
    ):
        self.source_name = source_name
        self.source_size = source_size
        self.destination_name = destination_name
        self.destination_size = destination_size
        super().__init__(
            f"Destination {destination_name} ({destination_size} bytes) "
            f"is too small for source {source_name} ({source_size} bytes)"
        )


class CloneOperationError(CloneError):
    """Generic clone operation failure."""

    def __init__(self, message: str, source: str = None, destination: str = None):
        self.source = source
        self.destination = destination
        super().__init__(message)


class FormatError(StorageError):
    """Base exception for format operations."""



class FormatOperationError(FormatError):
    """Generic format operation failure."""

    def __init__(self, message: str, device: str = None):
        self.device = device
        super().__init__(message)


class EraseError(StorageError):
    """Base exception for erase operations."""



class EraseOperationError(EraseError):
    """Generic erase operation failure."""

    def __init__(self, message: str, device: str = None):
        self.device = device
        super().__init__(message)
