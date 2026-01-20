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

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

from rpi_usb_cloner.storage import devices as storage_devices
from rpi_usb_cloner.storage.devices import format_device_label, list_usb_disks
from rpi_usb_cloner.storage.image_repo import find_image_repos
from rpi_usb_cloner.storage.mount import get_device_name, get_size, list_media_devices

logger = logging.getLogger(__name__)


# Cache for repo device names to avoid expensive scanning on every menu render
_repo_device_cache: Optional[Set[str]] = None

# Startup time tracking to avoid caching empty results before partitions mount
_startup_time: Optional[float] = None
_STARTUP_GRACE_PERIOD = 3.0  # Don't cache empty results for 3 seconds after startup


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


def invalidate_repo_cache() -> None:
    """Invalidate the repo device cache.

    Call this when USB devices change to force a rescan of repo devices.
    This avoids expensive partition scanning on every menu render while still
    staying up-to-date when devices are added/removed.
    """
    global _repo_device_cache
    _repo_device_cache = None


def _get_repo_device_names() -> Set[str]:
    """Get the set of device names that are repo drives.

    This function caches results to avoid expensive partition scanning on every
    menu render. The cache is invalidated when USB devices change.

    During the initial startup grace period, empty results are not cached to
    allow time for USB partitions to mount and repo flag files to become visible.
    """
    global _repo_device_cache, _startup_time

    # Initialize startup time on first call
    if _startup_time is None:
        import time
        _startup_time = time.time()
        logger.debug("Initialized repo cache startup time")

    # Return cached value if available
    if _repo_device_cache is not None:
        logger.debug(f"Returning cached repo devices: {_repo_device_cache}")
        return _repo_device_cache

    # Scan for repo devices (expensive operation)
    logger.debug("Scanning for repo devices...")
    repos = find_image_repos()
    logger.debug(f"Found {len(repos)} repo path(s): {repos}")

    if not repos:
        import time
        elapsed = time.time() - _startup_time
        in_grace_period = elapsed < _STARTUP_GRACE_PERIOD

        if in_grace_period:
            # Don't cache empty results during startup grace period
            # USB partitions may still be mounting
            logger.debug(
                f"No repos found (startup grace period: {elapsed:.1f}s/{_STARTUP_GRACE_PERIOD}s), "
                "not caching empty result"
            )
            return set()
        else:
            # After grace period, cache the empty result
            _repo_device_cache = set()
            logger.debug(f"No repos found (after {elapsed:.1f}s), caching empty set")
            return _repo_device_cache

    repo_devices: Set[str] = set()
    usb_devices = list_usb_disks()
    repo_paths = [Path(repo).resolve(strict=False) for repo in repos]
    logger.debug(f"Checking {len(usb_devices)} USB device(s) against repo paths")

    for device in usb_devices:
        device_name = device.get("name")
        mountpoints = _collect_mountpoints(device)
        logger.debug(f"Device {device_name}: mountpoints = {mountpoints}")

        for mount in mountpoints:
            mount_path = Path(mount).resolve(strict=False)
            for repo_path in repo_paths:
                is_match = _is_repo_on_mount(repo_path, mount_path)
                if is_match:
                    logger.debug(f"  MATCH: repo {repo_path} on mount {mount_path}")
                    if device_name:
                        repo_devices.add(device_name)
                        break

    # Cache the result
    logger.debug(f"Identified repo devices: {repo_devices}")
    _repo_device_cache = repo_devices
    return repo_devices


def list_media_drive_names() -> List[str]:
    """List media drive names, excluding repo drives."""
    repo_devices = _get_repo_device_names()
    return [
        device.get("name")
        for device in list_usb_disks()
        if device.get("name") and device.get("name") not in repo_devices
    ]


def list_media_drive_labels() -> List[str]:
    """List media drive labels, excluding repo drives."""
    repo_devices = _get_repo_device_names()
    labels = []
    for device in list_usb_disks():
        device_name = device.get("name")
        if device_name and device_name not in repo_devices:
            size_bytes = device.get("size", 0)
            label = f"{device_name} {size_bytes / 1024 ** 3:.2f}GB"
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


def list_raw_usb_disk_names() -> List[str]:
    """List USB disk names without filtering repo drives."""
    return [device.get("name") for device in list_usb_disks() if device.get("name")]


def list_usb_disk_labels() -> List[str]:
    """List USB disk labels, excluding repo drives."""
    repo_devices = _get_repo_device_names()
    return [
        format_device_label(device)
        for device in list_usb_disks()
        if device.get("name") not in repo_devices
    ]


def list_usb_disks_filtered() -> List[dict]:
    """List USB disks, excluding repo drives.

    Returns the full device dictionaries (like list_usb_disks) but filters
    out devices that are identified as image repositories.
    """
    repo_devices = _get_repo_device_names()
    return [
        device
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
    # Don't show label for repo drives
    repo_devices = _get_repo_device_names()
    if active_drive in repo_devices:
        return None
    for device in list_usb_disks():
        device_name = device.get("name")
        if device_name == active_drive:
            size_bytes = device.get("size", 0)
            return f"{device_name} {size_bytes / 1024 ** 3:.2f}GB"
    return active_drive
