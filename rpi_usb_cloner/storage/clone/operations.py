"""Core cloning operations."""

import os
import shutil
from typing import Any, Optional, Union

from rpi_usb_cloner.domain import CloneJob, CloneMode, Drive
from rpi_usb_cloner.storage.devices import (
    format_device_label,
    get_children,
    get_device_by_name,
    human_size,
    unmount_device,
)
from rpi_usb_cloner.storage.exceptions import (
    CloneOperationError,
    DeviceBusyError,
    InsufficientSpaceError,
    MountVerificationError,
    SourceDestinationSameError,
)
from rpi_usb_cloner.storage.validation import (
    validate_clone_operation,
    validate_device_unmounted,
)
from rpi_usb_cloner.ui.display import display_lines

from .command_runners import run_checked_command, run_checked_with_streaming_progress
from .models import (
    format_filesystem_type,
    get_partition_display_name,
    get_partition_number,
    normalize_clone_mode,
    resolve_device_node,
)
from .progress import _log_debug


def copy_partition_table(
    src: Union[str, dict[str, Any]], dst: Union[str, dict[str, Any]]
) -> None:
    """Copy partition table from source to destination device."""
    src_node = resolve_device_node(src)
    dst_node = resolve_device_node(dst)
    sfdisk_path = shutil.which("sfdisk")
    if not sfdisk_path:
        raise RuntimeError("sfdisk not found")
    dump_output = run_checked_command([sfdisk_path, "--dump", src_node])
    label = None
    for line in dump_output.splitlines():
        if line.startswith("label:"):
            label = line.split(":", 1)[1].strip().lower()
            break
    if not label:
        raise RuntimeError("Unable to detect partition table label")
    if label == "gpt":
        sgdisk_path = shutil.which("sgdisk")
        if not sgdisk_path:
            raise RuntimeError("sgdisk not found for GPT replicate")
        run_checked_command(
            [sgdisk_path, f"--replicate={dst_node}", "--randomize-guids", src_node]
        )
        _log_debug(f"GPT partition table replicated from {src_node} to {dst_node}")
        return
    if label in ("dos", "mbr", "msdos"):
        run_checked_command([sfdisk_path, dst_node], input_text=dump_output)
        _log_debug(f"MBR partition table cloned from {src_node} to {dst_node}")
        return
    raise RuntimeError(f"Unsupported partition table label: {label}")


def clone_dd(
    src: Union[str, dict[str, Any]],
    dst: Union[str, dict[str, Any]],
    total_bytes: Optional[int] = None,
    title: str = "CLONING",
    subtitle: Optional[str] = None,
) -> None:
    """Clone a device using dd (raw block-level copy)."""
    dd_path = shutil.which("dd")
    if not dd_path:
        raise RuntimeError("dd not found")
    src_node = resolve_device_node(src)
    dst_node = resolve_device_node(dst)
    run_checked_with_streaming_progress(
        [
            dd_path,
            f"if={src_node}",
            f"of={dst_node}",
            "bs=4M",
            "status=progress",
            "conv=fsync",
        ],
        total_bytes=total_bytes,
        title=title,
        subtitle=subtitle,
    )


def clone_partclone(
    source: Union[str, dict[str, Any]], target: Union[str, dict[str, Any]]
) -> None:
    """Clone a device using partclone (filesystem-aware cloning)."""
    partclone_tools = {
        "ext2": "partclone.ext2",
        "ext3": "partclone.ext3",
        "ext4": "partclone.ext4",
        "vfat": "partclone.fat",
        "fat16": "partclone.fat",
        "fat32": "partclone.fat",
        "ntfs": "partclone.ntfs",
        "exfat": "partclone.exfat",
        "xfs": "partclone.xfs",
        "btrfs": "partclone.btrfs",
    }
    source_node = resolve_device_node(source)
    target_node = resolve_device_node(target)
    source_name = os.path.basename(source_node)
    target_name = os.path.basename(target_node)
    source_device = get_device_by_name(source_name) or (
        source if isinstance(source, dict) else None
    )
    target_device = get_device_by_name(target_name) or (
        target if isinstance(target, dict) else None
    )
    if not source_device or not target_device:
        clone_dd(
            source_node,
            target_node,
            total_bytes=source.get("size") if isinstance(source, dict) else None,
        )
        return
    source_parts = [
        child for child in get_children(source_device) if child.get("type") == "part"
    ]
    if not source_parts:
        clone_dd(source_node, target_node, total_bytes=source_device.get("size"))
        return
    target_parts = [
        child for child in get_children(target_device) if child.get("type") == "part"
    ]
    target_parts_by_number = {}
    for child in target_parts:
        part_number = get_partition_number(child.get("name"))
        if part_number is None:
            continue
        target_parts_by_number.setdefault(part_number, child)
    for index, part in enumerate(source_parts, start=1):
        src_part = f"/dev/{part.get('name')}"
        part_number = get_partition_number(part.get("name"))
        dst_part = None
        if part_number is not None:
            target_part = target_parts_by_number.get(part_number)
            if target_part:
                dst_part = f"/dev/{target_part.get('name')}"
        if not dst_part and index - 1 < len(target_parts):
            dst_part = f"/dev/{target_parts[index - 1].get('name')}"
        if not dst_part:
            raise RuntimeError(f"Unable to map {src_part} to target partition")
        fstype = (part.get("fstype") or "").lower()
        tool = partclone_tools.get(fstype)
        tool_path = shutil.which(tool) if tool else None

        # Get friendly partition information for display
        part_name = get_partition_display_name(part)
        part_size_str = human_size(part.get("size")) if part.get("size") else ""
        fs_friendly = format_filesystem_type(fstype)

        # Build title line: "partition_name (1/4)"
        title_line = f"{part_name} ({index}/{len(source_parts)})"

        # Build info line: "8.2GB ext4" or "512MB FAT32"
        info_parts = []
        if part_size_str:
            info_parts.append(part_size_str)
        if fs_friendly:
            info_parts.append(fs_friendly)
        info_line = " ".join(info_parts) if info_parts else ""

        if not tool_path:
            # Use raw copy when no partclone tool available
            clone_dd(
                src_part,
                dst_part,
                total_bytes=part.get("size"),
                title=title_line,
                subtitle=info_line,
            )
            continue

        display_lines([title_line, info_line])
        with open(dst_part, "wb") as dst_handle:
            run_checked_with_streaming_progress(
                [tool_path, "-s", src_part, "-o", "-", "-F"],
                total_bytes=part.get("size"),
                title=title_line,
                subtitle=info_line,
                stdout_target=dst_handle,
            )


def clone_device(
    source: Union[str, dict[str, Any]],
    target: Union[str, dict[str, Any]],
    mode: Optional[str] = None,
) -> bool:
    """Clone a device using the specified mode.

    Args:
        source: Source device dict or path
        target: Target device dict or path
        mode: Clone mode ("smart", "exact", "verify")

    Returns:
        True if successful, False otherwise
    """
    # SAFETY: Validate clone operation before proceeding
    try:
        # For exact mode, we don't check space since we're doing raw copy
        check_space = (
            mode not in ("exact", None) or os.environ.get("CLONE_MODE") != "exact"
        )
        validate_clone_operation(
            source,
            target,
            check_space=check_space,
            check_unmounted=False,
        )
    except SourceDestinationSameError as error:
        display_lines(["FAILED", "Same device!"])
        _log_debug(f"Clone aborted: {error}")
        return False
    except InsufficientSpaceError as error:
        display_lines(["FAILED", "No space"])
        _log_debug(f"Clone aborted: {error}")
        return False
    except (DeviceBusyError, MountVerificationError) as error:
        display_lines(["FAILED", "Device busy"])
        _log_debug(f"Clone aborted: {error}")
        return False
    except Exception as error:
        display_lines(["FAILED", "Validation"])
        _log_debug(f"Clone aborted: validation failed: {error}")
        return False

    if mode is None:
        mode = os.environ.get("CLONE_MODE", "smart")
    mode = normalize_clone_mode(mode)
    if mode in ("smart", "verify"):
        success = clone_device_smart(source, target)
        if not success:
            return False
        if mode == "verify":
            from .verification import verify_clone

            return verify_clone(source, target)
        return True
    if not unmount_device(target):
        display_lines(["FAILED", "Unmount target"])
        _log_debug("Clone aborted: target unmount failed")
        return False
    try:
        validate_device_unmounted(target)
    except (DeviceBusyError, MountVerificationError) as error:
        display_lines(["FAILED", "Device busy"])
        _log_debug(f"Clone aborted: target still mounted: {error}")
        return False
    try:
        clone_dd(source, target, total_bytes=source.get("size"), title="CLONING")
    except RuntimeError as error:
        display_lines(["FAILED", str(error)[:20]])
        _log_debug(f"Clone failed: {error}")
        return False
    return True


def clone_device_smart(
    source: Union[str, dict[str, Any]], target: Union[str, dict[str, Any]]
) -> bool:
    """Clone a device using smart mode (partition-aware).

    Args:
        source: Source device dict
        target: Target device dict

    Returns:
        True if successful, False otherwise
    """
    # SAFETY: Validate clone operation before proceeding
    try:
        validate_clone_operation(
            source,
            target,
            check_space=True,
            check_unmounted=False,
        )
    except SourceDestinationSameError as error:
        display_lines(["FAILED", "Same device!"])
        _log_debug(f"Smart clone aborted: {error}")
        return False
    except InsufficientSpaceError as error:
        display_lines(["FAILED", "No space"])
        _log_debug(f"Smart clone aborted: {error}")
        return False
    except (DeviceBusyError, MountVerificationError) as error:
        display_lines(["FAILED", "Device busy"])
        _log_debug(f"Smart clone aborted: {error}")
        return False
    except Exception as error:
        display_lines(["FAILED", "Validation"])
        _log_debug(f"Smart clone aborted: validation failed: {error}")
        return False

    source_node = f"/dev/{source.get('name')}"
    target_node = f"/dev/{target.get('name')}"
    if not unmount_device(target):
        display_lines(["FAILED", "Unmount target"])
        _log_debug("Smart clone aborted: target unmount failed")
        return False
    try:
        validate_device_unmounted(target)
    except (DeviceBusyError, MountVerificationError) as error:
        display_lines(["FAILED", "Device busy"])
        _log_debug(f"Smart clone aborted: target still mounted: {error}")
        return False
    try:
        display_lines(["CLONING", "Copy table"])
        copy_partition_table(source, target)
    except RuntimeError as error:
        display_lines(["FAILED", "Partition tbl"])
        _log_debug(f"Partition table copy failed: {error}")
        return False
    try:
        clone_partclone(source, target)
    except RuntimeError as error:
        display_lines(["FAILED", str(error)[:20]])
        _log_debug(f"Smart clone failed ({source_node} -> {target_node}): {error}")
        return False
    display_lines(["CLONING", "Complete"])
    _log_debug(f"Smart clone completed from {source_node} to {target_node}")
    return True


def clone_device_v2(job: CloneJob) -> bool:
    """Clone a device using type-safe CloneJob (RECOMMENDED for new code).

    This function provides a type-safe API for cloning operations with
    built-in validation. It wraps the existing clone_device() implementation
    while adding CloneJob validation.

    Args:
        job: CloneJob containing source, destination, mode, and job_id

    Returns:
        True if successful, False otherwise

    Raises:
        ValueError: If CloneJob.validate() fails (e.g., source==destination,
                    destination too small, destination not removable)

    Example:
        >>> from rpi_usb_cloner.domain import CloneJob, CloneMode, Drive
        >>> source = Drive.from_lsblk_dict(source_dict)
        >>> destination = Drive.from_lsblk_dict(dest_dict)
        >>> job = CloneJob(source, destination, CloneMode.SMART, "clone-123")
        >>> job.validate()  # Raises ValueError if invalid
        >>> success = clone_device_v2(job)
    """
    # CRITICAL: Validate job constraints (source != destination, size, etc.)
    try:
        job.validate()
    except ValueError as error:
        # Map domain validation error to storage layer display
        error_msg = str(error)
        if "same device" in error_msg.lower():
            display_lines(["FAILED", "Same device!"])
        elif "smaller than source" in error_msg.lower():
            display_lines(["FAILED", "No space"])
        elif "not removable" in error_msg.lower():
            display_lines(["FAILED", "Not removable"])
        else:
            display_lines(["FAILED", "Validation"])
        _log_debug(f"Clone aborted: {error}")
        return False

    # Convert Drive objects to device paths (for backward compat with old API)
    # Note: clone_device still uses dicts, but we pass device paths which it accepts
    source_path = job.source.device_path
    destination_path = job.destination.device_path
    mode = job.mode.value

    # Get device dicts for the existing API (it expects dicts)
    source_dict = get_device_by_name(job.source.name)
    dest_dict = get_device_by_name(job.destination.name)

    if not source_dict or not dest_dict:
        display_lines(["FAILED", "Device lookup"])
        _log_debug(f"Clone aborted: Could not find source or destination device")
        return False

    # Call existing implementation
    return clone_device(source_dict, dest_dict, mode=mode)
