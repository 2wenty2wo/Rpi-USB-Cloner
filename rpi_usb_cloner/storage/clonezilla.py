from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from rpi_usb_cloner.storage import devices
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


def _is_clonezilla_image_dir(path: Path) -> bool:
    parts_file = path / "parts"
    if not parts_file.exists():
        return False
    has_table = _find_partition_table(path) is not None
    has_images = any(path.glob("*-ptcl-img*")) or any(path.glob("*dd-img*"))
    return has_table or has_images


def _collect_disk_layout_ops(image_dir: Path) -> list[DiskLayoutOp]:
    disk_layout_ops: list[DiskLayoutOp] = []
    for name, kind in (("disk", "disk"), ("sfdisk", "sfdisk")):
        path = image_dir / name
        if path.exists():
            disk_layout_ops.append(_read_disk_layout_op(kind, path))
    for path in sorted(image_dir.glob("*-pt.parted")):
        disk_layout_ops.append(_read_disk_layout_op("pt.parted", path))
    for path in sorted(image_dir.glob("*-mbr")):
        disk_layout_ops.append(_read_disk_layout_op("mbr", path))
    for path in sorted(image_dir.glob("*-gpt")):
        disk_layout_ops.append(_read_disk_layout_op("gpt", path))
    return disk_layout_ops


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
    return shutil.which(tool)


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
