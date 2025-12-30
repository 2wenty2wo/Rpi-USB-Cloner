import shutil

from commands import display_lines, log_debug, run_progress_command
from devices import format_device_label, unmount_device

QUICK_WIPE_MIB = 32


def erase_device(target, mode):
    target_node = f"/dev/{target.get('name')}"
    unmount_device(target)
    mode = (mode or "").lower()
    device_label = format_device_label(target)
    mode_label = mode.upper() if mode else None
    if mode == "secure":
        shred_path = shutil.which("shred")
        if not shred_path:
            display_lines(["ERROR", "no shred tool"])
            log_debug("Erase failed: shred not available")
            return False
        return run_progress_command(
            [shred_path, "-v", "-n", "1", "-z", target_node],
            total_bytes=target.get("size"),
            title="ERASING",
            device_label=device_label,
            mode_label=mode_label,
        )
    if mode == "discard":
        discard_path = shutil.which("blkdiscard")
        if not discard_path:
            display_lines(["ERROR", "no discard"])
            log_debug("Erase failed: blkdiscard not available")
            return False
        return run_progress_command(
            [discard_path, target_node],
            title="ERASING",
            device_label=device_label,
            mode_label=mode_label,
        )
    if mode == "zero":
        dd_path = shutil.which("dd")
        if not dd_path:
            display_lines(["ERROR", "no dd tool"])
            log_debug("Erase failed: dd not available")
            return False
        return run_progress_command(
            [dd_path, "if=/dev/zero", f"of={target_node}", "bs=4M", "status=progress", "conv=fsync"],
            total_bytes=target.get("size"),
            title="ERASING",
            device_label=device_label,
            mode_label=mode_label,
        )
    if mode != "quick":
        display_lines(["ERROR", "unknown mode"])
        log_debug(f"Erase failed: unknown mode {mode}")
        return False
    wipefs_path = shutil.which("wipefs")
    if not wipefs_path:
        display_lines(["ERROR", "no wipefs"])
        log_debug("Erase failed: wipefs not available")
        return False
    dd_path = shutil.which("dd")
    if not dd_path:
        display_lines(["ERROR", "no dd tool"])
        log_debug("Erase failed: dd not available")
        return False
    if not run_progress_command(
        [wipefs_path, "-a", target_node],
        title="ERASING",
        device_label=device_label,
        mode_label=mode_label,
    ):
        return False
    size_bytes = target.get("size") or 0
    bytes_per_mib = 1024 * 1024
    size_mib = size_bytes // bytes_per_mib if size_bytes else 0
    wipe_mib = min(QUICK_WIPE_MIB, size_mib) if size_mib else QUICK_WIPE_MIB
    wipe_bytes = wipe_mib * bytes_per_mib
    if not run_progress_command(
        [dd_path, "if=/dev/zero", f"of={target_node}", "bs=1M", f"count={wipe_mib}", "status=progress", "conv=fsync"],
        total_bytes=wipe_bytes,
        title="ERASING",
        device_label=device_label,
        mode_label=mode_label,
    ):
        return False
    if size_mib > wipe_mib:
        seek_mib = size_mib - wipe_mib
        return run_progress_command(
            [dd_path, "if=/dev/zero", f"of={target_node}", "bs=1M", f"count={wipe_mib}", f"seek={seek_mib}", "status=progress", "conv=fsync"],
            total_bytes=wipe_bytes,
            title="ERASING",
            device_label=device_label,
            mode_label=mode_label,
        )
    return True
