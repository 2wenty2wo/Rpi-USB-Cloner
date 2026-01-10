#!/usr/bin/env python
"""USB device mounting utilities with secure subprocess handling.

This module provides utilities for listing, mounting, and querying USB storage devices
on Linux systems. Originally vendored from an external source, it has been refactored
to eliminate security vulnerabilities.

SECURITY STATUS: ✅ FIXED (2024)
    All command injection vulnerabilities have been resolved by replacing os.system()
    calls with subprocess.run() using argument lists. Input validation added to prevent
    path traversal and malicious inputs.

Module Purpose:
    Provides utilities for listing, mounting, and querying USB storage devices on
    Linux systems. Originally designed as a standalone tool but integrated into
    the Rpi-USB-Cloner project.

Security Improvements:
    ✅ Replaced os.system() with subprocess.run() using argument lists
    ✅ Added input validation to prevent path traversal
    ✅ Added device path validation (/dev/ prefix required)
    ✅ Replaced hardcoded "output" file with proper command output handling
    ✅ Added proper error checking and exception raising
    ✅ Added error messages with context

Functions:
    - list_media_devices(): List all USB disk devices
    - get_device_name(): Extract device name from path
    - get_size(): Get device size in bytes
    - get_model(): Get device model string
    - get_vendor(): Get device vendor string
    - get_partition(): Get last partition using fdisk (FIXED)
    - mount_partition(): Mount a partition (FIXED)
    - unmount_partition(): Unmount a partition (FIXED)
    - mount(): Mount device's first partition (FIXED)
    - unmount(): Unmount device's partition (FIXED)

Example:
    >>> devices = list_media_devices()
    >>> for device in devices:
    ...     print(f"Device: {get_device_name(device)}")
    ...     print(f"Size: {get_size(device)} bytes")
    ...     print(f"Vendor: {get_vendor(device)}")

Original Attribution:
    Author: Christian Vallentin <mail@vallentinsource.com>
    Website: http://vallentinsource.com
    Repository: https://github.com/MrVallentin/mount.py
    Date Created: March 25, 2016
    Last Modified: March 27, 2016
    Security Fixes: January 2026
"""

import os
import subprocess
from pathlib import Path


def list_media_devices():
    # If the major number is 8, that indicates it to be a disk device.
    #
    # The minor number is the partitions on the same device:
    # - 0 means the entire disk
    # - 1 is the primary
    # - 2 is extended
    # - 5 is logical partitions
    # The maximum number of partitions is 15.
    #
    # Use `$ sudo fdisk -l` and `$ sudo sfdisk -l /dev/sda` for more information.
    with open("/proc/partitions", "r") as f:
        devices = []

        for line in f.readlines()[2:]:  # skip header lines
            words = [word.strip() for word in line.split()]
            minor_number = int(words[1])
            device_name = words[3]

            if (minor_number % 16) == 0:
                path = "/sys/class/block/" + device_name

                if os.path.islink(path):
                    if os.path.realpath(path).find("/usb") > 0:
                        devices.append("/dev/" + device_name)

        return devices


def get_device_name(device):
    return os.path.basename(device)


def get_device_block_path(device):
    return "/sys/block/%s" % get_device_name(device)


def get_media_path(device):
    return "/media/" + get_device_name(device)


def get_partition(device):
    """Get the last partition of a device using fdisk.

    Args:
            device: Device path (e.g., '/dev/sda')

    Returns:
            Partition device path (e.g., '/dev/sda1')

    Raises:
            ValueError: If device path is invalid
            RuntimeError: If fdisk fails or output cannot be parsed
    """
    # Validate device path to prevent command injection
    if not isinstance(device, str) or not device.startswith("/dev/"):
        raise ValueError(f"Invalid device path: {device}")

    # Additional validation: ensure no shell metacharacters
    if any(char in device for char in [";", "&", "|", "$", "`", "\n", "\r"]):
        raise ValueError(f"Device path contains invalid characters: {device}")

    try:
        # Use subprocess with argument list (safe from command injection)
        result = subprocess.run(
            ["fdisk", "-l", device], check=True, capture_output=True, text=True
        )

        # Parse output to find last partition
        lines = result.stdout.splitlines()
        partition_lines = [
            line.strip() for line in lines if line.strip().startswith("/dev/")
        ]
        if partition_lines:
            parts = partition_lines[-1].split()
            if parts:
                return parts[0].strip()

        raise RuntimeError(f"Could not find partition in fdisk output for {device}")

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"fdisk failed for {device}: {e.stderr.strip()}") from e


def is_mounted(device):
    return os.path.ismount(get_media_path(device))


def mount_partition(partition, name="usb"):
    """Mount a partition to /media/<name>.

    Args:
            partition: Device node (e.g., '/dev/sda1')
            name: Mount directory name (default: 'usb')

    Raises:
            ValueError: If inputs contain invalid characters
            RuntimeError: If mount operation fails
    """
    # Validate partition path
    if not isinstance(partition, str) or not partition.startswith("/dev/"):
        raise ValueError(f"Invalid partition path: {partition}")

    # Validate no shell metacharacters in partition
    if any(char in partition for char in [";", "&", "|", "$", "`", "\n", "\r", " "]):
        raise ValueError(f"Partition path contains invalid characters: {partition}")

    # Sanitize name to prevent path traversal
    name = str(name)
    name_path = Path(name)
    # Get only the final component, stripping any parent directories
    name = name_path.name

    # Reject suspicious names
    if not name or name in (".", "..") or "/" in name:
        raise ValueError(f"Invalid mount name: {name}")

    path = get_media_path(name)

    if not is_mounted(path):
        try:
            # Create mount directory using subprocess
            subprocess.run(
                ["mkdir", "-p", path], check=True, capture_output=True, text=True
            )

            # Mount the partition using subprocess
            subprocess.run(
                ["mount", partition, path], check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to mount {partition} to {path}: {e.stderr.strip()}"
            ) from e


def unmount_partition(name="usb"):
    """Unmount a partition from /media/<name>.

    Args:
            name: Mount directory name (default: 'usb')

    Raises:
            ValueError: If name contains invalid characters
            RuntimeError: If unmount operation fails
    """
    # Sanitize name to prevent path traversal
    name = str(name)
    name_path = Path(name)
    # Get only the final component, stripping any parent directories
    name = name_path.name

    # Reject suspicious names
    if not name or name in (".", "..") or "/" in name:
        raise ValueError(f"Invalid mount name: {name}")

    path = get_media_path(name)

    if is_mounted(path):
        try:
            subprocess.run(["umount", path], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to unmount {path}: {e.stderr.strip()}") from e


def mount(device, name=None):
    """Mount a device's first partition to /media/<name>.

    Args:
            device: Device path (e.g., '/dev/sda')
            name: Mount directory name (default: device name)

    Raises:
            ValueError: If device path is invalid
            RuntimeError: If partition detection or mount fails
    """
    if not name:
        name = get_device_name(device)
    mount_partition(get_partition(device), name)


def unmount(device, name=None):
    """Unmount a device's partition from /media/<name>.

    Args:
            device: Device path (e.g., '/dev/sda')
            name: Mount directory name (default: device name)

    Raises:
            ValueError: If inputs are invalid
            RuntimeError: If unmount fails
    """
    if not name:
        name = get_device_name(device)
    unmount_partition(name)


def is_removable(device):
    path = get_device_block_path(device) + "/removable"

    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read().strip() == "1"

    return None


def get_size(device):
    path = get_device_block_path(device) + "/size"

    if os.path.exists(path):
        with open(path, "r") as f:
            # Multiply by 512, as Linux sectors are always considered to be 512 bytes long
            # Resource: https://git.kernel.org/cgit/linux/kernel/git/torvalds/linux.git/tree/include/linux/types.h?id=v4.4-rc6#n121
            return int(f.read().strip()) * 512

    return -1


def get_model(device):
    path = get_device_block_path(device) + "/device/model"

    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read().strip()
    return None


def get_vendor(device):
    path = get_device_block_path(device) + "/device/vendor"

    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read().strip()
    return None


if __name__ == "__main__":
    devices = list_media_devices()

    for device in devices:
        mount(device)

        print("Drive:", get_device_name(device))
        print("Mounted:", "Yes" if is_mounted(device) else "No")
        print("Removable:", "Yes" if is_removable(device) else "No")
        print("Size:", get_size(device), "bytes")
        print("Size:", "%.2f" % (get_size(device) / 1024**3), "GB")
        print("Model:", get_model(device))
        print("Vendor:", get_vendor(device))
        print(" ")

        unmount(device)
