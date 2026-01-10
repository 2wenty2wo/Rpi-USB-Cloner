"""Drive listing and selection utilities for USB device management.

This module provides high-level utilities for working with USB drives, building on
the lower-level device detection in rpi_usb_cloner.storage.devices and
rpi_usb_cloner.storage.mount.

Purpose:
    Acts as a service layer between the UI and storage layers, providing:
    - Simplified drive listing functions
    - Drive selection logic
    - Human-readable drive labels
    - Drive state snapshots

Functions:
    - list_media_drive_names(): Get list of device names (e.g., ['sda', 'sdb'])
    - list_media_drive_labels(): Get formatted labels (e.g., ['sda 8.00GB', 'sdb 16.00GB'])
    - list_usb_disk_labels(): Get USB disk labels with vendor/model info
    - select_active_drive(): Choose active drive from list with validation

DriveSnapshot:
    Dataclass for capturing drive state at a point in time:
    - discovered: List of all detected drive names
    - active: Currently selected drive (None if no selection)

    Used for detecting changes in USB device connectivity.

Drive Selection Logic:
    select_active_drive() implements safe drive selection:
    1. If no drives available, return None
    2. If index out of range, return None
    3. Otherwise return drive at index

    This prevents index errors when drives are hotplugged/unplugged.

Label Formatting:
    Drive labels include human-readable information:
    - Device name (sda, sdb, etc.)
    - Size in GB with 2 decimal places
    - Vendor and model (when available)

    Format: "sda 8.00GB" or "sda Kingston DataTraveler (8.00GB)"

Example:
    >>> from rpi_usb_cloner.services import drives
    >>> drive_names = drives.list_media_drive_names()
    >>> print(f"Found drives: {drive_names}")
    Found drives: ['sda', 'sdb']

    >>> labels = drives.list_media_drive_labels()
    >>> print(labels)
    ['sda 8.00GB', 'sdb 16.00GB']

    >>> active = drives.select_active_drive(drive_names, index=0)
    >>> print(f"Selected: {active}")
    Selected: sda

Implementation Notes:
    - Delegates device detection to storage.devices and storage.mount
    - Does not cache results; queries devices on each call
    - Thread-safe if underlying device queries are thread-safe
    - Performance: Each call executes lsblk command

See Also:
    - rpi_usb_cloner.storage.devices: Low-level device detection
    - rpi_usb_cloner.storage.mount: Device mounting utilities
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

from rpi_usb_cloner.storage import devices as storage_devices
from rpi_usb_cloner.storage.devices import format_device_label, list_usb_disks
from rpi_usb_cloner.storage.image_repo import find_image_repos
from rpi_usb_cloner.storage.mount import (get_device_name, get_size,
                                          list_media_devices)


@dataclass
class DriveSnapshot:
    discovered: List[str]
    active: Optional[str]


def _collect_mountpoints(device: dict) -> Set[str]:
    """Collect all mountpoints for a device and its partitions."""
    mountpoints: Set[str] = set()
    stack = [device]
    while stack:
        current = stack.pop()
        mountpoint = current.get("mountpoint")
        if mountpoint:
            mountpoints.add(mountpoint)
        stack.extend(storage_devices.get_children(current))
    return mountpoints


def _is_repo_on_mount(repo_path: Path, mount_path: Path) -> bool:
    """Return True if repo_path is on mount_path, matching path boundaries."""
    return repo_path == mount_path or mount_path in repo_path.parents


def _get_repo_device_names() -> Set[str]:
    """Get the set of device names that are repo drives."""
    repos = find_image_repos()
    if not repos:
        return set()

    repo_devices: Set[str] = set()
    usb_devices = list_usb_disks()
    repo_paths = [Path(repo).resolve(strict=False) for repo in repos]

    for device in usb_devices:
        mountpoints = _collect_mountpoints(device)
        if any(
            _is_repo_on_mount(repo_path, Path(mount).resolve(strict=False))
            for mount in mountpoints
            for repo_path in repo_paths
        ):
            device_name = device.get("name")
            if device_name:
                repo_devices.add(device_name)

    return repo_devices


def list_media_drive_names() -> List[str]:
    """List media drive names, excluding repo drives."""
    repo_devices = _get_repo_device_names()
    return [
        get_device_name(device)
        for device in list_media_devices()
        if get_device_name(device) not in repo_devices
    ]


def list_media_drive_labels() -> List[str]:
    """List media drive labels, excluding repo drives."""
    repo_devices = _get_repo_device_names()
    labels = []
    for device in list_media_devices():
        device_name = get_device_name(device)
        if device_name not in repo_devices:
            label = f"{device_name} {get_size(device) / 1024 ** 3:.2f}GB"
            labels.append(label)
    return labels


def list_usb_disk_names() -> List[str]:
    """List USB disk names, excluding repo drives."""
    repo_devices = _get_repo_device_names()
    return [
        device.get("name")
        for device in list_usb_disks()
        if device.get("name") and device.get("name") not in repo_devices
    ]


def list_usb_disk_labels() -> List[str]:
    """List USB disk labels, excluding repo drives."""
    repo_devices = _get_repo_device_names()
    return [
        format_device_label(device)
        for device in list_usb_disks()
        if device.get("name") not in repo_devices
    ]


def refresh_drives(active_drive: Optional[str]) -> DriveSnapshot:
    discovered = list_media_drive_names()
    active = active_drive if active_drive in discovered else None
    return DriveSnapshot(discovered=discovered, active=active)


def select_active_drive(
    discovered: List[str],
    selected_index: int,
) -> Optional[str]:
    if not discovered:
        return None
    if selected_index < 0:
        return discovered[0]
    if selected_index >= len(discovered):
        return discovered[-1]
    return discovered[selected_index]


def get_active_drive_label(active_drive: Optional[str]) -> Optional[str]:
    if not active_drive:
        return None
    for device in list_media_devices():
        if get_device_name(device) == active_drive:
            return f"{get_device_name(device)} {get_size(device) / 1024 ** 3:.2f}GB"
    return active_drive
