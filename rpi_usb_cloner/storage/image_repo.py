from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from rpi_usb_cloner.domain import DiskImage, ImageRepo, ImageType
from loguru import logger

from rpi_usb_cloner.storage import clonezilla, devices, imageusb, mount
from rpi_usb_cloner.storage.imageusb.detection import get_imageusb_metadata


REPO_FLAG_FILENAME = ".rpi-usb-cloner-image-repo"


def _iter_partitions(device: dict) -> Iterable[dict]:
    stack = list(devices.get_children(device))
    while stack:
        child = stack.pop()
        if child.get("type") == "part":
            yield child
        stack.extend(devices.get_children(child))


def _resolve_mountpoint(partition: dict) -> Path | None:
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
    except (ValueError, RuntimeError):
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
                    f"Skipping image repo check for mountpoint {mountpoint}: {exc}",
                    mountpoint=str(mountpoint),
                    error=str(exc),
                    tags=["image", "repo"],
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
    """List all Clonezilla images, ISO files, and ImageUSB .BIN files in a repository.

    Searches for Clonezilla image directories in common locations:
    - {repo_root}/clonezilla/
    - {repo_root}/images/
    - {repo_root}/

    Also includes ISO files and ImageUSB .BIN files found in the repository root.

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

    # Also include ImageUSB .BIN files from the repo root
    for bin_file in repo_root.glob("*.bin"):
        if (
            bin_file.is_file()
            and bin_file not in seen
            and imageusb.is_imageusb_file(bin_file)
        ):
            # Create DiskImage domain object for ImageUSB .BIN file
            try:
                size_bytes = bin_file.stat().st_size
            except OSError:
                size_bytes = None

            image = DiskImage(
                name=bin_file.name,
                path=bin_file,
                image_type=ImageType.IMAGEUSB_BIN,
                size_bytes=size_bytes,
            )
            images.append(image)
            seen.add(bin_file)

    return sorted(images, key=lambda img: img.name)


def _iter_clonezilla_image_dirs(repo_root: Path) -> Iterable[Path]:
    candidates = [repo_root / "clonezilla", repo_root / "images", repo_root]
    seen: set[Path] = set()
    for candidate in candidates:
        for image_dir in clonezilla.list_clonezilla_image_dirs(candidate):
            if image_dir in seen:
                continue
            seen.add(image_dir)
            yield image_dir


def _is_temp_clonezilla_path(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered.startswith("."):
        return True
    if lowered.endswith((".tmp", ".part", ".partial", ".swp", ".swx")):
        return True
    return any(part.lower() in {"tmp", "temp"} for part in path.parts)


def _sum_tree_bytes(root: Path) -> int:
    total = 0
    try:
        paths = root.rglob("*")
    except OSError:
        return 0
    for path in paths:
        if _is_temp_clonezilla_path(path):
            continue
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def get_image_size_bytes(image: DiskImage) -> int | None:
    """Return size for a disk image, computing Clonezilla directory sizes."""
    if image.size_bytes is not None:
        return image.size_bytes
    if image.image_type == ImageType.CLONEZILLA_DIR:
        return _sum_tree_bytes(image.path)
    return None


def _get_repo_space_bytes(repo_root: Path) -> tuple[int, int, int]:
    try:
        stats = os.statvfs(repo_root)
    except OSError:
        return 0, 0, 0
    total_bytes = stats.f_frsize * stats.f_blocks
    free_bytes = stats.f_frsize * stats.f_bavail
    used_bytes = max(0, total_bytes - free_bytes)
    return total_bytes, used_bytes, free_bytes


def get_repo_usage(repo: ImageRepo) -> dict[str, dict[str, int] | int]:
    """Compute repository usage statistics and image size aggregates."""
    total_bytes, used_bytes, free_bytes = _get_repo_space_bytes(repo.path)

    clonezilla_bytes = 0
    for image_dir in _iter_clonezilla_image_dirs(repo.path):
        clonezilla_bytes += _sum_tree_bytes(image_dir)

    iso_bytes = 0
    for iso_file in repo.path.glob("*.iso"):
        try:
            if iso_file.is_file() and not iso_file.is_symlink():
                iso_bytes += iso_file.stat().st_size
        except OSError:
            continue

    imageusb_bytes = 0
    for bin_file in repo.path.glob("*.bin"):
        if not bin_file.is_file() or bin_file.is_symlink():
            continue
        if not imageusb.is_imageusb_file(bin_file):
            continue
        metadata = get_imageusb_metadata(bin_file)
        size_bytes = metadata.get("data_size_bytes") or metadata.get("size_bytes") or 0
        imageusb_bytes += max(0, int(size_bytes))

    other_bytes = max(0, used_bytes - (clonezilla_bytes + iso_bytes + imageusb_bytes))

    return {
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "type_bytes": {
            "clonezilla": clonezilla_bytes,
            "iso": iso_bytes,
            "imageusb": imageusb_bytes,
            "other": other_bytes,
        },
    }
