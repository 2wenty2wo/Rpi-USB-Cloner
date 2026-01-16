"""Safety validation functions for storage operations.

This module provides validation functions to prevent dangerous operations:
- Validates source != destination before cloning
- Verifies devices are unmounted before destructive operations
- Checks destination has sufficient space
- Validates device accessibility

All validation functions raise specific exceptions from the exceptions module
rather than returning boolean values, making error handling more explicit.

Example:
    from rpi_usb_cloner.storage.validation import validate_clone_operation

    try:
        validate_clone_operation(source_device, destination_device)
        # Safe to proceed with clone
    except SourceDestinationSameError:
        # Handle error
        pass
"""

import os
from typing import Optional

from .devices import get_children, get_device_by_name
from .exceptions import (
    DeviceBusyError,
    DeviceNotFoundError,
    DeviceValidationError,
    InsufficientSpaceError,
    MountVerificationError,
    SourceDestinationSameError,
)


def _get_device_name(device) -> str:
    """Extract device name from device dict or string."""
    if isinstance(device, dict):
        return device.get("name", "")
    return str(device)


def _get_device_path(device) -> str:
    """Get device path (/dev/xxx) from device dict or string."""
    name = _get_device_name(device)
    if name.startswith("/dev/"):
        return name
    return f"/dev/{name}"


def _is_mountpoint_active(mountpoint: str) -> bool:
    """Check if a mountpoint is currently active."""
    try:
        with open("/proc/mounts", "r", encoding="utf-8") as mounts_file:
            for line in mounts_file:
                parts = line.split()
                if len(parts) > 1 and parts[1] == mountpoint:
                    return True
    except FileNotFoundError:
        return os.path.ismount(mountpoint)
    return False


def validate_device_exists(device) -> None:
    """Validate that a device exists.

    Args:
        device: Device dict or device name string

    Raises:
        DeviceNotFoundError: If device does not exist
    """
    device_name = _get_device_name(device)
    if not device_name:
        raise DeviceNotFoundError("(empty name)")

    # If it's just a name, try to look it up
    if isinstance(device, str) and not device.startswith("/dev/"):
        device_dict = get_device_by_name(device_name)
        if not device_dict:
            raise DeviceNotFoundError(device_name)
    # If it's a path, check if device node exists
    elif isinstance(device, str):
        device_path = _get_device_path(device)
        if not os.path.exists(device_path):
            raise DeviceNotFoundError(device_name)


def validate_devices_different(source, destination) -> None:
    """Validate that source and destination devices are different.

    This is critical to prevent accidentally cloning a device to itself,
    which would destroy all data on the device.

    Args:
        source: Source device dict or device name
        destination: Destination device dict or device name

    Raises:
        SourceDestinationSameError: If devices are the same
    """
    source_name = _get_device_name(source)
    dest_name = _get_device_name(destination)

    # Remove /dev/ prefix for comparison
    source_name = source_name.replace("/dev/", "")
    dest_name = dest_name.replace("/dev/", "")

    # Compare base device names (strip partition numbers)
    # e.g., sda1 -> sda, nvme0n1p1 -> nvme0n1
    def get_base_device(name: str) -> str:
        # Handle nvme devices (nvme0n1p1 -> nvme0n1, but nvme0n1 stays as is)
        if "nvme" in name and "p" in name:
            return name.split("p")[0]
        # Handle mmcblk devices (mmcblk0p1 -> mmcblk0, but mmcblk0 stays as is)
        if "mmcblk" in name:
            if "p" in name:
                return name.split("p")[0]
            else:
                # For mmcblk0, mmcblk1, etc., return as-is
                return name
        # Handle regular devices (sda1 -> sda)
        # Strip trailing digits
        base = name.rstrip("0123456789")
        return base if base else name

    source_base = get_base_device(source_name)
    dest_base = get_base_device(dest_name)

    if source_base == dest_base:
        raise SourceDestinationSameError(source_name, dest_name)


def validate_device_unmounted(device) -> None:
    """Validate that a device and all its partitions are unmounted.

    Args:
        device: Device dict or device name

    Raises:
        DeviceBusyError: If device or any partition is mounted
        MountVerificationError: If specific mountpoint is active
    """
    device_name = _get_device_name(device)

    # Get device dict if we only have a name
    device_dict = device if isinstance(device, dict) else get_device_by_name(device_name)

    if not device_dict:
        # Can't verify unmount status without device info
        return

    # Check main device mountpoint
    main_mountpoint = device_dict.get("mountpoint")
    if main_mountpoint and _is_mountpoint_active(main_mountpoint):
        raise MountVerificationError(device_name, main_mountpoint)

    # Check all partition mountpoints
    for child in get_children(device_dict):
        child_name = child.get("name", "")
        child_mountpoint = child.get("mountpoint")
        if child_mountpoint and _is_mountpoint_active(child_mountpoint):
            raise MountVerificationError(device_name, child_mountpoint)


def validate_sufficient_space(source, destination) -> None:
    """Validate that destination has sufficient space for source data.

    Args:
        source: Source device dict
        destination: Destination device dict

    Raises:
        InsufficientSpaceError: If destination is too small
        DeviceValidationError: If size information is missing
    """
    source_name = _get_device_name(source)
    dest_name = _get_device_name(destination)

    # Get sizes from device dicts
    source_size = None
    dest_size = None

    if isinstance(source, dict):
        source_size = source.get("size")
    if isinstance(destination, dict):
        dest_size = destination.get("size")

    # If we don't have sizes, we can't validate
    if source_size is None:
        raise DeviceValidationError(
            source_name,
            "Cannot determine source device size"
        )
    if dest_size is None:
        raise DeviceValidationError(
            dest_name,
            "Cannot determine destination device size"
        )

    # Check if destination is large enough
    if dest_size < source_size:
        raise InsufficientSpaceError(
            source_name, source_size,
            dest_name, dest_size
        )


def validate_clone_operation(source, destination, check_space: bool = True) -> None:
    """Perform all validations required before a clone operation.

    This is a convenience function that runs all safety checks in the
    correct order.

    Args:
        source: Source device dict or name
        destination: Destination device dict or name
        check_space: Whether to validate sufficient space (default True)

    Raises:
        Various exceptions from the exceptions module if validation fails
    """
    # 1. Check devices exist
    validate_device_exists(source)
    validate_device_exists(destination)

    # 2. Check devices are different (CRITICAL)
    validate_devices_different(source, destination)

    # 3. Check destination is unmounted
    validate_device_unmounted(destination)

    # 4. Check sufficient space (optional, can be skipped for exact mode)
    # Only validate if both devices are dicts AND both have size information
    if check_space and isinstance(source, dict) and isinstance(destination, dict):
        source_size = source.get("size")
        dest_size = destination.get("size")
        # Only validate space if we have size info for both devices
        if source_size is not None and dest_size is not None:
            validate_sufficient_space(source, destination)


def validate_format_operation(device) -> None:
    """Perform all validations required before a format operation.

    Args:
        device: Device dict or name to format

    Raises:
        Various exceptions from the exceptions module if validation fails
    """
    # 1. Check device exists
    validate_device_exists(device)

    # 2. Check device is unmounted
    validate_device_unmounted(device)


def validate_erase_operation(device) -> None:
    """Perform all validations required before an erase operation.

    Args:
        device: Device dict or name to erase

    Raises:
        Various exceptions from the exceptions module if validation fails
    """
    # 1. Check device exists
    validate_device_exists(device)

    # 2. Check device is unmounted
    validate_device_unmounted(device)
