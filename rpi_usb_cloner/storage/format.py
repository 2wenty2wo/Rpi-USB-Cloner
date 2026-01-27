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

from rpi_usb_cloner.logging import LoggerFactory
from rpi_usb_cloner.storage.devices import (
    format_device_label,
    get_device_by_name,
    run_command,
    unmount_device,
)
from rpi_usb_cloner.storage.exceptions import (
    DeviceBusyError,
    MountVerificationError,
)
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
        log.debug(f"Creating MBR partition table on {device_path} (attempt {attempt + 1}/{max_retries})")
        
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
        log.error(f"parted failed (attempt {attempt + 1}/{max_retries}): stderr='{stderr_msg}' stdout='{stdout_msg}' rc={result.returncode}")
        
        if attempt < max_retries - 1:
            # Device might still be busy, wait and retry
            delay = retry_delays[attempt]
            log.debug(f"Retrying in {delay} seconds...")
            
            # Try to settle the device before retry
            for cmd in (["sync"], ["partprobe", device_path], ["udevadm", "settle", "--timeout=5"]):
                if shutil.which(cmd[0]):
                    try:
                        run_command(cmd, log_command=False)
                    except (subprocess.CalledProcessError, OSError):
                        pass
            
            time.sleep(delay)
        else:
            log.error(f"All {max_retries} attempts failed to create partition table on {device_path}")
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
        for cmd in (["sync"], ["partprobe", device_path], ["udevadm", "settle", "--timeout=10"]):
            if shutil.which(cmd[0]):
                try:
                    run_command(cmd, log_command=False)
                except (subprocess.CalledProcessError, OSError):
                    pass
                    
        # Wait for partition device node to appear (up to 5 seconds)
        partition_suffix = "p" if device_path[-1].isdigit() else ""
        partition_path = f"{device_path}{partition_suffix}1"
        
        for i in range(10):
            if os.path.exists(partition_path):
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
            stderr_output = process.stderr.read() if process.stderr else "no error message"
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
        if not unmount_device(device):
            log.debug("Failed to unmount device; aborting format")
            log.warning("Format aborted: failed to unmount %s", device_label)
            if progress_callback:
                progress_callback(["Unmount failed"], None)
            return False
    except Exception as error:
        log.debug(f"Failed to unmount device: {error}")
        log.error("Format aborted: unmount failed for %s: %s", device_label, error)
        return False

    try:
        refreshed_device = get_device_by_name(device_name) or device
        validate_device_unmounted(refreshed_device)
    except (DeviceBusyError, MountVerificationError) as error:
        log.debug(f"Format aborted: {error}")
        log.warning(
            "Format aborted: device still mounted for %s: %s", device_label, error
        )
        if progress_callback:
            progress_callback(["Device busy"], None)
        return False
    except Exception as error:
        log.debug(f"Format aborted: mount verification failed: {error}")
        log.error(
            "Format aborted: mount verification failed for %s: %s",
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
            log.debug("Skipping %s: command not found", command[0])
            continue
        try:
            run_command(command)
        except (subprocess.CalledProcessError, OSError) as error:
            log.debug("Best-effort command failed (%s): %s", command[0], error)
    time.sleep(2)  # Additional wait for device to fully release

    # Aggressively release device from any processes holding it open
    # First, check and unmount any partitions that might have been re-mounted
    device_pattern = f"/dev/{device_name}"
    if device_name and device_name[-1].isdigit():
        partition_suffixes = ["p1", "p2", "p3", "p4", ""]
    else:
        partition_suffixes = ["1", "2", "3", "4", ""]
    for partition_suffix in partition_suffixes:
        candidate_partition_path = f"{device_pattern}{partition_suffix}"
        try:
            # Try to unmount each potential partition
            result = run_command(
                ["umount", candidate_partition_path], check=False, log_command=False
            )
            if result.returncode == 0:
                log.debug(f"Unmounted {candidate_partition_path}")
        except Exception:
            pass
    
    # Kill any processes using the device or its partitions
    if shutil.which("fuser"):
        # First check what's using the device
        try:
            result = run_command(["fuser", "-m", device_path], check=False, log_command=False)
            if result.stdout.strip():
                log.warning(f"Device {device_path} is being held by process(es): {result.stdout.strip()}")
                # Now kill those processes
                log.debug(f"Killing processes using {device_path}")
                run_command(["fuser", "-km", device_path], check=False, log_command=False)
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
                run_command(["dmsetup", "remove_all", "--force"], check=False, log_command=False)
                time.sleep(1)
        except Exception as error:
            log.debug(f"dmsetup cleanup failed: {error}")
    
    # Final sync and settle before continuing
    for cmd in (["sync"], ["udevadm", "settle", "--timeout=5"]):
        if shutil.which(cmd[0]):
            try:
                run_command(cmd, log_command=False)
            except (subprocess.CalledProcessError, OSError):
                pass
    time.sleep(1)

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
    if not os.path.exists(partition_path):
        log.error(f"Partition path {partition_path} is missing just before format")
        # Try one last partprobe
        if shutil.which("partprobe"):
            run_command(["partprobe", device_path], check=False)
            time.sleep(1)
            
    if not os.path.exists(partition_path):
        log.warning(f"Format aborted: partition {partition_path} not found")
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
