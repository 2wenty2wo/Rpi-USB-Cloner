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

import contextlib
import os
import re
import select
import shutil
import subprocess
import time
from typing import Callable, List, Optional

from rpi_usb_cloner.logging import LoggerFactory
from rpi_usb_cloner.storage.devices import (
    format_device_label,
    get_device_by_name,
    run_command,
    unmount_device_with_retry,
)
from rpi_usb_cloner.storage.exceptions import (
    DeviceBusyError,
    MountVerificationError,
)
from rpi_usb_cloner.storage.mount import unmount_block_device
from rpi_usb_cloner.storage.validation import (
    validate_device_unmounted,
    validate_format_operation,
)


# Create logger for format operations
log = LoggerFactory.for_clone()


def configure_format_helpers(log_debug: Optional[Callable[[str], None]] = None) -> None:
    """Configure format helpers (kept for backwards compatibility).

    Note: log_debug parameter is ignored - logging now uses LoggerFactory.
    """


def unmount_device(
    device: dict, log_debug: Optional[Callable[[str], None]] = None
) -> tuple[bool, bool]:
    """Unmount device with retry (compatibility wrapper)."""
    return unmount_device_with_retry(device, log_debug=log_debug)


def _validate_device_path(device_path: str) -> bool:
    """Validate that device path starts with /dev/."""
    return device_path.startswith("/dev/")


def _create_partition_table(device_path: str) -> bool:
    """Create MBR partition table on device.

    Uses retry logic to handle intermittent device busy errors that can occur
    when the device hasn't fully settled after unmounting.

    Args:
        device_path: Device path (e.g., /dev/sda)

    Returns:
        True on success, False on failure
    """
    max_retries = 3
    retry_delays = [2, 4, 6]  # Increasing delays between retries

    for attempt in range(max_retries):
        log.debug(
            f"Creating MBR partition table on {device_path} (attempt {attempt + 1}/{max_retries})"
        )

        # Use check=False to capture stderr without raising exception immediately
        result = run_command(
            ["parted", "-s", device_path, "mklabel", "msdos"],
            check=False,
            log_command=False,  # We're logging it ourselves
        )

        if result.returncode == 0:
            log.debug("Partition table created successfully")
            return True

        # Log the actual error from parted
        stderr_msg = result.stderr.strip() if result.stderr else "no error message"
        stdout_msg = result.stdout.strip() if result.stdout else ""
        log.error(
            f"parted failed (attempt {attempt + 1}/{max_retries}): stderr='{stderr_msg}' stdout='{stdout_msg}' rc={result.returncode}"
        )

        if attempt < max_retries - 1:
            # Device might still be busy, wait and retry
            delay = retry_delays[attempt]
            log.debug(f"Retrying in {delay} seconds...")

            # Try to settle the device before retry
            for cmd in (
                ["sync"],
                ["partprobe", device_path],
                ["udevadm", "settle", "--timeout=5"],
            ):
                if shutil.which(cmd[0]):
                    with contextlib.suppress(subprocess.CalledProcessError, OSError):
                        run_command(cmd, log_command=False)

            time.sleep(delay)
        else:
            log.error(
                f"All {max_retries} attempts failed to create partition table on {device_path}"
            )
            return False

    return False


def _create_partition(device_path: str) -> bool:
    """Create single primary partition using full device.

    Args:
        device_path: Device path (e.g., /dev/sda)

    Returns:
        True on success, False on failure
    """
    try:
        log.debug(f"Creating primary partition on {device_path}")
        # Create partition from 1MiB to 100% (proper alignment)
        run_command(["parted", "-s", device_path, "mkpart", "primary", "1MiB", "100%"])

        # Aggressively notify kernel of partition changes
        for cmd in (
            ["sync"],
            ["partprobe", device_path],
            ["udevadm", "settle", "--timeout=10"],
        ):
            if shutil.which(cmd[0]):
                with contextlib.suppress(subprocess.CalledProcessError, OSError):
                    run_command(cmd, log_command=False)

        # Wait for partition device node to appear (up to 5 seconds)
        partition_suffix = "p" if device_path[-1].isdigit() else ""
        partition_path = f"{device_path}{partition_suffix}1"

        for _ in range(10):
            if os.path.exists(partition_path):  # noqa: PTH110
                log.debug(f"Partition node found: {partition_path}")
                return True
            time.sleep(0.5)

        log.error(f"Partition node {partition_path} did not appear after creation")
        return False
    except subprocess.CalledProcessError as error:
        log.debug(f"Failed to create partition: {error}")
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

    # Build format command based on filesystem type
    command = []

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
        log.debug(f"Unsupported filesystem type: {filesystem}")
        return False

    try:
        log.debug(f"Formatting {partition_path} as {filesystem} (mode: {mode})")

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

        # Monitor progress for ext4 (shows percentage)
        if filesystem == "ext4":
            pattern = re.compile(r"(\d+)%")
            while True:
                if process.poll() is not None:
                    break

                # Check for output
                stderr_stream = process.stderr
                if stderr_stream is None:
                    break
                readable, _, _ = select.select([stderr_stream], [], [], 0.1)
                if readable:
                    line = stderr_stream.readline()
                    if line:
                        log.debug(f"mkfs output: {line.strip()}")
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
            stderr_output = (
                process.stderr.read() if process.stderr else "no error message"
            )
            log.error(f"Format command failed with code {returncode}")
            log.error(f"Command: {' '.join(command)}")
            log.error(f"Error output: {stderr_output.strip()}")
            return False

        log.debug(f"Successfully formatted {partition_path} as {filesystem}")

        # Update progress to complete
        if progress_callback:
            progress_callback(["Format complete"], 1.0)

        return True

    except subprocess.CalledProcessError as error:
        log.debug(f"Failed to format partition: {error}")
        return False
    except Exception as error:
        log.debug(f"Unexpected error during format: {error}")
        return False


def _collect_mountpoints(device: dict) -> list[str]:
    mountpoints: list[str] = []
    for child in device.get("children", []) or []:
        mountpoint = child.get("mountpoint")
        if mountpoint:
            mountpoints.append(mountpoint)
    mountpoint = device.get("mountpoint")
    if mountpoint:
        mountpoints.append(mountpoint)
    return mountpoints


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
        log.debug("Device has no name field")
        log.warning("Format aborted: device has no name field")
        return False

    # SAFETY: Validate format operation before proceeding
    try:
        validate_format_operation(device, check_unmounted=False)
    except (DeviceBusyError, MountVerificationError) as error:
        log.debug(f"Format aborted: {error}")
        log.warning(f"Format aborted due to validation failure: {error}")
        if progress_callback:
            progress_callback(["Device busy"], None)
        return False
    except Exception as error:
        log.debug(f"Format aborted: validation failed: {error}")
        log.error(f"Format aborted: validation failed: {error}")
        if progress_callback:
            progress_callback(["Validation failed"], None)
        return False

    device_path = f"/dev/{device_name}"
    partition_suffix = "p" if device_name[-1].isdigit() else ""
    partition_path = f"/dev/{device_name}{partition_suffix}1"

    # Validate device path
    if not _validate_device_path(device_path):
        log.debug(f"Invalid device path: {device_path}")
        log.warning(f"Format aborted: invalid device path {device_path}")
        return False

    device_label = format_device_label(device)
    log.debug(f"Starting format of {device_label} as {filesystem} ({mode})")
    log.info(
        "Starting format of {} as {} ({})",
        device_label,
        filesystem,
        mode,
    )

    # Unmount device and all partitions
    try:
        if progress_callback:
            progress_callback(["Unmounting..."], 0.0)
        unmount_result = unmount_device(device, log_debug=log.debug)
        if isinstance(unmount_result, tuple):
            unmount_success, used_lazy_unmount = unmount_result
        else:
            unmount_success, used_lazy_unmount = bool(unmount_result), False
    except Exception as error:
        log.debug(f"Failed to unmount device: {error}")
        log.error("Format aborted: unmount failed for {}: {}", device_label, error)
        return False

    refreshed_device = get_device_by_name(device_name) or device

    if not unmount_success:
        mountpoints = _collect_mountpoints(refreshed_device)
        mountpoints_label = ", ".join(mountpoints) if mountpoints else "none"
        log.debug(
            "Failed to unmount {} (lazy used={}). Active mountpoints: {}",
            device_label,
            used_lazy_unmount,
            mountpoints_label,
        )
        log.warning(
            "Format aborted: device still mounted for {} (mountpoints: {})",
            device_label,
            mountpoints_label,
        )
        if progress_callback:
            progress_callback(["Device still mounted"], None)
        return False

    try:
        validate_device_unmounted(refreshed_device)
    except (DeviceBusyError, MountVerificationError) as error:
        log.debug(f"Format aborted: {error}")
        log.warning(
            "Format aborted: device still mounted for {}: {}", device_label, error
        )
        if progress_callback:
            progress_callback(["Device busy"], None)
        return False
    except Exception as error:
        log.debug(f"Format aborted: mount verification failed: {error}")
        log.error(
            "Format aborted: mount verification failed for {}: {}",
            device_label,
            error,
        )
        if progress_callback:
            progress_callback(["Validation failed"], None)
        return False

    # Allow device to settle after unmount (prevents intermittent parted failures)
    # Sync to flush any pending writes and udevadm settle to wait for udev processing
    for command in (["sync"], ["udevadm", "settle", "--timeout=5"]):
        if not shutil.which(command[0]):
            log.debug("Skipping {}: command not found", command[0])
            continue
        try:
            run_command(command)
        except (subprocess.CalledProcessError, OSError) as error:
            log.debug("Best-effort command failed ({}): {}", command[0], error)
    time.sleep(2)  # Additional wait for device to fully release

    # CRITICAL: Tell udisks2/automount to stop managing this device
    # This prevents the system from auto-remounting partitions during format
    if shutil.which("udisksctl"):
        try:
            log.debug(f"Telling udisks2 to unmount {device_path} and all partitions")
            # Unmount the base device (will fail if not mounted, which is fine)
            run_command(
                ["udisksctl", "unmount", "-b", device_path, "--no-user-interaction"],
                check=False,
                log_command=False,
            )
            # Unmount all potential partitions
            partition_suffix = "p" if device_name[-1].isdigit() else ""
            for i in range(1, 9):  # Check up to 8 partitions
                potential_partition = f"{device_path}{partition_suffix}{i}"
                run_command(
                    [
                        "udisksctl",
                        "unmount",
                        "-b",
                        potential_partition,
                        "--no-user-interaction",
                    ],
                    check=False,
                    log_command=False,
                )
            time.sleep(1)
        except Exception as error:
            log.debug(
                f"udisksctl unmount operations failed (continuing anyway): {error}"
            )

    # Aggressively release device from any processes holding it open
    # First, check and unmount any partitions that might have been re-mounted
    device_pattern = f"/dev/{device_name}"
    if device_name and device_name[-1].isdigit():
        partition_suffixes = ["p1", "p2", "p3", "p4", ""]
    else:
        partition_suffixes = ["1", "2", "3", "4", ""]
    for partition_suffix in partition_suffixes:
        candidate_partition_path = f"{device_pattern}{partition_suffix}"
        with contextlib.suppress(Exception):
            # Try to unmount each potential partition
            result = run_command(
                ["umount", candidate_partition_path], check=False, log_command=False
            )
            if result.returncode == 0:
                log.debug(f"Unmounted {candidate_partition_path}")

    # Kill any processes using the device or its partitions
    if shutil.which("fuser"):
        # First check what's using the device
        try:
            result = run_command(
                ["fuser", "-m", device_path], check=False, log_command=False
            )
            if result.stdout.strip():
                log.warning(
                    f"Device {device_path} is being held by process(es): {result.stdout.strip()}"
                )
                # Now kill those processes
                log.debug(f"Killing processes using {device_path}")
                run_command(
                    ["fuser", "-km", device_path], check=False, log_command=False
                )
                time.sleep(1)  # Give processes time to die
        except Exception as error:
            log.debug(f"fuser check/kill failed: {error}")

    # Try to remove any device-mapper mappings (can hold devices open)
    if shutil.which("dmsetup"):
        try:
            # Get list of dm devices
            result = run_command(["dmsetup", "ls"], check=False, log_command=False)
            if result.stdout.strip() and "No devices found" not in result.stdout:
                log.debug("Checking device-mapper for stale mappings")
                # Try to remove all dm devices (safe - only removes those we can)
                run_command(
                    ["dmsetup", "remove_all", "--force"], check=False, log_command=False
                )
        except Exception as error:
            log.debug(f"dmsetup cleanup failed: {error}")

    # Final sync and settle before continuing
    for cmd in (["sync"], ["udevadm", "settle", "--timeout=5"]):
        if shutil.which(cmd[0]):
            with contextlib.suppress(subprocess.CalledProcessError, OSError):
                run_command(cmd, log_command=False)
    time.sleep(1)

    # CRITICAL FIX: Delete all existing partitions to release kernel's hold
    # This is THE KEY - parted can't create a new table if old partitions are registered
    try:
        # IMPORTANT: Unmount again right before deletion since auto-mount may have re-mounted
        log.debug(f"Final unmount before partition deletion from {device_path}")

        # Use udisksctl to tell automount to leave us alone
        if shutil.which("udisksctl"):
            for i in range(1, 9):
                partition_suffix_local = "p" if device_name[-1].isdigit() else ""
                potential_partition = f"{device_path}{partition_suffix_local}{i}"
                run_command(
                    [
                        "udisksctl",
                        "unmount",
                        "-b",
                        potential_partition,
                        "--no-user-interaction",
                    ],
                    check=False,
                    log_command=False,
                )

        # Also use regular umount
        for i in range(1, 9):
            partition_suffix_local = "p" if device_name[-1].isdigit() else ""
            potential_partition = f"{device_path}{partition_suffix_local}{i}"
            run_command(["umount", potential_partition], check=False, log_command=False)

        time.sleep(1)

        log.debug(f"Deleting all existing partitions from {device_path}")
        # First, get the current partition table type and partition list
        result = run_command(
            ["parted", "-s", device_path, "print"], check=False, log_command=False
        )

        # Parse partition numbers and delete them in reverse order
        # Look for lines like " 1      1049kB  15.5GB  15.5GB  ext4"
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line and line[0].isdigit():
                    # Extract partition number (first field)
                    parts = line.split()
                    if parts:
                        partition_num = parts[0]
                        log.debug(
                            f"Deleting partition {partition_num} from {device_path}"
                        )
                        run_command(
                            ["parted", "-s", device_path, "rm", partition_num],
                            check=False,
                        )

            # Force kernel to re-read the (now empty) partition table
            for cmd in (
                ["partprobe", device_path],
                ["blockdev", "--rereadpt", device_path],
            ):
                if shutil.which(cmd[0]):
                    with contextlib.suppress(subprocess.CalledProcessError, OSError):
                        run_command(cmd, check=False, log_command=False)
            time.sleep(2)  # Give kernel time to process
    except Exception as error:
        log.debug(f"Partition deletion failed (continuing anyway): {error}")

    # Final safety gate: ensure device is still unmounted before wipefs/partitioning
    final_device = get_device_by_name(device_name) or refreshed_device or device
    final_check_error: Optional[Exception] = None
    last_mountpoints: list[str] = []
    for attempt in range(1, 4):
        final_device = (
            get_device_by_name(device_name, force_refresh=True)
            or refreshed_device
            or device
        )
        detected_mountpoints = (
            _collect_mountpoints(final_device) if final_device else []
        )
        if detected_mountpoints:
            last_mountpoints = detected_mountpoints
            log.debug(
                "Final unmount retry {}/3 for {} (mountpoints: {})",
                attempt,
                device_label,
                ", ".join(detected_mountpoints),
            )

            if shutil.which("udisksctl"):
                run_command(
                    [
                        "udisksctl",
                        "unmount",
                        "-b",
                        device_path,
                        "--no-user-interaction",
                    ],
                    check=False,
                    log_command=False,
                )
                for i in range(1, 9):
                    partition_suffix_local = "p" if device_name[-1].isdigit() else ""
                    potential_partition = f"{device_path}{partition_suffix_local}{i}"
                    run_command(
                        [
                            "udisksctl",
                            "unmount",
                            "-b",
                            potential_partition,
                            "--no-user-interaction",
                        ],
                        check=False,
                        log_command=False,
                    )

            run_command(["umount", device_path], check=False, log_command=False)
            for i in range(1, 9):
                partition_suffix_local = "p" if device_name[-1].isdigit() else ""
                potential_partition = f"{device_path}{partition_suffix_local}{i}"
                run_command(
                    ["umount", potential_partition], check=False, log_command=False
                )

        if shutil.which("udevadm"):
            run_command(
                ["udevadm", "settle", "--timeout=5"],
                check=False,
                log_command=False,
            )
        time.sleep(1)
        final_device = (
            get_device_by_name(device_name, force_refresh=True)
            or refreshed_device
            or device
        )
        refreshed_mountpoints = (
            _collect_mountpoints(final_device) if final_device else []
        )
        if refreshed_mountpoints:
            last_mountpoints = refreshed_mountpoints

        try:
            validate_device_unmounted(final_device)
            final_check_error = None
            break
        except (DeviceBusyError, MountVerificationError) as error:
            final_check_error = error
            if isinstance(error, MountVerificationError):
                last_mountpoints = [error.mountpoint]
            if attempt < 3:
                log.debug(
                    "Final mount verification retry {}/3 for {}: {}",
                    attempt,
                    device_label,
                    error,
                )
                continue
        except Exception as error:
            final_check_error = error
            if attempt < 3:
                log.debug(
                    "Final mount verification retry {}/3 for {}: {}",
                    attempt,
                    device_label,
                    error,
                )
                continue
        break

    if final_check_error:
        mountpoint_note = ""
        if last_mountpoints:
            mountpoint_note = f" (mountpoint: {', '.join(last_mountpoints)})"
        if isinstance(final_check_error, (DeviceBusyError, MountVerificationError)):
            log.warning(
                "Format aborted: device busy before wipefs for {}: {}{}",
                device_label,
                final_check_error,
                mountpoint_note,
            )
        else:
            log.error(
                "Format aborted: final mount verification failed for {}: {}{}",
                device_label,
                final_check_error,
                mountpoint_note,
            )
        if progress_callback:
            progress_callback(["Device busy", "Aborting format"], None)
        return False

    if shutil.which("fuser"):
        try:
            result = run_command(
                ["fuser", "-m", device_path], check=False, log_command=False
            )
            if result.returncode == 0:
                fuser_output = (result.stdout or "").strip()
                if fuser_output:
                    log.warning(
                        "Format aborted: device busy (holders: {}) for {}",
                        fuser_output,
                        device_label,
                    )
                    if progress_callback:
                        progress_callback(["Device busy", "Aborting format"], None)
                    return False
            else:
                log.debug(
                    "fuser check failed for {} (rc={}, stderr={})",
                    device_label,
                    result.returncode,
                    (result.stderr or "").strip(),
                )
        except Exception as error:
            log.debug(f"fuser check failed (continuing anyway): {error}")

    # Wipe filesystem signatures to prevent parted confusion
    # This is critical - old signatures can cause parted to fail
    if shutil.which("wipefs"):
        try:
            log.debug(f"Wiping filesystem signatures from {device_path}")
            run_command(["wipefs", "-a", device_path])
            time.sleep(1)  # Let kernel process the wipe
        except subprocess.CalledProcessError as error:
            # Don't fail on wipefs errors, but log them
            log.debug(f"wipefs failed (continuing anyway): {error}")

    # Create partition table
    if progress_callback:
        progress_callback(["Creating partition table..."], 0.1)

    if not _create_partition_table(device_path):
        log.warning(
            f"Format aborted: failed to create partition table on {device_label}"
        )
        return False

    # Create partition
    if progress_callback:
        progress_callback(["Creating partition..."], 0.3)

    if not _create_partition(device_path):
        log.warning(f"Format aborted: failed to create partition on {device_label}")
        return False

    # Wait an extra moment and verify partition exists again before formatting
    # Sometimes it flickers during creation
    time.sleep(1)
    if not os.path.exists(partition_path):  # noqa: PTH110
        log.error(f"Partition path {partition_path} is missing just before format")
        # Try one last partprobe
        if shutil.which("partprobe"):
            run_command(["partprobe", device_path], check=False)
            time.sleep(1)

    if not os.path.exists(partition_path):  # noqa: PTH110
        log.warning(f"Format aborted: partition {partition_path} not found")
        return False

    refreshed_device = get_device_by_name(device_name) or device
    post_partition_mountpoint = None
    partition_name = f"{device_name}{partition_suffix}1"
    for child in refreshed_device.get("children", []) or []:
        if child.get("name") == partition_name and child.get("mountpoint"):
            post_partition_mountpoint = child.get("mountpoint")
            break

    if post_partition_mountpoint:
        log.info(
            "Detected post-partition auto-mount for {} at {}; unmounting",
            partition_path,
            post_partition_mountpoint,
        )
        if progress_callback:
            progress_callback(
                ["Auto-mounted partition detected", "Unmounting..."], 0.45
            )
        unmount_success = False
        if shutil.which("udisksctl"):
            result = run_command(
                [
                    "udisksctl",
                    "unmount",
                    "-b",
                    partition_path,
                    "--no-user-interaction",
                ],
                check=False,
                log_command=False,
            )
            unmount_success = result.returncode == 0
        if not unmount_success:
            try:
                unmount_block_device(partition_path)
                unmount_success = True
            except (ValueError, RuntimeError) as error:
                log.debug("Fallback umount failed for {}: {}", partition_path, error)
        if not unmount_success:
            log.warning(
                "Format aborted: device busy after auto-mount on {}",
                device_label,
            )
            if progress_callback:
                progress_callback(["Device busy", "Aborting format"], None)
            return False
        time.sleep(1)
        refreshed_device = get_device_by_name(device_name) or refreshed_device

    try:
        validate_device_unmounted(refreshed_device)
    except (DeviceBusyError, MountVerificationError) as error:
        log.warning(
            "Format aborted: device busy after partitioning for {}: {}",
            device_label,
            error,
        )
        if progress_callback:
            progress_callback(["Device busy", "Aborting format"], None)
        return False
    except Exception as error:
        log.error(
            "Format aborted: mount verification failed after partitioning for {}: {}",
            device_label,
            error,
        )
        if progress_callback:
            progress_callback(["Device busy", "Aborting format"], None)
        return False

    # Format filesystem
    if not _format_filesystem(
        partition_path, filesystem, mode, label, progress_callback
    ):
        log.warning(
            f"Format aborted: filesystem format failed on {device_label} ({filesystem})"
        )
        return False

    log.debug(f"Format completed successfully: {device_label}")
    log.info("Format completed successfully for {}", device_label)
    return True
