from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from rpi_usb_cloner.storage import clonezilla, devices, mount

REPO_FLAG_FILENAME = ".rpi-usb-cloner-image-repo"


def _iter_partitions(device: dict) -> Iterable[dict]:
    stack = list(devices.get_children(device))
    while stack:
        child = stack.pop()
        if child.get("type") == "part":
            yield child
        stack.extend(devices.get_children(child))


def _resolve_mountpoint(partition: dict) -> Optional[Path]:
    mountpoint = partition.get("mountpoint")
    if mountpoint:
        return Path(mountpoint)
    name = partition.get("name")
    if not name:
        return None
    partition_node = f"/dev/{name}"

    # Attempt to mount the partition, handle new exceptions
    try:
        mount.mount_partition(partition_node, name=name)
    except (ValueError, RuntimeError) as e:
        # Mount failed - log but continue (partition may already be mounted or inaccessible)
        # Returning None will cause this partition to be skipped
        return None

    mounted_partition = None
    for device in devices.list_usb_disks():
        for child in _iter_partitions(device):
            if child.get("name") == name:
                mounted_partition = child
                break
        if mounted_partition:
            break
    if not mounted_partition:
        return None
    mountpoint = mounted_partition.get("mountpoint")
    if not mountpoint:
        return None
    return Path(mountpoint)


def find_image_repos(flag_filename: str = REPO_FLAG_FILENAME) -> list[Path]:
    repos: list[Path] = []
    seen: set[Path] = set()
    for device in devices.list_usb_disks():
        for partition in _iter_partitions(device):
            mountpoint = _resolve_mountpoint(partition)
            if not mountpoint:
                continue
            if not (mountpoint / flag_filename).exists():
                continue
            if mountpoint in seen:
                continue
            repos.append(mountpoint)
            seen.add(mountpoint)
    return repos


def list_clonezilla_images(repo_root: Path) -> list[Path]:
    candidates = [repo_root / "clonezilla", repo_root / "images", repo_root]
    image_dirs: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        for image_dir in clonezilla.list_clonezilla_image_dirs(candidate):
            if image_dir in seen:
                continue
            image_dirs.append(image_dir)
            seen.add(image_dir)

    # Also include ISO files from the repo root
    for iso_file in repo_root.glob("*.iso"):
        if iso_file.is_file() and iso_file not in seen:
            image_dirs.append(iso_file)
            seen.add(iso_file)

    return sorted(image_dirs, key=lambda path: path.name)
