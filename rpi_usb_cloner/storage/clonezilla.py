from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from rpi_usb_cloner.storage import clone, devices
from rpi_usb_cloner.storage.clone import get_partition_number, resolve_device_node


@dataclass(frozen=True)
class ClonezillaImage:
    name: str
    path: Path
    parts: list[str]
    partition_table: Optional[Path]


@dataclass(frozen=True)
class DiskLayoutOp:
    kind: str
    path: Path
    contents: Optional[str]
    size_bytes: int


@dataclass(frozen=True)
class PartitionRestoreOp:
    partition: str
    image_files: list[Path]
    tool: str
    fstype: Optional[str]
    compressed: bool


@dataclass(frozen=True)
class RestorePlan:
    image_dir: Path
    parts: list[str]
    disk_layout_ops: list[DiskLayoutOp]
    partition_ops: list[PartitionRestoreOp]


def parse_clonezilla_image(image_dir: Path) -> RestorePlan:
    if not image_dir.is_dir():
        raise RuntimeError("Image folder not found")
    parts_path = image_dir / "parts"
    if not parts_path.exists():
        raise RuntimeError("Clonezilla parts file missing")
    parts = [item.strip() for item in parts_path.read_text().split() if item.strip()]
    if not parts:
        raise RuntimeError("Clonezilla parts list empty")
    disk_layout_ops = _collect_disk_layout_ops(image_dir)
    partition_ops = []
    for part_name in parts:
        partition_op = _build_partition_restore_op(image_dir, part_name)
        if not partition_op:
            raise RuntimeError(f"Image data missing for {part_name}")
        partition_ops.append(partition_op)
    return RestorePlan(
        image_dir=image_dir,
        parts=parts,
        disk_layout_ops=disk_layout_ops,
        partition_ops=partition_ops,
    )


def get_mountpoint(device: dict) -> Optional[str]:
    if device.get("mountpoint"):
        return device.get("mountpoint")
    for child in devices.get_children(device):
        mountpoint = child.get("mountpoint")
        if mountpoint:
            return mountpoint
    return None


def find_image_repository(device: dict) -> Optional[Path]:
    mountpoint = get_mountpoint(device)
    if not mountpoint:
        return None
    mount_path = Path(mountpoint)
    candidates = [mount_path / "clonezilla", mount_path / "images", mount_path]
    for candidate in candidates:
        if candidate.is_dir():
            if list_clonezilla_image_dirs(candidate):
                return candidate
    return None


def list_clonezilla_image_dirs(repo_path: Path) -> list[Path]:
    if not repo_path.is_dir():
        return []
    image_dirs = []
    for entry in repo_path.iterdir():
        if entry.is_dir() and _is_clonezilla_image_dir(entry):
            image_dirs.append(entry)
    return sorted(image_dirs, key=lambda path: path.name)


def load_image(image_dir: Path) -> ClonezillaImage:
    if not image_dir.is_dir():
        raise RuntimeError("Image folder not found")
    parts_path = image_dir / "parts"
    if not parts_path.exists():
        raise RuntimeError("Clonezilla parts file missing")
    parts = [item.strip() for item in parts_path.read_text().split() if item.strip()]
    if not parts:
        raise RuntimeError("Clonezilla parts list empty")
    partition_table = _find_partition_table(image_dir)
    return ClonezillaImage(name=image_dir.name, path=image_dir, parts=parts, partition_table=partition_table)


def restore_image(
    image: ClonezillaImage,
    target_device: dict,
    *,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> None:
    if os.geteuid() != 0:
        raise RuntimeError("Run as root")
    devices.unmount_device(target_device)
    target_node = resolve_device_node(target_device)
    if not image.partition_table:
        raise RuntimeError("Partition table missing")
    _write_partition_table(image.partition_table, target_node)
    time.sleep(2)
    refreshed = devices.get_device_by_name(target_device.get("name")) or target_device
    target_parts = _map_target_partitions(image.parts, refreshed)
    total_parts = len(image.parts)
    for index, part_name in enumerate(image.parts, start=1):
        target_part = target_parts.get(part_name)
        if not target_part:
            raise RuntimeError(f"Missing target partition for {part_name}")
        if progress_callback:
            progress_callback(f"Restoring {part_name} {index}/{total_parts}")
        _restore_partition(image.path, part_name, target_part)
    if progress_callback:
        progress_callback("Finalizing...")


def restore_clonezilla_image(plan: RestorePlan, target_device: str) -> None:
    if os.geteuid() != 0:
        raise RuntimeError("Run as root")
    target_node = resolve_device_node(target_device)
    target_name = Path(target_node).name
    target_info = devices.get_device_by_name(target_name)
    if target_info:
        devices.unmount_device(target_info)
    required_size = _estimate_required_size_bytes(
        plan.disk_layout_ops,
        image_dir=plan.image_dir,
    )
    target_size = _get_device_size_bytes(target_info, target_node)
    if required_size is None or target_size is None:
        print("Warning: unable to determine size information; skipping size check.")
    elif target_size < required_size:
        raise RuntimeError(
            f"Target device too small ({devices.human_size(target_size)} < {devices.human_size(required_size)})"
        )
    for op in plan.disk_layout_ops:
        try:
            _apply_disk_layout_op(op, target_node)
        except Exception as exc:
            raise RuntimeError(f"Partition table apply failed ({op.kind}): {exc}") from exc
    time.sleep(2)
    refreshed = devices.get_device_by_name(target_name) or target_info
    if not refreshed:
        raise RuntimeError("Unable to refresh target device")
    target_parts = _map_target_partitions(plan.parts, refreshed)
    total_parts = len(plan.partition_ops)
    for index, op in enumerate(plan.partition_ops, start=1):
        target_part = target_parts.get(op.partition)
        if not target_part:
            raise RuntimeError(f"Missing target partition for {op.partition}")
        title = f"PART {index}/{total_parts}"
        try:
            _restore_partition_op(op, target_part, title=title)
        except Exception as exc:
            raise RuntimeError(f"Partition restore failed ({title}): {exc}") from exc


def _is_clonezilla_image_dir(path: Path) -> bool:
    parts_file = path / "parts"
    if not parts_file.exists():
        return False
    has_table = _find_partition_table(path) is not None
    has_images = any(path.glob("*-ptcl-img*")) or any(path.glob("*dd-img*"))
    return has_table or has_images


def _collect_disk_layout_ops(image_dir: Path, *, select: bool = True) -> list[DiskLayoutOp]:
    disk_layout_ops: list[DiskLayoutOp] = []
    for name, kind in (("disk", "disk"), ("sfdisk", "sfdisk")):
        path = image_dir / name
        if path.exists():
            disk_layout_ops.append(_read_disk_layout_op(kind, path))
    for path in sorted(image_dir.glob("*-pt.sf")):
        disk_layout_ops.append(_read_disk_layout_op("pt.sf", path))
    for path in sorted(image_dir.glob("*-pt.parted")):
        disk_layout_ops.append(_read_disk_layout_op("pt.parted", path))
    for path in sorted(image_dir.glob("*-pt.sgdisk")):
        disk_layout_ops.append(_read_disk_layout_op("pt.sgdisk", path))
    for path in sorted(image_dir.glob("*-mbr")):
        disk_layout_ops.append(_read_disk_layout_op("mbr", path))
    for path in sorted(image_dir.glob("*-gpt")):
        disk_layout_ops.append(_read_disk_layout_op("gpt", path))
    if select:
        return _select_disk_layout_ops(disk_layout_ops)
    return disk_layout_ops


def _select_disk_layout_ops(disk_layout_ops: list[DiskLayoutOp]) -> list[DiskLayoutOp]:
    if not disk_layout_ops:
        return []
    priority = ["pt.sgdisk", "gpt", "pt.parted", "pt.sf", "mbr", "sfdisk", "disk"]
    for kind in priority:
        for op in disk_layout_ops:
            if op.kind == kind:
                return [op]
    return [disk_layout_ops[0]]


def _read_disk_layout_op(kind: str, path: Path) -> DiskLayoutOp:
    data = path.read_bytes()
    size_bytes = len(data)
    contents: Optional[str]
    if b"\x00" in data[:1024]:
        contents = None
    else:
        contents = data.decode("utf-8", errors="replace")
    return DiskLayoutOp(kind=kind, path=path, contents=contents, size_bytes=size_bytes)


def _build_partition_restore_op(image_dir: Path, part_name: str) -> Optional[PartitionRestoreOp]:
    partclone_files = _find_image_files(image_dir, part_name, "ptcl-img")
    if partclone_files:
        fstype = _extract_partclone_fstype(part_name, partclone_files[0].name)
        return PartitionRestoreOp(
            partition=part_name,
            image_files=partclone_files,
            tool="partclone",
            fstype=fstype,
            compressed=_is_gzip_compressed(partclone_files),
        )
    dd_files = _find_image_files(image_dir, part_name, "img")
    if dd_files:
        return PartitionRestoreOp(
            partition=part_name,
            image_files=dd_files,
            tool="dd",
            fstype=None,
            compressed=_is_gzip_compressed(dd_files),
        )
    return None


def _estimate_required_size_bytes(
    disk_layout_ops: list[DiskLayoutOp],
    *,
    image_dir: Optional[Path] = None,
) -> Optional[int]:
    ops = list(disk_layout_ops)
    if image_dir:
        extra_ops = _collect_disk_layout_ops(image_dir, select=False)
        seen_paths = {op.path for op in ops}
        for op in extra_ops:
            if op.path not in seen_paths:
                ops.append(op)
                seen_paths.add(op.path)
    sector_size = 512
    max_sector = None
    for op in ops:
        if not op.contents:
            if op.kind == "pt.sgdisk":
                max_lba = _estimate_last_lba_from_sgdisk_backup(op.path)
                if max_lba is not None and (max_sector is None or max_lba > max_sector):
                    max_sector = max_lba
            continue
        contents = op.contents.splitlines()
        for line in contents:
            line = line.strip()
            if not line:
                continue
            if line.startswith("sector-size:"):
                match = re.search(r"sector-size:\s*(\d+)", line)
                if match:
                    sector_size = int(match.group(1))
            if line.startswith("last-lba:"):
                match = re.search(r"last-lba:\s*(\d+)", line)
                if match:
                    last_lba = int(match.group(1))
                    if max_sector is None or last_lba > max_sector:
                        max_sector = last_lba
            start_match = re.search(r"start=\s*(\d+)", line)
            size_match = re.search(r"size=\s*(\d+)", line)
            if start_match and size_match:
                start = int(start_match.group(1))
                size = int(size_match.group(1))
                end = start + max(size - 1, 0)
                if max_sector is None or end > max_sector:
                    max_sector = end
            if ":" in line and line.lstrip().startswith("/dev/"):
                fields = [field.strip() for field in line.split(":")]
                if len(fields) > 1 and fields[1].endswith("s"):
                    total_sectors = int(fields[1][:-1])
                    end_sector = max(total_sectors - 1, 0)
                    if max_sector is None or end_sector > max_sector:
                        max_sector = end_sector
            if line[0].isdigit() and ":" in line:
                fields = [field.strip() for field in line.split(":")]
                if len(fields) > 2 and fields[1].endswith("s") and fields[2].endswith("s"):
                    end_sector = int(fields[2][:-1])
                    if max_sector is None or end_sector > max_sector:
                        max_sector = end_sector
    if max_sector is None:
        return None
    return (max_sector + 1) * sector_size


def _get_device_size_bytes(target_info: Optional[dict], target_node: str) -> Optional[int]:
    if target_info and target_info.get("size"):
        return int(target_info.get("size"))
    blockdev = shutil.which("blockdev")
    if not blockdev:
        return None
    result = subprocess.run(
        [blockdev, "--getsize64", target_node],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _apply_disk_layout_op(op: DiskLayoutOp, target_node: str) -> None:
    if op.kind in {"disk", "sfdisk", "pt.sf"}:
        if not op.contents:
            raise RuntimeError("Missing sfdisk data")
        sfdisk = shutil.which("sfdisk")
        if not sfdisk:
            raise RuntimeError("sfdisk not found")
        result = subprocess.run(
            [sfdisk, "--force", target_node],
            input=op.contents,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            message = _format_command_failure("sfdisk failed", [sfdisk, "--force", target_node], result)
            raise RuntimeError(message)
        return
    if op.kind == "pt.parted":
        if not op.contents:
            raise RuntimeError("Missing parted data")
        parted = shutil.which("parted")
        if not parted:
            raise RuntimeError("parted not found")
        result = subprocess.run(
            [parted, "-s", target_node],
            input=op.contents,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            message = _format_command_failure("parted failed", [parted, "--script", target_node], result)
            raise RuntimeError(message)
        return
    if op.kind == "mbr":
        dd_path = shutil.which("dd")
        if not dd_path:
            raise RuntimeError("dd not found")
        result = subprocess.run(
            [
                dd_path,
                f"if={op.path}",
                f"of={target_node}",
                "bs=1",
                f"count={op.size_bytes}",
                "conv=fsync",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            message = _format_command_failure("dd failed", result.args, result)
            raise RuntimeError(message)
        return
    if op.kind == "gpt":
        sgdisk = shutil.which("sgdisk")
        if not sgdisk:
            raise RuntimeError("sgdisk not found")
        result = subprocess.run(
            [sgdisk, f"--load-backup={op.path}", target_node],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            message = _format_command_failure("sgdisk failed", result.args, result)
            raise RuntimeError(message)
        return
    if op.kind == "pt.sgdisk":
        sgdisk = shutil.which("sgdisk")
        if not sgdisk:
            raise RuntimeError("sgdisk not found")
        result = subprocess.run(
            [sgdisk, f"--load-backup={op.path}", target_node],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            message = _format_command_failure("sgdisk failed", result.args, result)
            raise RuntimeError(message)
        return
    raise RuntimeError(f"Unsupported disk layout op: {op.kind}")


def _format_command_failure(summary: str, command: list[str], result: subprocess.CompletedProcess) -> str:
    stderr = " ".join(result.stderr.strip().split())
    stdout = " ".join(result.stdout.strip().split())
    details = []
    if stderr:
        details.append(f"stderr: {stderr}")
    if stdout:
        details.append(f"stdout: {stdout}")
    if details:
        return f"{summary} ({' '.join(command)}): {' | '.join(details)}"
    return f"{summary} ({' '.join(command)})"


def _estimate_last_lba_from_sgdisk_backup(path: Path) -> Optional[int]:
    data = path.read_bytes()
    signature = b"EFI PART"
    offset = data.find(signature)
    if offset == -1 or len(data) < offset + 56:
        return None
    current_lba = struct.unpack_from("<Q", data, offset + 24)[0]
    backup_lba = struct.unpack_from("<Q", data, offset + 32)[0]
    last_usable = struct.unpack_from("<Q", data, offset + 48)[0]
    return max(current_lba, backup_lba, last_usable)


def _restore_partition_op(op: PartitionRestoreOp, target_part: str, *, title: str) -> None:
    restore_command = _build_restore_command_from_plan(op, target_part)
    _run_restore_pipeline(op.image_files, restore_command, title=title)


def _find_image_files(image_dir: Path, part_name: str, suffix: str) -> list[Path]:
    if suffix == "ptcl-img":
        pattern = f"{part_name}.*-{suffix}*"
    elif suffix == "img":
        patterns = [f"{part_name}.dd-img*", f"{part_name}.{suffix}*"]
        matches = []
        for candidate in patterns:
            matches.extend(image_dir.glob(candidate))
        return sorted({path for path in matches})
    else:
        pattern = f"{part_name}.{suffix}*"
    return sorted(image_dir.glob(pattern))


def _extract_partclone_fstype(part_name: str, file_name: str) -> Optional[str]:
    match = re.search(rf"{re.escape(part_name)}\.(.+?)-ptcl-img", file_name)
    if not match:
        return None
    return match.group(1)


def _find_partition_table(image_dir: Path) -> Optional[Path]:
    for suffix in ("-pt.sf", "-pt.sgdisk", "-pt.parted"):
        matches = list(image_dir.glob(f"*{suffix}"))
        if matches:
            return matches[0]
    return None


def _write_partition_table(table_path: Path, target_node: str) -> None:
    if table_path.name.endswith("-pt.sf"):
        sfdisk = shutil.which("sfdisk")
        if not sfdisk:
            raise RuntimeError("sfdisk not found")
        contents = table_path.read_text()
        result = subprocess.run(
            [sfdisk, "--force", target_node],
            input=contents,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "sgdisk failed"
            raise RuntimeError(message)
        return
    raise RuntimeError("Unsupported partition table")


def _map_target_partitions(parts: Iterable[str], target_device: dict) -> dict[str, str]:
    target_children = [child for child in devices.get_children(target_device) if child.get("type") == "part"]
    target_by_number = {}
    for child in target_children:
        number = get_partition_number(child.get("name"))
        if number is None:
            continue
        target_by_number[number] = f"/dev/{child.get('name')}"
    mapping = {}
    for part_name in parts:
        number = get_partition_number(part_name)
        if number is None:
            continue
        mapping[part_name] = target_by_number.get(number)
    return mapping


def _restore_partition(image_dir: Path, part_name: str, target_part: str) -> None:
    image_files = sorted(image_dir.glob(f"{part_name}.*-img*"))
    if not image_files:
        raise RuntimeError(f"Image data missing for {part_name}")
    descriptor = _get_partition_descriptor(part_name, image_files)
    command, supports_progress = _build_restore_command(descriptor, target_part)
    _run_pipeline(image_files, command, supports_progress)


def _get_partition_descriptor(part_name: str, image_files: list[Path]) -> dict:
    file_name = image_files[0].name
    partclone_match = re.search(rf"{re.escape(part_name)}\.(.+?)-ptcl-img", file_name)
    if partclone_match:
        return {
            "mode": "partclone",
            "fstype": partclone_match.group(1),
            "compressed": _is_gzip_compressed(image_files),
        }
    if "dd-img" in file_name:
        return {"mode": "dd", "compressed": _is_gzip_compressed(image_files)}
    return {"mode": "dd", "compressed": _is_gzip_compressed(image_files)}


def _is_gzip_compressed(image_files: list[Path]) -> bool:
    for image_file in image_files:
        if ".gz" in image_file.suffixes:
            return True
        if image_file.name.endswith(".gz"):
            return True
    return False


def _build_restore_command(descriptor: dict, target_part: str) -> tuple[list[str], bool]:
    if descriptor["mode"] == "partclone":
        fstype = descriptor.get("fstype", "").lower()
        tool = _get_partclone_tool(fstype)
        if tool:
            return [tool, "-r", "-s", "-", "-o", target_part], True
        raise RuntimeError(f"partclone tool not found for filesystem '{fstype}'")
    dd_path = shutil.which("dd")
    if not dd_path:
        raise RuntimeError("dd not found")
    return [dd_path, f"of={target_part}", "bs=4M", "status=progress", "conv=fsync"], True


def _get_partclone_tool(fstype: str) -> Optional[str]:
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
    tool = partclone_tools.get(fstype)
    if not tool:
        return None
    found = shutil.which(tool)
    if found:
        return found
    for prefix in ("/usr/sbin", "/sbin", "/usr/local/sbin"):
        candidate = Path(prefix) / tool
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _build_restore_command_from_plan(op: PartitionRestoreOp, target_part: str) -> list[str]:
    if op.tool == "partclone":
        fstype = (op.fstype or "").lower()
        tool = _get_partclone_tool(fstype)
        if not tool:
            raise RuntimeError(f"partclone tool not found for filesystem '{fstype}'")
        return [tool, "-r", "-s", "-", "-o", target_part, "-F"]
    dd_path = shutil.which("dd")
    if not dd_path:
        raise RuntimeError("dd not found")
    return [dd_path, f"of={target_part}", "bs=4M", "status=progress", "conv=fsync"]


def _run_pipeline(image_files: list[Path], restore_command: list[str], supports_progress: bool) -> None:
    if not image_files:
        raise RuntimeError("No image files")
    cat_proc = subprocess.Popen(["cat", *[str(path) for path in image_files]], stdout=subprocess.PIPE)
    upstream = cat_proc.stdout
    decompress_proc = None
    if _is_gzip_compressed(image_files):
        gzip_path = shutil.which("pigz") or shutil.which("gzip")
        if not gzip_path:
            raise RuntimeError("gzip not found")
        decompress_proc = subprocess.Popen(
            [gzip_path, "-dc"],
            stdin=upstream,
            stdout=subprocess.PIPE,
        )
        upstream = decompress_proc.stdout
    if upstream is None:
        raise RuntimeError("Restore pipeline failed")
    restore_proc = subprocess.Popen(
        restore_command,
        stdin=upstream,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout, stderr = restore_proc.communicate()
    if cat_proc.stdout:
        cat_proc.stdout.close()
    cat_proc.wait()
    if decompress_proc:
        if decompress_proc.stdout:
            decompress_proc.stdout.close()
        decompress_proc.wait()
    if restore_proc.returncode != 0:
        message = (stderr or stdout or "Restore failed").strip()
        raise RuntimeError(message)
    if supports_progress:
        return


def _run_restore_pipeline(image_files: list[Path], restore_command: list[str], *, title: str) -> None:
    if not image_files:
        raise RuntimeError("No image files")
    cat_proc = subprocess.Popen(["cat", *[str(path) for path in image_files]], stdout=subprocess.PIPE)
    upstream = cat_proc.stdout
    decompress_proc = None
    if _is_gzip_compressed(image_files):
        gzip_path = shutil.which("pigz") or shutil.which("gzip")
        if not gzip_path:
            raise RuntimeError("gzip not found")
        decompress_proc = subprocess.Popen(
            [gzip_path, "-dc"],
            stdin=upstream,
            stdout=subprocess.PIPE,
        )
        upstream = decompress_proc.stdout
    if upstream is None:
        raise RuntimeError("Restore pipeline failed")
    error: Optional[Exception] = None
    try:
        clone.run_checked_with_progress(
            restore_command,
            title=title,
            stdin_source=upstream,
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
