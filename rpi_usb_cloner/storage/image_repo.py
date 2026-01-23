from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

from rpi_usb_cloner.domain import DiskImage, ImageRepo, ImageType
from rpi_usb_cloner.storage import clonezilla, devices, mount

REPO_FLAG_FILENAME = ".rpi-usb-cloner-image-repo"
logger = logging.getLogger(__name__)


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


def find_image_repos(flag_filename: str = REPO_FLAG_FILENAME) -> list[ImageRepo]:
    """Find all USB partitions containing image repositories.

    An image repository is identified by a flag file (default: .rpi-usb-cloner-image-repo).

    Args:
        flag_filename: Name of the flag file to search for

    Returns:
        List of ImageRepo objects representing discovered repositories
    """
    repos: list[ImageRepo] = []
    seen: set[Path] = set()
    for device in devices.list_usb_disks():
        device_name = device.get("name")
        for partition in _iter_partitions(device):
            mountpoint = _resolve_mountpoint(partition)
            if not mountpoint:
                continue
            flag_path = mountpoint / flag_filename
            try:
                if not flag_path.exists():
                    continue
            except OSError as exc:
                logger.debug(
                    "Skipping image repo check for mountpoint %s: %s",
                    mountpoint,
                    exc,
                )
                continue
            if mountpoint in seen:
                continue
            # Create ImageRepo domain object
            repo = ImageRepo(path=mountpoint, drive_name=device_name)
            repos.append(repo)
            seen.add(mountpoint)
    return repos


def list_clonezilla_images(repo_root: Path) -> list[DiskImage]:
    """List all Clonezilla images and ISO files in a repository.

    Searches for Clonezilla image directories in common locations:
    - {repo_root}/clonezilla/
    - {repo_root}/images/
    - {repo_root}/

    Also includes ISO files found in the repository root.

    Args:
        repo_root: Root path of the image repository

    Returns:
        List of DiskImage objects sorted by name
    """
    candidates = [repo_root / "clonezilla", repo_root / "images", repo_root]
    images: list[DiskImage] = []
    seen: set[Path] = set()

    # Search for Clonezilla image directories
    for candidate in candidates:
        for image_dir in clonezilla.list_clonezilla_image_dirs(candidate):
            if image_dir in seen:
                continue
            # Create DiskImage domain object for Clonezilla directory
            image = DiskImage(
                name=image_dir.name,
                path=image_dir,
                image_type=ImageType.CLONEZILLA_DIR,
            )
            images.append(image)
            seen.add(image_dir)

    # Also include ISO files from the repo root
    for iso_file in repo_root.glob("*.iso"):
        if iso_file.is_file() and iso_file not in seen:
            # Create DiskImage domain object for ISO file
            try:
                size_bytes = iso_file.stat().st_size
            except OSError:
                size_bytes = None

            image = DiskImage(
                name=iso_file.name,
                path=iso_file,
                image_type=ImageType.ISO,
                size_bytes=size_bytes,
            )
            images.append(image)
            seen.add(iso_file)

    return sorted(images, key=lambda img: img.name)
