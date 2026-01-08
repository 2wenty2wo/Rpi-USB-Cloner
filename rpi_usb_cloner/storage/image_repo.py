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
    mount.mount_partition(partition_node, name=name)
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


def list_repo_device_names(flag_filename: str = REPO_FLAG_FILENAME) -> set[str]:
    repo_devices: set[str] = set()
    for device in devices.list_usb_disks():
        device_name = device.get("name")
        if not device_name:
            continue
        for partition in _iter_partitions(device):
            mountpoint = _resolve_mountpoint(partition)
            if not mountpoint:
                continue
            if (mountpoint / flag_filename).exists():
                repo_devices.add(device_name)
                break
    return repo_devices


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
    return sorted(image_dirs, key=lambda path: path.name)
