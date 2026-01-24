"""Device erasure operations."""

import shutil

import rpi_usb_cloner.ui.display as display
from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.storage.devices import (
    format_device_label,
    get_device_by_name,
    unmount_device,
)
from rpi_usb_cloner.storage.exceptions import (
    DeviceBusyError,
    MountVerificationError,
)
from rpi_usb_cloner.storage.validation import (
    validate_device_unmounted,
    validate_erase_operation,
)

from .command_runners import run_checked_with_streaming_progress
from .progress import _log_debug


def display_lines(lines):
    return display.display_lines(lines)


def erase_device(target, mode, progress_callback=None):
    """Erase a device using the specified mode.

    Modes:
        quick: Fast erase (wipefs + zero start/end of disk)
        zero: Full zero fill
        secure: Secure erase with shred
        discard: TRIM/discard (for SSDs)

    Args:
        target: Target device dict
        mode: Erase mode string
        progress_callback: Optional callback for progress updates

    Returns:
        True if successful, False otherwise
    """
    # SAFETY: Validate erase operation before proceeding
    try:
        validate_erase_operation(target, check_unmounted=False)
    except (DeviceBusyError, MountVerificationError) as error:
        if progress_callback:
            progress_callback(["ERROR", "Device busy"], None)
        else:
            display_lines(["ERROR", "Device busy"])
        _log_debug(f"Erase aborted: {error}")
        return False
    except Exception as error:
        if progress_callback:
            progress_callback(["ERROR", "Validation"], None)
        else:
            display_lines(["ERROR", "Validation"])
        _log_debug(f"Erase aborted: validation failed: {error}")
        return False

    target_node = f"/dev/{target.get('name')}"
    if not unmount_device(target):
        if progress_callback:
            progress_callback(["ERROR", "Unmount failed"], None)
        else:
            display_lines(["ERROR", "Unmount failed"])
        _log_debug("Erase aborted: target unmount failed")
        return False
    try:
        refreshed_target = get_device_by_name(target.get("name")) or target
        validate_device_unmounted(refreshed_target)
    except (DeviceBusyError, MountVerificationError) as error:
        if progress_callback:
            progress_callback(["ERROR", "Device busy"], None)
        else:
            display_lines(["ERROR", "Device busy"])
        _log_debug(f"Erase aborted: {error}")
        return False
    except Exception as error:
        if progress_callback:
            progress_callback(["ERROR", "Validation"], None)
        else:
            display_lines(["ERROR", "Validation"])
        _log_debug(f"Erase aborted: validation failed: {error}")
        return False
    mode = (mode or "").lower()
    device_label = format_device_label(target)
    mode_label = mode.upper() if mode else None

    # Build subtitle for progress display
    subtitle_parts = []
    if device_label:
        subtitle_parts.append(device_label)
    if mode_label:
        subtitle_parts.append(f"Mode {mode_label}")
    subtitle = " - ".join(subtitle_parts) if subtitle_parts else None

    def emit_error(message):
        if progress_callback:
            progress_callback(["ERROR", message], None)
        else:
            display_lines(["ERROR", message])

    def run_erase_command(command, total_bytes=None):
        try:
            run_checked_with_streaming_progress(
                command,
                total_bytes=total_bytes,
                title="ERASING",
                progress_callback=progress_callback,
                subtitle=subtitle,
            )
            return True
        except Exception as e:
            _log_debug(f"Erase command failed: {e}")
            return False

    if mode == "secure":
        shred_path = shutil.which("shred")
        if not shred_path:
            emit_error("no shred tool")
            _log_debug("Erase failed: shred not available")
            return False
        return run_erase_command(
            [shred_path, "-v", "-n", "1", "-z", target_node],
            total_bytes=target.get("size"),
        )

    if mode == "discard":
        discard_path = shutil.which("blkdiscard")
        if not discard_path:
            emit_error("no discard")
            _log_debug("Erase failed: blkdiscard not available")
            return False
        return run_erase_command([discard_path, target_node])

    if mode == "zero":
        dd_path = shutil.which("dd")
        if not dd_path:
            emit_error("no dd tool")
            _log_debug("Erase failed: dd not available")
            return False
        return run_erase_command(
            [
                dd_path,
                "if=/dev/zero",
                f"of={target_node}",
                "bs=4M",
                "status=progress",
                "conv=fsync",
            ],
            total_bytes=target.get("size"),
        )

    if mode != "quick":
        emit_error("unknown mode")
        _log_debug(f"Erase failed: unknown mode {mode}")
        return False

    # Quick mode: wipefs + zero start and end
    wipefs_path = shutil.which("wipefs")
    if not wipefs_path:
        emit_error("no wipefs")
        _log_debug("Erase failed: wipefs not available")
        return False
    dd_path = shutil.which("dd")
    if not dd_path:
        emit_error("no dd tool")
        _log_debug("Erase failed: dd not available")
        return False

    if not run_erase_command([wipefs_path, "-a", target_node]):
        return False

    def coerce_int(value, default=0):
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            return default
        return coerced if isinstance(coerced, int) else default

    size_bytes = coerce_int(target.get("size"))
    bytes_per_mib = 1024 * 1024
    size_mib = coerce_int(size_bytes // bytes_per_mib if size_bytes else 0)
    quick_wipe_mib = coerce_int(app_state.QUICK_WIPE_MIB)
    wipe_mib = coerce_int(min(quick_wipe_mib, size_mib) if size_mib else quick_wipe_mib)
    wipe_bytes = wipe_mib * bytes_per_mib

    if not run_erase_command(
        [
            dd_path,
            "if=/dev/zero",
            f"of={target_node}",
            "bs=1M",
            f"count={wipe_mib}",
            "status=progress",
            "conv=fsync",
        ],
        total_bytes=wipe_bytes,
    ):
        return False

    if size_mib > wipe_mib:
        seek_mib = size_mib - wipe_mib
        return run_erase_command(
            [
                dd_path,
                "if=/dev/zero",
                f"of={target_node}",
                "bs=1M",
                f"count={wipe_mib}",
                f"seek={seek_mib}",
                "status=progress",
                "conv=fsync",
            ],
            total_bytes=wipe_bytes,
        )

    return True
