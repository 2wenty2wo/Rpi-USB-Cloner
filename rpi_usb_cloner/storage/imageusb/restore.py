"""ImageUSB .BIN file restoration operations."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from rpi_usb_cloner.logging import get_logger
from rpi_usb_cloner.storage import devices
from rpi_usb_cloner.storage.clone.command_runners import (
    run_checked_with_streaming_progress,
)
from rpi_usb_cloner.storage.clone.models import resolve_device_node

from .detection import IMAGEUSB_HEADER_SIZE, validate_imageusb_file


log = get_logger(source=__name__)


def restore_imageusb_file(
    image_path: Path,
    target_device: str,
    *,
    progress_callback: Callable[[list[str], float | None], None] | None = None,
) -> None:
    """Restore an ImageUSB .BIN file to a target device.

    The ImageUSB .BIN format contains a 512-byte header followed by a raw disk image.
    This function uses dd to skip the header and write the disk image to the target.

    Args:
        image_path: Path to the ImageUSB .BIN file
        target_device: Target device node (e.g., "/dev/sda") or device name (e.g., "sda")
        progress_callback: Optional callback for progress updates (receives [title, subtitle], progress_fraction)

    Raises:
        RuntimeError: If restoration fails or validation fails
        PermissionError: If not running as root
    """
    # Validate permissions
    if os.geteuid() != 0:
        raise PermissionError("Must run as root to restore images")

    # Validate image file
    error = validate_imageusb_file(image_path)
    if error:
        raise RuntimeError(f"Invalid ImageUSB file: {error}")

    # Resolve target device node
    target_node = resolve_device_node(target_device)
    target_name = Path(target_node).name

    # Get device info
    target_info = devices.get_device_by_name(target_name)
    if not target_info:
        raise RuntimeError(f"Target device not found: {target_name}")

    # Safety check: must be removable
    rm_value = target_info.get("rm")
    try:
        rm_flag = int(rm_value)
    except (TypeError, ValueError):
        rm_flag = 0
    if rm_flag != 1:
        raise RuntimeError(
            f"Target device {target_name} is not removable - refusing to restore"
        )

    # Unmount all partitions on target device
    log.info("Unmounting target device: %s", target_name)
    if progress_callback:
        progress_callback(["Preparing device...", "Unmounting partitions"], None)

    if not devices.unmount_device(target_info, raise_on_failure=False):
        raise RuntimeError(f"Failed to unmount target device: {target_name}")

    # Get file size for progress calculation
    try:
        file_size = image_path.stat().st_size
        # Data size is file size minus header
        data_size = file_size - IMAGEUSB_HEADER_SIZE
    except OSError as e:
        raise RuntimeError(f"Cannot read file size: {e}") from e

    # Find dd command
    dd_path = shutil.which("dd")
    if not dd_path:
        raise RuntimeError("dd command not found")

    # Build dd command
    # Skip first 512 bytes (bs=512, skip=1)
    # Use 4MB block size for actual transfer (faster)
    # The input file has a 512-byte header, so we skip it with bs=512 skip=1
    # Then we switch to 4MB blocks for the actual data transfer
    command = [
        dd_path,
        f"if={image_path}",
        f"of={target_node}",
        "bs=512",  # Block size for skip operation
        "skip=1",  # Skip first block (512 bytes header)
        "status=progress",  # Show progress
        "conv=fsync",  # Sync writes to disk
    ]

    log.info("Restoring ImageUSB file: %s -> %s", image_path.name, target_node)
    log.debug("Command: %s", " ".join(command))

    # Execute restore with progress tracking
    title = f"Restoring {image_path.name}"
    subtitle = f"to {target_name}"

    try:
        if progress_callback:
            progress_callback([title, subtitle], 0.0)

        # Use the clone module's progress tracking
        run_checked_with_streaming_progress(
            command,
            title=title,
            total_bytes=data_size,  # Total bytes to write (excluding header)
            stdin_source=None,  # dd reads from if= parameter
            progress_callback=progress_callback,
            subtitle=subtitle,
        )

        log.info("ImageUSB restoration completed successfully")

        if progress_callback:
            progress_callback([title, "Complete"], 1.0)

    except subprocess.CalledProcessError as e:
        error_msg = f"dd command failed: {e.stderr if e.stderr else str(e)}"
        log.error(error_msg)
        raise RuntimeError(error_msg) from e
    except Exception as e:
        log.error("Restoration failed: %s", str(e))
        raise RuntimeError(f"Restoration failed: {e}") from e


def restore_imageusb_file_simple(
    image_path: Path,
    target_device: str,
) -> None:
    """Restore an ImageUSB .BIN file to a target device (simple API without progress).

    This is a simplified version without progress callbacks for backward compatibility
    or simple use cases.

    Args:
        image_path: Path to the ImageUSB .BIN file
        target_device: Target device node (e.g., "/dev/sda") or device name (e.g., "sda")

    Raises:
        RuntimeError: If restoration fails or validation fails
        PermissionError: If not running as root
    """
    restore_imageusb_file(image_path, target_device, progress_callback=None)
