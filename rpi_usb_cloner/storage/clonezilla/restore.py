"""Clonezilla image restoration operations."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Iterable, Optional, TypedDict

from rpi_usb_cloner.logging import get_logger
from rpi_usb_cloner.storage import clone, devices
from rpi_usb_cloner.storage.clone import (
    format_filesystem_type,
    get_partition_display_name,
    get_partition_number,
    resolve_device_node,
)

from .compression import get_compression_type
from .file_utils import sorted_clonezilla_volumes
from .image_discovery import get_partclone_tool
from .models import ClonezillaImage, PartitionRestoreOp, RestorePlan
from .partition_table import (
    apply_disk_layout_op,
    build_partition_mode_layout_ops,
    estimate_required_size_bytes,
    normalize_partition_mode,
)


log = get_logger(source=__name__)


def get_blockdev_size_bytes(device_node: str) -> Optional[int]:
    """Get device size using blockdev command."""
    blockdev = shutil.which("blockdev")
    if not blockdev:
        return None
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


def get_device_size_bytes(
    target_info: Optional[dict], target_node: str
) -> Optional[int]:
    """Get device size from device info or blockdev."""
    if target_info:
        size_value = target_info.get("size")
        if size_value is not None:
            return int(size_value)
    return get_blockdev_size_bytes(target_node)


def reread_partition_table(target_node: str) -> None:
    """Force kernel to re-read partition table."""
    partprobe = shutil.which("partprobe")
    if partprobe:
        subprocess.run([partprobe, target_node], check=False)
        return
    blockdev = shutil.which("blockdev")
    if blockdev:
        subprocess.run([blockdev, "--rereadpt", target_node], check=False)


def settle_udev() -> None:
    """Wait for udev to settle."""
    udevadm = shutil.which("udevadm")
    if udevadm:
        subprocess.run([udevadm, "settle"], check=False)


def wait_for_partition_count(
    target_name: str,
    required_count: int,
    *,
    timeout_seconds: int,
    poll_interval: float = 0.5,
    allow_short: bool = False,
) -> tuple[dict, int]:
    """Wait for a specific number of partitions to appear."""
    deadline = time.monotonic() + timeout_seconds
    last_info = None
    last_count = 0
    while time.monotonic() < deadline:
        last_info = devices.get_device_by_name(target_name)
        if last_info:
            last_count = count_target_partitions(last_info)
            if last_count >= required_count:
                return last_info, last_count
        time.sleep(poll_interval)
    if not last_info:
        raise RuntimeError(
            "Unable to refresh target device after partition table update."
        )
    if allow_short:
        return last_info, last_count
    raise RuntimeError(
        "Partition table applied but kernel did not create all partitions "
        f"(expected {required_count}, saw {last_count})."
    )


class TargetPartitionInfo(TypedDict):
    node: str
    size_bytes: Optional[int]


def wait_for_target_partitions(
    target_name: str,
    parts: Iterable[str],
    *,
    timeout_seconds: int,
    poll_interval: float = 1.0,
) -> tuple[dict, dict[str, Optional[TargetPartitionInfo]]]:
    """Wait for specific partitions to appear after partition table update."""
    deadline = time.monotonic() + timeout_seconds
    last_info = None
    last_mapping: dict[str, Optional[TargetPartitionInfo]] = {}
    while time.monotonic() < deadline:
        last_info = devices.get_device_by_name(target_name)
        if last_info:
            last_mapping = map_target_partitions(parts, last_info)
            missing = [part for part in parts if not last_mapping.get(part)]
            if not missing:
                return last_info, last_mapping
        time.sleep(poll_interval)
    if not last_info:
        raise RuntimeError(
            "Unable to refresh target device after partition table update."
        )
    missing = [part for part in parts if not last_mapping.get(part)]
    missing_label = ", ".join(missing) if missing else "unknown"
    raise RuntimeError(f"Timed out waiting for partitions to appear: {missing_label}")


def map_target_partitions(
    parts: Iterable[str],
    target_device: dict,
) -> dict[str, Optional[TargetPartitionInfo]]:
    """Map source partition names to target partition info."""
    target_children = [
        child
        for child in devices.get_children(target_device)
        if child.get("type") == "part"
    ]
    target_by_number: dict[int, TargetPartitionInfo] = {}
    for child in target_children:
        number = get_partition_number(child.get("name"))
        if number is None:
            continue
        node = f"/dev/{child.get('name')}"
        size_bytes = child.get("size")
        if size_bytes is None:
            size_bytes = get_blockdev_size_bytes(node)
        else:
            size_bytes = int(size_bytes)
        target_by_number[number] = {"node": node, "size_bytes": size_bytes}
    mapping: dict[str, Optional[TargetPartitionInfo]] = {}
    for part_name in parts:
        number = get_partition_number(part_name)
        if number is None:
            continue
        mapping[part_name] = target_by_number.get(number)
    return mapping


def count_target_partitions(target_device: dict) -> int:
    """Count the number of partitions on a device."""
    return sum(
        1
        for child in devices.get_children(target_device)
        if child.get("type") == "part"
    )


def write_partition_table(table_path: Path, target_node: str) -> None:
    """Write a partition table file to a target device.

    Supports:
    - sfdisk format (-pt.sf)
    - sgdisk format (-pt.sgdisk)
    """
    if table_path.name.endswith("-pt.sf"):
        sfdisk = shutil.which("sfdisk")
        if not sfdisk:
            raise RuntimeError("sfdisk not found")
        contents = table_path.read_text()
        result = subprocess.run(
            [sfdisk, "--force", target_node],
            input=contents,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "sfdisk failed"
            raise RuntimeError(message)
        return
    if table_path.name.endswith("-pt.sgdisk"):
        sgdisk = shutil.which("sgdisk")
        if not sgdisk:
            raise RuntimeError("sgdisk not found")
        result = subprocess.run(
            [sgdisk, f"--load-backup={table_path}", target_node],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "sgdisk failed"
            raise RuntimeError(message)
        return
    raise RuntimeError("Unsupported partition table")


def build_restore_command_from_plan(
    op: PartitionRestoreOp, target_part: str
) -> list[str]:
    """Build the restoration command for a partition from a restore plan."""
    if op.tool == "partclone":
        fstype = (op.fstype or "").lower()
        tool = get_partclone_tool(fstype)
        if not tool:
            raise RuntimeError(f"partclone tool not found for filesystem '{fstype}'")
        return [tool, "-r", "-s", "-", "-o", target_part, "-F"]
    dd_path = shutil.which("dd")
    if not dd_path:
        raise RuntimeError("dd not found")
    return [dd_path, f"of={target_part}", "bs=4M", "status=progress", "conv=fsync"]


def run_restore_pipeline(
    image_files: list[Path],
    restore_command: list[str],
    *,
    title: str,
    total_bytes: Optional[int] = None,
    progress_callback: Optional[Callable[[list[str], Optional[float]], None]] = None,
    subtitle: Optional[str] = None,
) -> None:
    """Execute the restoration pipeline with decompression and progress tracking."""
    if not image_files:
        raise RuntimeError("No image files")
    image_files = sorted_clonezilla_volumes(image_files)
    cat_proc = subprocess.Popen(
        ["cat", *[str(path) for path in image_files]], stdout=subprocess.PIPE
    )
    upstream = cat_proc.stdout
    decompress_proc = None
    compression_type = get_compression_type(image_files)
    if compression_type == "gzip":
        gzip_path = shutil.which("pigz") or shutil.which("gzip")
        if not gzip_path:
            raise RuntimeError("gzip not found")
        decompress_proc = subprocess.Popen(
            [gzip_path, "-dc"],
            stdin=upstream,
            stdout=subprocess.PIPE,
        )
        upstream = decompress_proc.stdout
    elif compression_type == "zstd":
        zstd_path = shutil.which("pzstd") or shutil.which("zstd")
        if not zstd_path:
            raise RuntimeError("zstd not found")
        decompress_proc = subprocess.Popen(
            [zstd_path, "-dc"],
            stdin=upstream,
            stdout=subprocess.PIPE,
        )
        upstream = decompress_proc.stdout
    if upstream is None:
        raise RuntimeError("Restore pipeline failed")
    error: Optional[Exception] = None
    try:
        clone.run_checked_with_streaming_progress(
            restore_command,
            title=title,
            total_bytes=total_bytes,
            stdin_source=upstream,
            progress_callback=progress_callback,
            subtitle=subtitle,
        )
    except Exception as exc:
        error = exc
    finally:
        if cat_proc.stdout:
            cat_proc.stdout.close()
        cat_proc.wait()
        if decompress_proc:
            if decompress_proc.stdout:
                decompress_proc.stdout.close()
            decompress_proc.wait()
    if error:
        raise error
    if cat_proc.returncode != 0:
        raise RuntimeError("Image stream failed")
    if decompress_proc and decompress_proc.returncode != 0:
        raise RuntimeError("Image decompression failed")


def restore_partition_op(
    op: PartitionRestoreOp,
    target_part: str,
    *,
    title: str,
    total_bytes: Optional[int] = None,
    progress_callback: Optional[Callable[[list[str], Optional[float]], None]] = None,
    subtitle: Optional[str] = None,
) -> None:
    """Restore a single partition from a restore operation."""
    restore_command = build_restore_command_from_plan(op, target_part)
    run_restore_pipeline(
        op.image_files,
        restore_command,
        title=title,
        total_bytes=total_bytes,
        progress_callback=progress_callback,
        subtitle=subtitle,
    )


def restore_image(
    image: ClonezillaImage,
    target_device: dict,
    *,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """Restore a Clonezilla image to a target device (legacy API)."""
    if os.geteuid() != 0:
        raise RuntimeError("Run as root")
    if not devices.unmount_device(target_device):
        raise RuntimeError("Failed to unmount target device before restore")
    target_node = resolve_device_node(target_device)
    if not image.partition_table:
        raise RuntimeError("Partition table missing")
    write_partition_table(image.partition_table, target_node)
    time.sleep(2)
    refreshed = devices.get_device_by_name(target_device.get("name")) or target_device
    target_parts = map_target_partitions(image.parts, refreshed)
    total_parts = len(image.parts)
    for index, part_name in enumerate(image.parts, start=1):
        target_part = target_parts.get(part_name)
        if not target_part:
            raise RuntimeError(f"Missing target partition for {part_name}")
        if progress_callback:
            progress_callback(f"Restoring {part_name} {index}/{total_parts}")
        from .compression import is_compressed
        from .file_utils import find_image_files, has_partition_image_files

        partclone_files = find_image_files(image.path, part_name, "ptcl-img")
        dd_files = find_image_files(image.path, part_name, "img")
        if not partclone_files and not dd_files:
            if has_partition_image_files(image.path, part_name):
                raise RuntimeError(
                    f"Image set does not match partclone/dd naming convention for partition {part_name}"
                )
            raise RuntimeError(f"Image data missing for {part_name}")
        if partclone_files:
            from .file_utils import extract_partclone_fstype

            fstype = extract_partclone_fstype(part_name, partclone_files[0].name)
            if not dd_files or get_partclone_tool((fstype or "").lower()):
                descriptor = {
                    "mode": "partclone",
                    "fstype": fstype,
                    "compressed": is_compressed(partclone_files),
                }
                image_files = partclone_files
            else:
                descriptor = {"mode": "dd", "compressed": is_compressed(dd_files)}
                image_files = dd_files
        else:
            descriptor = {"mode": "dd", "compressed": is_compressed(dd_files)}
            image_files = dd_files
        if descriptor["mode"] == "partclone":
            fstype_value = descriptor.get("fstype")
            if isinstance(fstype_value, str):
                fstype = fstype_value.lower()
            else:
                fstype = ""
            tool = get_partclone_tool(fstype)
            if not tool:
                raise RuntimeError(
                    f"partclone tool not found for filesystem '{fstype}'"
                )
            command = [tool, "-r", "-s", "-", "-o", target_part["node"]]
        else:
            dd_path = shutil.which("dd")
            if not dd_path:
                raise RuntimeError("dd not found")
            command = [
                dd_path,
                f"of={target_part['node']}",
                "bs=4M",
                "status=progress",
                "conv=fsync",
            ]
        run_restore_pipeline(
            image_files,
            command,
            title=f"{part_name} ({index}/{total_parts})",
            total_bytes=target_part.get("size_bytes"),
        )
    if progress_callback:
        progress_callback("Finalizing...")


def restore_clonezilla_image(
    plan: RestorePlan,
    target_device: str,
    *,
    partition_mode: str = "k0",
    progress_callback: Optional[Callable[[list[str], Optional[float]], None]] = None,
) -> None:
    """Restore a Clonezilla image to a target device.

    Args:
        plan: Restore plan from parse_clonezilla_image()
        target_device: Target device node or name
        partition_mode: Partition table mode ("k0", "k", "k1", "k2")
        progress_callback: Optional callback for progress updates
    """

    def emit_prewrite_progress(step: str) -> None:
        if progress_callback:
            progress_callback(["Preparing media...", step], None)

    if os.geteuid() != 0:
        raise RuntimeError("Run as root")
    partition_mode = normalize_partition_mode(partition_mode)
    target_node = resolve_device_node(target_device)
    target_name = Path(target_node).name
    target_info = devices.get_device_by_name(target_name)
    if target_info and not devices.unmount_device(target_info):
        raise RuntimeError("Failed to unmount target device before restore")

    emit_prewrite_progress("Checking target size")
    required_size = estimate_required_size_bytes(
        plan.disk_layout_ops,
        image_dir=plan.image_dir,
    )
    target_size = get_device_size_bytes(target_info, target_node)
    if required_size is None or target_size is None:
        log.warning(
            "Unable to determine size information; skipping size check",
            required_size=required_size,
            target_size=target_size,
            tags=["clonezilla", "restore", "size"],
        )
    elif target_size < required_size:
        raise RuntimeError(
            f"Target device too small ({devices.human_size(target_size)} < {devices.human_size(required_size)})"
        )

    required_partitions = len(plan.parts)
    disk_layout_ops = build_partition_mode_layout_ops(
        plan.disk_layout_ops,
        partition_mode=partition_mode,
        target_size=target_size,
    )
    post_layout_ops = [
        op for op in disk_layout_ops if op.kind == "hidden-data-after-mbr"
    ]
    layout_ops = [op for op in disk_layout_ops if op.kind != "hidden-data-after-mbr"]

    if partition_mode == "k":
        emit_prewrite_progress("Checking existing partition layout")
        emit_prewrite_progress("Waiting for partitions")
        refreshed, observed_count = wait_for_partition_count(
            target_name,
            required_partitions,
            timeout_seconds=10,
            allow_short=True,
        )
        if observed_count < required_partitions:
            raise RuntimeError(
                "target partition table missing required partitions for restore in -k mode"
            )
        target_parts = map_target_partitions(plan.parts, refreshed)
    else:
        applied_layout = False
        attempt_results: list[str] = []
        emit_prewrite_progress("Applying partition layout")
        for layout_op in layout_ops:
            try:
                applied_layout = apply_disk_layout_op(layout_op, target_node)
            except Exception as exc:
                raise RuntimeError(
                    f"Partition table apply failed ({layout_op.kind}): {exc}"
                ) from exc
            if not applied_layout:
                continue
            reread_partition_table(target_node)
            emit_prewrite_progress("Waiting for udev to settle")
            settle_udev()
            emit_prewrite_progress("Waiting for partitions")
            _, observed_count = wait_for_partition_count(
                target_name,
                required_partitions,
                timeout_seconds=10,
                allow_short=True,
            )
            if observed_count >= required_partitions:
                break
            if observed_count < required_partitions:
                log.warning(
                    "Partition count mismatch after %s layout op (expected %s, saw %s).",
                    layout_op.kind,
                    required_partitions,
                    observed_count,
                )
                attempt_results.append(
                    f"{layout_op.kind}: expected {required_partitions}, saw {observed_count}"
                )
                applied_layout = False
        if layout_ops and not applied_layout:
            attempts = (
                "; ".join(attempt_results)
                if attempt_results
                else "no successful layout ops"
            )
            raise RuntimeError(
                "Partition table apply failed to produce expected partition count "
                f"(expected {required_partitions}). Attempts: {attempts}."
            )
        refreshed, target_parts = wait_for_target_partitions(
            target_name,
            plan.parts,
            timeout_seconds=10,
        )

    if post_layout_ops:
        emit_prewrite_progress("Applying post-layout updates")
    for layout_op in post_layout_ops:
        try:
            apply_disk_layout_op(layout_op, target_node)
        except Exception as exc:
            raise RuntimeError(
                f"Partition table apply failed ({layout_op.kind}): {exc}"
            ) from exc

    total_parts = len(plan.partition_ops)
    for index, op in enumerate(plan.partition_ops, start=1):
        target_part = target_parts.get(op.partition)
        if not target_part:
            raise RuntimeError(f"Missing target partition for {op.partition}")

        # Get partition device info for better display
        part_node = target_part["node"]
        part_name = Path(part_node).name
        part_device = devices.get_device_by_name(part_name)

        # Build friendly display information
        if part_device:
            part_display_name = get_partition_display_name(part_device)
        else:
            part_display_name = part_name

        # Build title: "partition_name (1/4)"
        title = f"{part_display_name} ({index}/{total_parts})"

        # Build subtitle: "8.2GB ext4" or "512MB FAT32"
        subtitle_parts = []
        if target_part.get("size_bytes"):
            subtitle_parts.append(devices.human_size(target_part["size_bytes"]))
        if op.fstype:
            subtitle_parts.append(format_filesystem_type(op.fstype))
        subtitle = " ".join(subtitle_parts) if subtitle_parts else None

        try:
            restore_partition_op(
                op,
                part_node,
                title=title,
                total_bytes=target_part.get("size_bytes"),
                progress_callback=progress_callback,
                subtitle=subtitle,
            )
        except Exception as exc:
            raise RuntimeError(f"Partition restore failed ({title}): {exc}") from exc
