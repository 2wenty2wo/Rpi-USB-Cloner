"""USB device detection, management, and filtering using lsblk.

This module provides utilities for detecting, querying, and managing USB storage devices
on Raspberry Pi systems. It uses the lsblk command to gather device information and
implements filtering logic to identify safe-to-modify removable devices.

Device Detection:
    Uses lsblk with JSON output to enumerate block devices and their properties:
    - Device name (e.g., sda, sdb)
    - Size in bytes
    - Mountpoints (if any)
    - Filesystem type
    - Partition information
    - Vendor and model strings
    - Removable device flag
    - USB subsystem detection via /sys/block/*/device path checking

Filtering Logic:
    The module implements safety filters to prevent accidental modification of system
    disks:

    1. Must be marked as removable (rm=1 in lsblk output)
    2. Must NOT be mounted to critical system paths (/, /boot, /boot/firmware)
    3. Must NOT have child partitions mounted to system paths
    4. Must be accessible via USB subsystem (/sys/block/*/device contains "usb")

    This filtering is critical for safety but is NOT foolproof. The module does not
    verify device nodes against /sys/block/*/removable before destructive operations.

Operations:
    - list_media_drive_names(): Get list of removable USB device names
    - get_device_by_name(): Retrieve detailed device information
    - unmount_device(): Unmount device and all partitions
    - format_device_label(): Create human-readable device labels
    - human_size(): Convert bytes to human-readable format (KB/MB/GB)

Mount Management:
    The unmount_device() function attempts to unmount all partitions of a device before
    operations. However, it silently ignores unmount failures (see lines 133-142),
    which can lead to data corruption if operations proceed on mounted devices.

Security Issues:
    1. Silent umount failures - operations may proceed on mounted devices
    2. No validation that source != destination before cloning
    3. No verification that device is actually removable before destructive ops
    4. Race conditions possible between detection and operation

Example:
    >>> from rpi_usb_cloner.storage.devices import list_media_drive_names
    >>> usb_devices = list_media_drive_names()
    >>> print(f"Found {len(usb_devices)} USB drives: {usb_devices}")
    Found 2 USB drives: ['sda', 'sdb']

    >>> from rpi_usb_cloner.storage.devices import get_device_by_name
    >>> device = get_device_by_name('sda')
    >>> print(f"Device: {device['name']}, Size: {human_size(device['size'])}")
    Device: sda, Size: 7.5GB

Implementation Notes:
    - Relies on lsblk command availability (standard on Raspberry Pi OS)
    - Uses JSON parsing for structured output
    - Global _log_debug and _error_handler for debugging and error reporting
    - Must be configured with configure_device_helpers() before use
"""
import json
import os
import re
import subprocess
import time
from typing import Callable, Iterable, Optional

ROOT_MOUNTPOINTS = {"/", "/boot", "/boot/firmware"}
LSBLK_CACHE_TTL_SECONDS = 1.0

_log_debug: Callable[[str], None]
_error_handler: Optional[Callable[[Iterable[str]], None]]
_last_lsblk_names: Optional[tuple[str, ...]] = None
_lsblk_cache: Optional[list[dict]] = None
_lsblk_cache_time: Optional[float] = None


def _noop_logger(message: str) -> None:
    return None


_log_debug = _noop_logger
_error_handler = None


def configure_device_helpers(
    log_debug: Optional[Callable[[str], None]] = None,
    error_handler: Optional[Callable[[Iterable[str]], None]] = None,
) -> None:
    global _log_debug, _error_handler
    _log_debug = log_debug or _noop_logger
    _error_handler = error_handler


def run_command(command, check=True, log_output=True, log_command=True):
    if log_command:
        _log_debug(f"Running command: {' '.join(command)}")
    try:
        result = subprocess.run(command, check=check, text=True, capture_output=True)
    except subprocess.CalledProcessError as error:
        _log_debug(f"Command failed: {' '.join(command)}")
        if error.stdout:
            _log_debug(f"stdout: {error.stdout.strip()}")
        if error.stderr:
            _log_debug(f"stderr: {error.stderr.strip()}")
        raise
    if result.stdout and (log_output or result.returncode != 0):
        _log_debug(f"stdout: {result.stdout.strip()}")
    if result.stderr and (log_output or result.returncode != 0):
        _log_debug(f"stderr: {result.stderr.strip()}")
    if log_command:
        _log_debug(f"Command completed with return code {result.returncode}")
    return result


def human_size(size_bytes):
    if size_bytes is None:
        return "0B"
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}PB"


def format_device_label(device):
    if isinstance(device, dict):
        name = device.get("name") or ""
        size_label = human_size(device.get("size"))
    else:
        name = str(device or "")
        size_label = ""
    if size_label:
        size_label = re.sub(r"\.0([A-Z])", r"\1", size_label)
        return f"{name} {size_label}".strip()
    return name


def get_block_devices(force_refresh: bool = False):
    """Return block device data from lsblk with a short-lived cache.

    When lsblk fails or returns invalid JSON, the previous cache remains intact
    and is returned if available; otherwise an empty list is returned. When
    force_refresh=True, errors return an empty list so callers do not receive
    stale data.
    """
    global _last_lsblk_names, _lsblk_cache, _lsblk_cache_time
    now = time.monotonic()
    if (
        not force_refresh
        and _lsblk_cache is not None
        and _lsblk_cache_time is not None
        and now - _lsblk_cache_time <= LSBLK_CACHE_TTL_SECONDS
    ):
        return _lsblk_cache
    try:
        result = run_command(
            [
                "lsblk",
                "-J",
                "-b",
                "-o",
                "NAME,TYPE,SIZE,MODEL,VENDOR,TRAN,RM,MOUNTPOINT,FSTYPE,LABEL,SERIAL,PTTYPE,ROTA,PTUUID",
            ],
            log_output=False,
            log_command=False,
        )
        data = json.loads(result.stdout)
        devices = data.get("blockdevices", [])
        device_names = tuple(device.get("name") for device in devices if device.get("name"))
        if device_names != _last_lsblk_names:
            if device_names:
                _log_debug(
                    f"lsblk found {len(device_names)} devices: {', '.join(device_names)}"
                )
            else:
                _log_debug("lsblk found no block devices")
            _last_lsblk_names = device_names
        _lsblk_cache = devices
        _lsblk_cache_time = now
        return devices
    except (subprocess.CalledProcessError, json.JSONDecodeError) as error:
        if _error_handler:
            _error_handler(["LSBLK ERROR", str(error)])
        _log_debug(f"lsblk failed: {error}")
        if _lsblk_cache is not None and not force_refresh:
            return _lsblk_cache
        return []


def get_children(device):
    return device.get("children", []) or []


def get_device_by_name(name):
    if not name:
        return None
    for device in get_block_devices():
        if device.get("name") == name:
            return device
    return None


def has_root_mountpoint(device):
    mountpoint = device.get("mountpoint")
    if mountpoint in ROOT_MOUNTPOINTS:
        return True
    for child in get_children(device):
        if has_root_mountpoint(child):
            return True
    return False


def is_root_device(device):
    if device.get("type") != "disk":
        return False
    return has_root_mountpoint(device)


def list_usb_disks():
    devices = []
    for device in get_block_devices():
        if device.get("type") != "disk":
            continue
        if is_root_device(device):
            continue
        tran = device.get("tran")
        rm = device.get("rm")
        if tran == "usb" or rm == 1:
            devices.append(device)
    return devices


def _is_mountpoint_active(mountpoint: str) -> bool:
    try:
        with open("/proc/mounts", "r", encoding="utf-8") as mounts_file:
            for line in mounts_file:
                parts = line.split()
                if len(parts) > 1 and parts[1] == mountpoint:
                    return True
    except FileNotFoundError:
        return os.path.ismount(mountpoint)
    return False


def _collect_device_mountpoints(device: dict) -> list[str]:
    mountpoints: list[str] = []
    for child in get_children(device):
        mountpoint = child.get("mountpoint")
        if mountpoint:
            mountpoints.append(mountpoint)
    mountpoint = device.get("mountpoint")
    if mountpoint:
        mountpoints.append(mountpoint)
    return mountpoints


def unmount_device(device) -> bool:
    mountpoints = _collect_device_mountpoints(device)
    if not mountpoints:
        return True

    success, _used_lazy = unmount_device_with_retry(device, log_debug=_log_debug)
    if success:
        return True

    failed_mounts = [mp for mp in mountpoints if _is_mountpoint_active(mp)]
    if failed_mounts:
        _log_debug(f"Failed to unmount mountpoints: {', '.join(failed_mounts)}")
        if _error_handler:
            _error_handler(["UNMOUNT FAILED", *failed_mounts])
    return False


def unmount_device_with_retry(
    device: dict,
    log_debug: Optional[Callable[[str], None]] = None,
) -> tuple[bool, bool]:
    """Unmount device with retry and optional lazy unmount.

    Args:
        device: Device dict from lsblk
        log_debug: Optional debug logging function

    Returns:
        Tuple of (success, used_lazy_unmount)
    """
    import time

    device_name = device.get("name")

    def log(msg: str):
        if log_debug:
            log_debug(msg)

    def filter_active_mountpoints(
        mountpoint_list: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        active = []
        for partition_name, mountpoint in mountpoint_list:
            if _is_mountpoint_active(mountpoint):
                active.append((partition_name, mountpoint))
            else:
                log(f"{mountpoint} already unmounted")
        return active

    # Collect all mountpoints
    mountpoints = []
    if device.get("mountpoint"):
        mountpoints.append((device.get("name"), device.get("mountpoint")))
    for child in get_children(device):
        if child.get("mountpoint"):
            mountpoints.append((child.get("name"), child.get("mountpoint")))

    if not mountpoints:
        log(f"No mounted partitions on {device_name}")
        return True, False

    # Sync filesystem buffers first
    try:
        log("Syncing filesystem buffers...")
        run_command(["sync"], check=False)
        time.sleep(0.5)
    except Exception as error:
        log(f"Sync failed: {error}")

    # Try normal unmount first (3 attempts)
    for attempt in range(1, 4):
        log(f"Unmount attempt {attempt}/3...")
        active_mountpoints = filter_active_mountpoints(mountpoints)
        if not active_mountpoints:
            log("Successfully unmounted all partitions")
            return True, False

        all_unmounted = True

        for partition_name, mountpoint in active_mountpoints:
            try:
                run_command(["umount", mountpoint], check=True)
                log(f"Unmounted {mountpoint}")
            except subprocess.CalledProcessError as error:
                log(f"Failed to unmount {mountpoint}: {error}")
                all_unmounted = False

        if all_unmounted and not filter_active_mountpoints(mountpoints):
            log("Successfully unmounted all partitions")
            return True, False

        # Wait before retry
        if attempt < 3:
            time.sleep(1)

    # Normal unmount failed - ask about lazy unmount
    # Note: In the action handler, this will trigger a user prompt
    # For now, we'll attempt lazy unmount automatically after normal fails

    log("Normal unmount failed, attempting lazy unmount...")

    # Try lazy unmount
    all_unmounted = True
    active_mountpoints = filter_active_mountpoints(mountpoints)
    if not active_mountpoints:
        log("All partitions already unmounted before lazy unmount")
        return True, False

    for partition_name, mountpoint in active_mountpoints:
        try:
            run_command(["umount", "-l", mountpoint], check=True)
            log(f"Lazy unmounted {mountpoint}")
        except subprocess.CalledProcessError as error:
            log(f"Failed to lazy unmount {mountpoint}: {error}")
            all_unmounted = False

    if all_unmounted and not filter_active_mountpoints(mountpoints):
        log("Successfully lazy unmounted all partitions")
        return True, True

    log("Failed to unmount device even with lazy unmount")
    return False, False


def power_off_device(
    device: dict,
    log_debug: Optional[Callable[[str], None]] = None,
) -> bool:
    """Power off a USB device safely.

    Args:
        device: Device dict from lsblk
        log_debug: Optional debug logging function

    Returns:
        True on success, False on failure
    """
    device_name = device.get("name")
    device_path = f"/dev/{device_name}"

    def log(msg: str):
        if log_debug:
            log_debug(msg)

    # Try udisksctl first (preferred method)
    try:
        log(f"Powering off {device_name} with udisksctl...")
        run_command(["udisksctl", "power-off", "-b", device_path], check=True)
        log(f"Successfully powered off {device_name}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        log(f"udisksctl power-off failed: {error}")

    # Fallback to hdparm (spindown for HDDs)
    try:
        log(f"Attempting hdparm spindown for {device_name}...")
        run_command(["hdparm", "-Y", device_path], check=True)
        log(f"Successfully spun down {device_name}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        log(f"hdparm spindown failed: {error}")

    log(f"Failed to power off {device_name}")
    return False
