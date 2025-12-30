import os
import re
import shutil

from commands import (
    display_lines,
    log_debug,
    run_checked_command,
    run_checked_with_progress,
)
from devices import get_children, get_device_by_name, unmount_device


def resolve_device_node(device):
    if isinstance(device, str):
        return device if device.startswith("/dev/") else f"/dev/{device}"
    return f"/dev/{device.get('name')}"


def normalize_clone_mode(mode):
    if not mode:
        return "smart"
    mode = mode.lower()
    if mode == "raw":
        return "exact"
    if mode in ("smart", "exact", "verify"):
        return mode
    return "smart"


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
        log_debug(f"GPT partition table replicated from {src_node} to {dst_node}")
        return
    if label in ("dos", "mbr", "msdos"):
        run_checked_command([sfdisk_path, dst_node], input_text=dump_output)
        log_debug(f"MBR partition table cloned from {src_node} to {dst_node}")
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
        display_lines([f"PART {index}/{len(source_parts)}", tool])
        with open(dst_part, "wb") as dst_handle:
            run_checked_with_progress(
                [tool_path, "-s", src_part, "-o", "-", "-f"],
                total_bytes=part.get("size"),
                title=f"PART {index}/{len(source_parts)}",
                stdout_target=dst_handle,
            )


def clone_device(source, target, mode=None):
    mode = normalize_clone_mode(mode)
    if mode in ("smart", "verify"):
        success = clone_device_smart(source, target)
        if not success:
            return False
        if mode == "verify":
            from verify_ops import verify_clone

            return verify_clone(source, target)
        return True
    unmount_device(target)
    try:
        clone_dd(source, target, total_bytes=source.get("size"), title="CLONING")
    except RuntimeError as error:
        display_lines(["FAILED", str(error)[:20]])
        log_debug(f"Clone failed: {error}")
        return False
    return True


def clone_device_smart(source, target):
    source_node = f"/dev/{source.get('name')}"
    target_node = f"/dev/{target.get('name')}"
    unmount_device(target)
    try:
        display_lines(["CLONING", "Copy table"])
        copy_partition_table(source, target)
    except RuntimeError as error:
        display_lines(["FAILED", "Partition tbl"])
        log_debug(f"Partition table copy failed: {error}")
        return False
    try:
        clone_partclone(source, target)
    except RuntimeError as error:
        display_lines(["FAILED", str(error)[:20]])
        log_debug(f"Smart clone failed ({source_node} -> {target_node}): {error}")
        return False
    display_lines(["CLONING", "Complete"])
    log_debug(f"Smart clone completed from {source_node} to {target_node}")
    return True
