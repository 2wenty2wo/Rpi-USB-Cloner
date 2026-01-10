"""Image discovery and parsing for Clonezilla images."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from rpi_usb_cloner.storage import devices

from .compression import is_compressed
from .file_utils import extract_partclone_fstype, find_image_files, has_partition_image_files
from .models import ClonezillaImage, DiskLayoutOp, PartitionRestoreOp, RestorePlan


def get_mountpoint(device: dict) -> Optional[str]:
    """Get the mountpoint of a device or its children."""
    if device.get("mountpoint"):
        return device.get("mountpoint")
    for child in devices.get_children(device):
        mountpoint = child.get("mountpoint")
        if mountpoint:
            return mountpoint
    return None


def find_partition_table(image_dir: Path) -> Optional[Path]:
    """Find the partition table file in a Clonezilla image directory."""
    for suffix in ("-pt.sf", "-pt.sgdisk", "-pt.parted"):
        matches = list(image_dir.glob(f"*{suffix}"))
        if matches:
            return matches[0]
    return None


def is_clonezilla_image_dir(path: Path) -> bool:
    """Check if a directory contains a Clonezilla image."""
    parts_file = path / "parts"
    if not parts_file.exists():
        return False
    has_table = find_partition_table(path) is not None
    has_images = any(path.glob("*-ptcl-img*")) or any(path.glob("*dd-img*"))
    return has_table or has_images


def find_image_repository(device: dict) -> Optional[Path]:
    """Find Clonezilla image repository on a mounted device.

    Searches common locations:
    - <mountpoint>/clonezilla
    - <mountpoint>/images
    - <mountpoint>
    """
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
    """List all Clonezilla image directories in a repository."""
    if not repo_path.is_dir():
        return []
    image_dirs = []
    for entry in repo_path.iterdir():
        if entry.is_dir() and is_clonezilla_image_dir(entry):
            image_dirs.append(entry)
    return sorted(image_dirs, key=lambda path: path.name)


def load_image(image_dir: Path) -> ClonezillaImage:
    """Load Clonezilla image metadata from a directory."""
    if not image_dir.is_dir():
        raise RuntimeError("Image folder not found")
    parts_path = image_dir / "parts"
    if not parts_path.exists():
        raise RuntimeError("Clonezilla parts file missing")
    parts = [item.strip() for item in parts_path.read_text().split() if item.strip()]
    if not parts:
        raise RuntimeError("Clonezilla parts list empty")
    partition_table = find_partition_table(image_dir)
    return ClonezillaImage(
        name=image_dir.name,
        path=image_dir,
        parts=parts,
        partition_table=partition_table,
    )


def get_partclone_tool(fstype: str) -> Optional[str]:
    """Find the partclone tool for a filesystem type.

    Returns:
        Path to the partclone tool, or None if not available
    """
    import os
    import shutil

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


def build_partition_restore_op(image_dir: Path, part_name: str) -> Optional[PartitionRestoreOp]:
    """Build a partition restore operation from image files.

    Args:
        image_dir: Clonezilla image directory
        part_name: Partition name (e.g., "sda1")

    Returns:
        PartitionRestoreOp or None if no suitable image files found
    """
    partclone_files = find_image_files(image_dir, part_name, "ptcl-img")
    dd_files = find_image_files(image_dir, part_name, "img")

    if partclone_files:
        fstype = extract_partclone_fstype(part_name, partclone_files[0].name)
        if not dd_files:
            return PartitionRestoreOp(
                partition=part_name,
                image_files=partclone_files,
                tool="partclone",
                fstype=fstype,
                compressed=is_compressed(partclone_files),
            )
        tool = get_partclone_tool((fstype or "").lower())
        if tool:
            return PartitionRestoreOp(
                partition=part_name,
                image_files=partclone_files,
                tool="partclone",
                fstype=fstype,
                compressed=is_compressed(partclone_files),
            )

    if dd_files:
        return PartitionRestoreOp(
            partition=part_name,
            image_files=dd_files,
            tool="dd",
            fstype=None,
            compressed=is_compressed(dd_files),
        )

    if has_partition_image_files(image_dir, part_name):
        raise RuntimeError(f"Image set does not match partclone/dd naming convention for partition {part_name}")

    return None


def parse_clonezilla_image(image_dir: Path) -> RestorePlan:
    """Parse a Clonezilla image directory and create a restore plan."""
    from .partition_table import collect_disk_layout_ops

    if not image_dir.is_dir():
        raise RuntimeError("Image folder not found")
    parts_path = image_dir / "parts"
    if not parts_path.exists():
        raise RuntimeError("Clonezilla parts file missing")
    parts = [item.strip() for item in parts_path.read_text().split() if item.strip()]
    if not parts:
        raise RuntimeError("Clonezilla parts list empty")

    disk_layout_ops = collect_disk_layout_ops(image_dir)
    partition_ops = []
    for part_name in parts:
        partition_op = build_partition_restore_op(image_dir, part_name)
        if not partition_op:
            raise RuntimeError(f"Image data missing for {part_name}")
        partition_ops.append(partition_op)

    return RestorePlan(
        image_dir=image_dir,
        parts=parts,
        disk_layout_ops=disk_layout_ops,
        partition_ops=partition_ops,
    )
