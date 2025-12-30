import os
import re
import shutil
import subprocess
import time
from typing import Callable, Optional

from rpi_usb_cloner import config
from rpi_usb_cloner.services.progress import run_checked_with_progress, run_progress_command
from devices import format_device_label, get_children, get_device_by_name, human_size, unmount_device

_display_lines: Optional[Callable] = None


def configure(display_lines: Callable) -> None:
    global _display_lines
    _display_lines = display_lines


def _require_display() -> None:
    if _display_lines is None:
        raise RuntimeError("Cloning module not configured")


def normalize_clone_mode(mode):
    if not mode:
        return "smart"
    mode = mode.lower()
    if mode == "raw":
        return "exact"
    if mode in ("smart", "exact", "verify"):
        return mode
    return "smart"


def resolve_device_node(device):
    if isinstance(device, str):
        return device if device.startswith("/dev/") else f"/dev/{device}"
    return f"/dev/{device.get('name')}"


def run_checked_command(command, input_text=None):
    config.log_debug(f"Running command: {' '.join(command)}")
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        message = stderr or stdout or "Command failed"
        raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")
    return result.stdout


def copy_partition_table(src, dst):
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
        run_checked_command([sgdisk_path, f"--replicate={dst_node}", "--randomize-guids", src_node])
        config.log_debug(f"GPT partition table replicated from {src_node} to {dst_node}")
        return
    if label in ("dos", "mbr", "msdos"):
        run_checked_command([sfdisk_path, dst_node], input_text=dump_output)
        config.log_debug(f"MBR partition table cloned from {src_node} to {dst_node}")
        return
    raise RuntimeError(f"Unsupported partition table label: {label}")


def get_partition_number(name):
    if not name:
        return None
    match = re.search(r"(?:p)?(\d+)$", name)
    if not match:
        return None
    return int(match.group(1))


def clone_dd(src, dst, total_bytes=None, title="CLONING"):
    dd_path = shutil.which("dd")
    if not dd_path:
        raise RuntimeError("dd not found")
    src_node = resolve_device_node(src)
    dst_node = resolve_device_node(dst)
    run_checked_with_progress(
        [dd_path, f"if={src_node}", f"of={dst_node}", "bs=4M", "status=progress", "conv=fsync"],
        total_bytes=total_bytes,
        title=title,
    )


def clone_partclone(source, target):
    _require_display()
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
    source_device = get_device_by_name(source_name) or (source if isinstance(source, dict) else None)
    target_device = get_device_by_name(target_name) or (target if isinstance(target, dict) else None)
    if not source_device or not target_device:
        clone_dd(source_node, target_node, total_bytes=source.get("size") if isinstance(source, dict) else None)
        return
    source_parts = [child for child in get_children(source_device) if child.get("type") == "part"]
    if not source_parts:
        clone_dd(source_node, target_node, total_bytes=source_device.get("size"))
        return
    target_parts = [child for child in get_children(target_device) if child.get("type") == "part"]
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
        if not tool_path:
            clone_dd(src_part, dst_part, total_bytes=part.get("size"), title=f"DD {index}/{len(source_parts)}")
            continue
        _display_lines([f"PART {index}/{len(source_parts)}", tool])
        with open(dst_part, "wb") as dst_handle:
            run_checked_with_progress(
                [tool_path, "-s", src_part, "-o", "-", "-f"],
                total_bytes=part.get("size"),
                title=f"PART {index}/{len(source_parts)}",
                stdout_target=dst_handle,
            )


def compute_sha256(device_node, total_bytes=None, title="VERIFY"):
    _require_display()
    dd_path = shutil.which("dd")
    sha_path = shutil.which("sha256sum")
    if not dd_path or not sha_path:
        raise RuntimeError("dd or sha256sum not found")
    config.log_debug(f"Computing sha256 for {device_node}")
    _display_lines([title, "Starting..."])
    dd_cmd = [dd_path, f"if={device_node}", "bs=4M", "status=progress"]
    if total_bytes:
        total_bytes = int(total_bytes)
        dd_cmd.extend([f"count={total_bytes}", "iflag=count_bytes"])
    dd_proc = subprocess.Popen(
        dd_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    sha_proc = subprocess.Popen(
        [sha_path],
        stdin=dd_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if dd_proc.stdout:
        dd_proc.stdout.close()
    last_update = time.time()
    while True:
        line = dd_proc.stderr.readline()
        if line:
            config.log_debug(f"dd: {line.strip()}")
            match = re.search(r"(\d+)\s+bytes", line)
            if match:
                bytes_copied = int(match.group(1))
                percent = ""
                if total_bytes:
                    percent = f"{(bytes_copied / total_bytes) * 100:.1f}%"
                _display_lines([title, f"{human_size(bytes_copied)} {percent}".strip()])
                last_update = time.time()
        if dd_proc.poll() is not None:
            break
        if time.time() - last_update > 5:
            _display_lines([title, "Working..."])
            last_update = time.time()
    dd_proc.wait()
    sha_out, sha_err = sha_proc.communicate()
    if dd_proc.returncode != 0:
        error_output = dd_proc.stderr.read().strip()
        message = error_output.splitlines()[-1] if error_output else "dd failed"
        raise RuntimeError(message)
    if sha_proc.returncode != 0:
        message = sha_err.strip() or "sha256sum failed"
        raise RuntimeError(message)
    checksum = sha_out.split()[0] if sha_out else ""
    _display_lines([title, "Complete"])
    config.log_debug(f"sha256 for {device_node}: {checksum}")
    return checksum


def verify_clone_device(source_node, target_node, total_bytes=None):
    _require_display()
    print(f"Verifying {source_node} -> {target_node}")
    try:
        src_hash = compute_sha256(source_node, total_bytes=total_bytes, title="VERIFY SRC")
        dst_hash = compute_sha256(target_node, total_bytes=total_bytes, title="VERIFY DST")
    except RuntimeError as error:
        _display_lines(["VERIFY", "Error"])
        config.log_debug(f"Verify failed: {error}")
        return False
    if src_hash != dst_hash:
        _display_lines(["VERIFY", "Mismatch"])
        config.log_debug(f"Verify mismatch for {source_node} -> {target_node}")
        print("Verify failed: checksum mismatch")
        return False
    _display_lines(["VERIFY", "Complete"])
    print("Verify complete: checksums match")
    return True


def verify_clone(source, target):
    _require_display()
    source_node = resolve_device_node(source)
    target_node = resolve_device_node(target)
    source_name = os.path.basename(source_node)
    target_name = os.path.basename(target_node)
    source_device = get_device_by_name(source_name) or (source if isinstance(source, dict) else None)
    target_device = get_device_by_name(target_name) or (target if isinstance(target, dict) else None)
    if not source_device or not target_device:
        return verify_clone_device(source_node, target_node, source.get("size") if isinstance(source, dict) else None)
    source_parts = [child for child in get_children(source_device) if child.get("type") == "part"]
    if not source_parts:
        return verify_clone_device(source_node, target_node, source_device.get("size"))
    target_parts = [child for child in get_children(target_device) if child.get("type") == "part"]
    target_parts_by_number = {}
    for child in target_parts:
        part_number = get_partition_number(child.get("name"))
        if part_number is None:
            continue
        target_parts_by_number.setdefault(part_number, child)
    total_parts = len(source_parts)
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
            _display_lines(["VERIFY", "No target part"])
            config.log_debug(f"Verify failed: no target partition for {src_part}")
            return False
        print(f"Verifying {src_part} -> {dst_part}")
        try:
            src_hash = compute_sha256(src_part, total_bytes=part.get("size"), title=f"V {index}/{total_parts} SRC")
            dst_hash = compute_sha256(dst_part, total_bytes=part.get("size"), title=f"V {index}/{total_parts} DST")
        except RuntimeError as error:
            _display_lines(["VERIFY", "Error"])
            config.log_debug(f"Verify failed ({src_part} -> {dst_part}): {error}")
            return False
        if src_hash != dst_hash:
            _display_lines(["VERIFY", "Mismatch"])
            config.log_debug(f"Verify mismatch for {src_part} -> {dst_part}")
            print(f"Verify failed: {src_part} -> {dst_part}")
            return False
    _display_lines(["VERIFY", "Complete"])
    print("Verify complete: all partitions match")
    return True


def clone_device(source, target, mode=None):
    _require_display()
    mode = normalize_clone_mode(mode or config.CLONE_MODE)
    if mode in ("smart", "verify"):
        success = clone_device_smart(source, target)
        if not success:
            return False
        if mode == "verify":
            return verify_clone(source, target)
        return True
    unmount_device(target)
    try:
        clone_dd(source, target, total_bytes=source.get("size"), title="CLONING")
    except RuntimeError as error:
        _display_lines(["FAILED", str(error)[:20]])
        config.log_debug(f"Clone failed: {error}")
        return False
    return True


def clone_device_smart(source, target):
    _require_display()
    source_node = f"/dev/{source.get('name')}"
    target_node = f"/dev/{target.get('name')}"
    unmount_device(target)
    try:
        _display_lines(["CLONING", "Copy table"])
        copy_partition_table(source, target)
    except RuntimeError as error:
        _display_lines(["FAILED", "Partition tbl"])
        config.log_debug(f"Partition table copy failed: {error}")
        return False
    try:
        clone_partclone(source, target)
    except RuntimeError as error:
        _display_lines(["FAILED", str(error)[:20]])
        config.log_debug(f"Smart clone failed ({source_node} -> {target_node}): {error}")
        return False
    _display_lines(["CLONING", "Complete"])
    config.log_debug(f"Smart clone completed from {source_node} to {target_node}")
    return True


def erase_device(target, mode):
    _require_display()
    target_node = f"/dev/{target.get('name')}"
    unmount_device(target)
    mode = (mode or "").lower()
    device_label = format_device_label(target)
    mode_label = mode.upper() if mode else None
    if mode == "secure":
        shred_path = shutil.which("shred")
        if not shred_path:
            _display_lines(["ERROR", "no shred tool"])
            config.log_debug("Erase failed: shred not available")
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
            _display_lines(["ERROR", "no discard"])
            config.log_debug("Erase failed: blkdiscard not available")
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
            _display_lines(["ERROR", "no dd tool"])
            config.log_debug("Erase failed: dd not available")
            return False
        return run_progress_command(
            [dd_path, "if=/dev/zero", f"of={target_node}", "bs=4M", "status=progress", "conv=fsync"],
            total_bytes=target.get("size"),
            title="ERASING",
            device_label=device_label,
            mode_label=mode_label,
        )
    if mode != "quick":
        _display_lines(["ERROR", "unknown mode"])
        config.log_debug(f"Erase failed: unknown mode {mode}")
        return False
    wipefs_path = shutil.which("wipefs")
    if not wipefs_path:
        _display_lines(["ERROR", "no wipefs"])
        config.log_debug("Erase failed: wipefs not available")
        return False
    dd_path = shutil.which("dd")
    if not dd_path:
        _display_lines(["ERROR", "no dd tool"])
        config.log_debug("Erase failed: dd not available")
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
    wipe_mib = min(config.QUICK_WIPE_MIB, size_mib) if size_mib else config.QUICK_WIPE_MIB
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
            title="ERASING",
            device_label=device_label,
            mode_label=mode_label,
        )
    return True
