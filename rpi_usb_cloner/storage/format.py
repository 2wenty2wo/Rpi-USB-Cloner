"""USB drive formatting operations with progress tracking.

This module implements USB drive formatting functionality for the Rpi-USB-Cloner,
supporting multiple filesystem types with MBR partitioning.

Supported Filesystems:
    ext4:   Linux native filesystem (recommended for Raspberry Pi)
    vfat:   FAT32 filesystem for universal compatibility (≤32GB recommended)
    exfat:  exFAT filesystem for large drives and files (≥64GB recommended)
    ntfs:   NTFS filesystem for Windows compatibility

Format Modes:
    quick:  Fast format without bad block checking
    full:   Complete format with bad block checking (slower but thorough)

Partitioning:
    - Uses MBR (Master Boot Record) partition table by default
    - Creates a single primary partition using full device capacity
    - Partition starts at 1MiB offset for proper alignment

Operations:
    - format_device(): Main entry point for formatting
    - _create_partition_table(): Creates MBR partition table
    - _create_partition(): Creates single primary partition
    - _format_filesystem(): Formats partition with chosen filesystem

Implementation Details:
    - Uses parted for partition management
    - Uses mkfs.* tools for filesystem creation
    - Automatically unmounts devices before operations
    - Supports progress callbacks for UI updates
    - Full mode adds bad block checking (-c flag)

Security Notes:
    - All operations require root privileges
    - Devices must be validated before formatting
    - System and repository drives are blocked

Example:
    >>> from rpi_usb_cloner.storage.format import format_device
    >>> device = {"name": "sda", "size": 32000000000}
    >>> success = format_device(device, "vfat", "quick", label="BACKUP")
"""

import os
import re
import select
import shutil
import subprocess
import time
from typing import Callable, List, Optional

from loguru import logger

from rpi_usb_cloner.storage.device_lock import device_operation
from rpi_usb_cloner.storage.devices import (
    format_device_label,
    run_command,
    unmount_device,
)




def configure_format_helpers(
    log_debug: Optional[Callable[[str], None]] = None,
) -> None:
    """Configure format helpers (kept for backwards compatibility).

    Note: log_debug parameter is ignored - logging now uses loguru.
    """
    return


def _get_partition_path(device_path: str) -> str:
    """Get partition path for device (handles nvme/mmc suffix)."""
    device_name = device_path.replace("/dev/", "")
    partition_suffix = "p" if device_name[-1].isdigit() else ""
    return f"/dev/{device_name}{partition_suffix}1"


def _get_live_partition_mountpoint(partition_path: str) -> Optional[str]:
    """Return live mountpoint for a partition if currently mounted."""
    try:
        with open("/proc/mounts", encoding="utf-8") as mounts_file:
            for line in mounts_file:
                parts = line.split()
                if len(parts) > 1 and parts[0] == partition_path:
                    return parts[1]
    except FileNotFoundError:
        return None
    return None


def _ensure_partition_unmounted(partition_path: str) -> bool:
    """Ensure the partition is unmounted."""
    live_mountpoint = _get_live_partition_mountpoint(partition_path)
    if live_mountpoint:
        logger.warning(f"Partition still mounted at {live_mountpoint}")
        return False
    return True


def _unmount_partition_aggressive(partition_path: str) -> bool:
    """Attempt to unmount partition with aggressive options."""
    try:
        run_command(["umount", "-f", partition_path], check=False, log_command=False)
        return True
    except Exception as error:
        logger.debug(f"Aggressive unmount failed for {partition_path}: {error}")
        return False


def _validate_device_path(device_path: str) -> bool:
    """Validate that device path starts with /dev/."""
    return device_path.startswith("/dev/")


def _create_partition_table(device_path: str) -> bool:
    """Create MBR partition table on device.

    Args:
        device_path: Device path (e.g., /dev/sda)

    Returns:
        True on success, False on failure
    """
    try:
        logger.debug(f"Creating MBR partition table on {device_path}")
        result = run_command(
            ["parted", "-s", device_path, "mklabel", "msdos"],
            check=False,
            log_command=False,
        )
        if result.returncode != 0:
            logger.error(f"parted failed: {result.stderr}")
            return False
        return True
    except subprocess.CalledProcessError as error:
        logger.error(f"parted failed: {error}")
        return False


def _wait_for_partition_device(
    partition_path: str,
    timeout_seconds: float = 10.0,
    poll_interval: float = 0.25,
) -> bool:
    """Wait for partition device node to appear."""
    logger.debug(f"Waiting for partition device {partition_path} to appear")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if os.path.exists(partition_path):  # noqa: PTH110
            return True
        time.sleep(poll_interval)
    logger.error(f"Partition device did not appear: {partition_path}")
    return False


def _create_partition(device_path: str) -> bool:
    """Create single primary partition using full device.

    Args:
        device_path: Device path (e.g., /dev/sda)

    Returns:
        True on success, False on failure
    """
    try:
        logger.debug(f"Creating primary partition on {device_path}")
        # Create partition from 1MiB to 100% (proper alignment)
        run_command(["parted", "-s", device_path, "mkpart", "primary", "1MiB", "100%"])
        partition_path = _get_partition_path(device_path)
        if shutil.which("sync"):
            run_command(["sync"], check=False, log_command=False)
        return _wait_for_partition_device(partition_path)
    except subprocess.CalledProcessError as error:
        logger.error(f"Failed to create partition: {error}")
        return False


def _format_filesystem(
    partition_path: str,
    filesystem: str,
    mode: str,
    label: Optional[str],
    progress_callback: Optional[Callable[[List[str], Optional[float]], None]],
) -> bool:
    """Format partition with chosen filesystem.

    Args:
        partition_path: Partition path (e.g., /dev/sda1)
        filesystem: Filesystem type (ext4, vfat, exfat, ntfs)
        mode: Format mode (quick or full)
        label: Optional volume label
        progress_callback: Optional callback for progress updates

    Returns:
        True on success, False on failure
    """
    filesystem = filesystem.lower()
    mode = mode.lower()

    if not _ensure_partition_unmounted(partition_path):
        logger.warning(f"Format aborted: {partition_path} is still mounted")
        return False

    # Build format command based on filesystem type
    command: List[str] = []

    if filesystem == "ext4":
        command = ["mkfs.ext4", "-F"]
        if mode == "full":
            command.append("-c")  # Check for bad blocks
        if label:
            command.extend(["-L", label])
        command.append(partition_path)

    elif filesystem == "vfat":
        command = ["mkfs.vfat", "-F", "32"]
        if label:
            command.extend(["-n", label])
        command.append(partition_path)

    elif filesystem == "exfat":
        command = ["mkfs.exfat"]
        if label:
            command.extend(["-n", label])
        command.append(partition_path)

    elif filesystem == "ntfs":
        command = ["mkfs.ntfs", "-f"]
        if mode == "full":
            command.remove("-f")  # Remove fast format flag
        if label:
            command.extend(["-L", label])
        command.append(partition_path)

    else:
        logger.error(f"Unsupported filesystem type: {filesystem}")
        return False

    try:
        logger.info(f"Formatting {partition_path} as {filesystem} (mode: {mode})")

        # Update progress
        if progress_callback:
            progress_callback([f"Formatting {filesystem}..."], 0.5)

        # Run format command
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stderr_stream = process.stderr
        if stderr_stream is None:
            logger.error("Format failed: missing stderr stream")
            return False

        # Monitor progress for ext4 (shows percentage)
        if filesystem == "ext4":
            pattern = re.compile(r"(\d+)%")
            while True:
                if process.poll() is not None:
                    break

                # Check for output
                readable, _, _ = select.select([stderr_stream], [], [], 0.1)
                if readable:
                    line = stderr_stream.readline()
                    if line:
                        logger.debug(f"mkfs output: {line.strip()}")
                        match = pattern.search(line)
                        if match and progress_callback:
                            percent = int(match.group(1))
                            progress_callback(
                                [f"Formatting {filesystem}...", f"{percent}%"],
                                percent / 100.0,
                            )
                time.sleep(0.1)

        # Wait for completion
        returncode = process.wait()

        if returncode != 0:
            stderr = stderr_stream.read()
            logger.error(f"Format failed: {stderr}")
            return False

        logger.info(f"Successfully formatted {partition_path} as {filesystem}")

        # Update progress to complete
        if progress_callback:
            progress_callback(["Format complete"], 1.0)

        return True

    except subprocess.CalledProcessError as error:
        logger.error(f"Failed to format partition: {error}")
        return False
    except Exception as error:
        logger.error(f"Unexpected error during format: {error}")
        return False


def format_device(
    device: dict,
    filesystem: str,
    mode: str,
    label: Optional[str] = None,
    progress_callback: Optional[Callable[[List[str], Optional[float]], None]] = None,
) -> bool:
    """Format a USB drive with chosen filesystem.

    Creates MBR partition table, single primary partition, and formats with
    chosen filesystem type.

    Args:
        device: Device dict from lsblk with 'name' field
        filesystem: Filesystem type (ext4, vfat, exfat, ntfs)
        mode: Format mode (quick or full)
        label: Optional volume label
        progress_callback: Optional callback(lines, progress_ratio)

    Returns:
        True on success, False on failure
    """
    device_name = device.get("name")
    if not device_name:
        logger.warning("Format aborted: device has no name field")
        return False

    device_path = f"/dev/{device_name}"
    partition_path = _get_partition_path(device_path)

    # Validate device path
    if not _validate_device_path(device_path):
        logger.warning(f"Format aborted: invalid device path {device_path}")
        return False

    device_label = format_device_label(device)
    logger.info(f"Starting format of {device_label} as {filesystem} ({mode})")

    # Use device operation lock to pause web UI scanning
    with device_operation(device_name):
        # Unmount device and all partitions
        try:
            if progress_callback:
                progress_callback(["Unmounting..."], 0.0)
            unmounted = unmount_device(device)
            if not unmounted:
                logger.error(f"Failed to unmount device: {device_label}")
                return False
            # Give the system a moment to release the device
            time.sleep(1)
        except Exception as error:
            logger.error(f"Failed to unmount device: {error}")
            return False

        # Create partition table
        if progress_callback:
            progress_callback(["Creating partition table..."], 0.1)

        if not _create_partition_table(device_path):
            logger.warning(
                f"Format aborted: failed to create partition table on {device_label}"
            )
            return False

        # Create partition
        if progress_callback:
            progress_callback(["Creating partition..."], 0.3)

        if not _create_partition(device_path):
            logger.warning(f"Format aborted: failed to create partition on {device_label}")
            return False

        if not os.path.exists(partition_path):  # noqa: PTH110
            logger.warning(f"Format aborted: partition node missing for {device_label}")
            return False

        # Format filesystem
        if not _format_filesystem(
            partition_path, filesystem, mode, label, progress_callback
        ):
            logger.warning(f"Format aborted: filesystem format failed on {device_label}")
            return False

        logger.info(f"Format completed successfully for {device_label}")
        return True
