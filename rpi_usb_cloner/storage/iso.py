"""ISO image writing functionality.

This module provides support for writing ISO files directly to USB devices.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Optional

from rpi_usb_cloner.storage import clone, devices
from rpi_usb_cloner.storage.clone import resolve_device_node


def restore_iso_image(
    iso_path: Path,
    target_device: str,
    *,
    progress_callback: Callable[[list[str], float | None], None] | None = None,
) -> None:
    """Write an ISO file directly to a device using dd.

    Args:
        iso_path: Path to the ISO file
        target_device: Target device name (e.g., "sda")
        progress_callback: Optional callback for progress updates
    """
    if os.geteuid() != 0:
        raise RuntimeError("Run as root")

    if not iso_path.is_file():
        raise RuntimeError(f"ISO file not found: {iso_path}")

    target_node = resolve_device_node(target_device)
    target_name = Path(target_node).name
    target_info = devices.get_device_by_name(target_name)

    if target_info and not devices.unmount_device(target_info):
        raise RuntimeError("Failed to unmount target device before ISO restore")

    # Get ISO size
    iso_size = iso_path.stat().st_size
    target_size = _get_device_size_bytes(target_info, target_node)

    if target_size and iso_size > target_size:
        raise RuntimeError(
            f"Target device too small ({devices.human_size(target_size)} < {devices.human_size(iso_size)})"
        )

    # Write ISO using dd
    dd_path = shutil.which("dd")
    if not dd_path:
        raise RuntimeError("dd not found")

    command = [
        dd_path,
        f"if={iso_path}",
        f"of={target_node}",
        "bs=4M",
        "status=progress",
        "conv=fsync",
    ]

    clone.run_checked_with_streaming_progress(
        command,
        title=f"Writing {iso_path.name}",
        total_bytes=iso_size,
        progress_callback=progress_callback,
    )


def _get_blockdev_size_bytes(device_node: str) -> int | None:
    """Get device size using blockdev command."""
    blockdev = shutil.which("blockdev")
    if not blockdev:
        return None
    import subprocess

    result = subprocess.run(
        [blockdev, "--getsize64", device_node],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _get_device_size_bytes(
    target_info: Optional[dict], target_node: str
) -> Optional[int]:
    """Get device size from device info or blockdev."""
    if target_info:
        size_value = target_info.get("size")
        if size_value is not None:
            return int(size_value)
    return _get_blockdev_size_bytes(target_node)
