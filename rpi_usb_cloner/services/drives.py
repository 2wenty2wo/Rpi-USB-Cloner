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

from rpi_usb_cloner.domain import Drive
from rpi_usb_cloner.logging import get_logger
from rpi_usb_cloner.storage import devices as storage_devices
from rpi_usb_cloner.storage.devices import format_device_label, list_usb_disks
from rpi_usb_cloner.storage.image_repo import find_image_repos


log = get_logger(source=__name__)


# Cache for repo device names to avoid expensive scanning on every menu render
_repo_device_cache: set[str] | None = None

# Startup time tracking to avoid caching empty results before partitions mount
_startup_time: float | None = None
_STARTUP_GRACE_PERIOD = 3.0  # Don't cache empty results for 3 seconds after startup


@dataclass
class DriveSnapshot:
    discovered: list[str]
    active: str | None


@dataclass
class USBSnapshot:
    """Complete USB device snapshot in a single pass.

    This dataclass holds all USB device information needed by the main loop,
    collected in a single lsblk call to minimize system overhead.

    Attributes:
        raw_devices: List of all USB device names (e.g., ['sda', 'sdb'])
        media_devices: List of media drive names (excluding repos)
        mountpoints: List of (device_name, mountpoint) tuples for all USB devices
    """

    raw_devices: list[str]
    media_devices: list[str]
    mountpoints: list[tuple[str, str]]


def get_usb_snapshot() -> USBSnapshot:
    """Get complete USB device snapshot in a single pass.

    This function is optimized for the main event loop, collecting all
    USB device information with minimal system calls. It performs a
    single lsblk invocation and extracts:
    - Raw USB device names (all USB disks)
    - Media device names (excluding repo drives)
    - Mountpoint mappings for all USB devices

    Returns:
        USBSnapshot containing all device information

    Performance:
        - Single lsblk call (uses 1-second cache in get_block_devices)
        - Single pass through device list
        - ~3x faster than calling separate functions

    Example:
        >>> snapshot = get_usb_snapshot()
        >>> print(f"Found {len(snapshot.raw_devices)} USB devices")
        >>> print(f"Media drives: {snapshot.media_devices}")
        >>> print(f"Mountpoints: {snapshot.mountpoints}")
    """
    # Import here to avoid circular dependency at module load
    from rpi_usb_cloner.storage.devices import get_block_devices, get_children

    repo_devices = _get_repo_device_names()
    raw_devices: list[str] = []
    media_devices: list[str] = []
    mountpoints: list[tuple[str, str]] = []

    def collect_mountpoints(device: dict, device_name: str) -> None:
        """Recursively collect mountpoints from device and children."""
        mountpoint = device.get("mountpoint")
        if mountpoint:
            mountpoints.append((device_name, mountpoint))
        for child in get_children(device):
            collect_mountpoints(child, device_name)

    # Single pass through all block devices
    for device in get_block_devices():
        if device.get("type") != "disk":
            continue

        # Check if it's a USB device
        tran = device.get("tran")
        rm = device.get("rm")
        if tran != "usb" and rm != 1:
            continue

        # Skip root device (system disk)
        from rpi_usb_cloner.storage.devices import has_root_mountpoint

        if has_root_mountpoint(device):
            continue

        device_name = device.get("name")
        if not device_name:
            continue

        # Add to raw devices list
        raw_devices.append(device_name)

        # Collect mountpoints for this device
        collect_mountpoints(device, device_name)

        # Add to media devices if not a repo drive
        if device_name not in repo_devices:
            media_devices.append(device_name)

    return USBSnapshot(
        raw_devices=sorted(raw_devices),
        media_devices=sorted(media_devices),
        mountpoints=sorted(mountpoints),
    )


def _collect_mountpoints(device: dict) -> set[str]:
    """Collect all mountpoints for a device and its partitions."""
    mountpoints: set[str] = set()
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


def _get_repo_device_names() -> set[str]:
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
        log.debug("Initialized repo cache startup time")

    # Return cached value if available
    if _repo_device_cache is not None:
        return _repo_device_cache

    # Scan for repo devices (expensive operation)
    log.debug("Scanning for repo devices...")
    repos = find_image_repos()
    log.debug(f"Found {len(repos)} repo path(s): {repos}")

    if not repos:
        import time

        elapsed = time.time() - _startup_time
        in_grace_period = elapsed < _STARTUP_GRACE_PERIOD

        if in_grace_period:
            # Don't cache empty results during startup grace period
            # USB partitions may still be mounting
            log.debug(
                f"No repos found (startup grace period: {elapsed:.1f}s/{_STARTUP_GRACE_PERIOD}s), "
                "not caching empty result"
            )
            return set()
        # After grace period, cache the empty result
        _repo_device_cache = set()
        log.debug(f"No repos found (after {elapsed:.1f}s), caching empty set")
        return _repo_device_cache

    repo_devices: set[str] = set()
    usb_devices = list_usb_disks()
    repo_paths = [repo.path.resolve(strict=False) for repo in repos]
    log.debug(f"Checking {len(usb_devices)} USB device(s) against repo paths")

    for device in usb_devices:
        device_name = device.get("name")
        mountpoints = _collect_mountpoints(device)
        log.debug(f"Device {device_name}: mountpoints = {mountpoints}")

        for mount in mountpoints:
            mount_path = Path(mount).resolve(strict=False)
            for repo_path in repo_paths:
                is_match = _is_repo_on_mount(repo_path, mount_path)
                if is_match:
                    log.debug(f"  MATCH: repo {repo_path} on mount {mount_path}")
                    if device_name:
                        repo_devices.add(device_name)
                        break

    # Cache the result
    log.debug(f"Identified repo devices: {repo_devices}")
    _repo_device_cache = repo_devices
    return repo_devices


def list_media_drives() -> list[Drive]:
    """List media drives as domain objects, excluding repo drives.

    Returns type-safe Drive objects instead of raw dicts. This is the
    preferred function for new code.

    Returns:
        List of Drive domain objects representing non-repo USB drives
    """
    repo_devices = _get_repo_device_names()
    drives = []
    for device in list_usb_disks():
        device_name = device.get("name")
        if device_name and device_name not in repo_devices:
            try:
                drive = Drive.from_lsblk_dict(device)
                drives.append(drive)
            except (KeyError, ValueError) as error:
                # Skip devices that can't be converted (malformed lsblk data)
                log.debug(f"Skipping device {device_name}: {error}")
                continue
    return drives


def list_media_drive_names() -> list[str]:
    """List media drive names, excluding repo drives.

    Note: For new code, prefer list_media_drives() which returns
    type-safe Drive objects.
    """
    return [drive.name for drive in list_media_drives()]


def list_media_drive_labels() -> list[str]:
    """List media drive labels, excluding repo drives.

    Note: For new code, prefer list_media_drives() which returns
    Drive objects with a format_label() method.
    """
    return [drive.format_label() for drive in list_media_drives()]


def list_usb_disk_names() -> list[str]:
    """List USB disk names, excluding repo drives."""
    repo_devices = _get_repo_device_names()
    names: list[str] = []
    for device in list_usb_disks():
        name = device.get("name")
        if name and name not in repo_devices:
            names.append(name)
    return names


def list_raw_usb_disk_names() -> list[str]:
    """List USB disk names without filtering repo drives."""
    names: list[str] = []
    for device in list_usb_disks():
        name = device.get("name")
        if name:
            names.append(name)
    return names


def list_usb_disk_labels() -> list[str]:
    """List USB disk labels, excluding repo drives."""
    repo_devices = _get_repo_device_names()
    return [
        format_device_label(device)
        for device in list_usb_disks()
        if device.get("name") not in repo_devices
    ]


def list_usb_disks_filtered() -> list[dict]:
    """List USB disks, excluding repo drives.

    Returns the full device dictionaries (like list_usb_disks) but filters
    out devices that are identified as image repositories.
    """
    repo_devices = _get_repo_device_names()
    return [
        device for device in list_usb_disks() if device.get("name") not in repo_devices
    ]


def refresh_drives(active_drive: str | None) -> DriveSnapshot:
    discovered = list_media_drive_names()
    active = active_drive if active_drive in discovered else None
    return DriveSnapshot(discovered=discovered, active=active)


def select_active_drive(
    discovered: list[str],
    selected_index: int,
) -> str | None:
    if not discovered:
        return None
    if selected_index < 0:
        return discovered[0]
    if selected_index >= len(discovered):
        return discovered[-1]
    return discovered[selected_index]


def get_active_drive_label(active_drive: str | None) -> str | None:
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


def get_drive_counts() -> tuple[int, int]:
    """Get counts of USB drives and repo drives.

    Returns:
        Tuple of (usb_count, repo_count) where:
        - usb_count: Number of non-repo USB drives
        - repo_count: Number of repo drives
    """
    repo_devices = _get_repo_device_names()
    all_devices = list_usb_disks()
    all_device_names = {d.get("name") for d in all_devices if d.get("name")}

    repo_count = len(repo_devices & all_device_names)
    usb_count = len(all_device_names - repo_devices)

    return usb_count, repo_count
