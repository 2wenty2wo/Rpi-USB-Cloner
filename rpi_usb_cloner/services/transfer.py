"""Image transfer service for copying images between repositories.

This module provides functionality for transferring disk images between
image repositories, primarily for USB-to-USB transfers.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from rpi_usb_cloner.domain import DiskImage, ImageRepo, ImageType
from rpi_usb_cloner.logging import get_logger
from rpi_usb_cloner.storage import image_repo

log = get_logger(source=__name__)


def find_destination_repos(exclude_drive: str | None = None) -> list[ImageRepo]:
    """Find image repositories, optionally excluding a specific drive.
    
    Args:
        exclude_drive: Drive name to exclude (e.g., "sda"). If None, returns all repos.
        
    Returns:
        List of ImageRepo objects, excluding the specified drive if provided.
    """
    all_repos = image_repo.find_image_repos()
    
    if exclude_drive is None:
        return all_repos
    
    return [repo for repo in all_repos if repo.drive_name != exclude_drive]


def estimate_transfer_size(images: list[DiskImage]) -> int:
    """Calculate total bytes to transfer for a list of images.
    
    Args:
        images: List of DiskImage objects to transfer
        
    Returns:
        Total size in bytes. Returns 0 if size cannot be determined.
    """
    total = 0
    for img in images:
        size = image_repo.get_image_size_bytes(img)
        if size is not None:
            total += size
    return total


def copy_images_to_repo(
    images: list[DiskImage],
    destination: ImageRepo,
    progress_callback: Callable[[str, float], None] | None = None,
) -> tuple[int, int]:
    """Copy multiple disk images to a destination repository.
    
    Args:
        images: List of DiskImage objects to copy
        destination: Target ImageRepo to copy images to
        progress_callback: Optional callback(image_name, progress_ratio) called during copy.
                          progress_ratio is 0.0 to 1.0 per image.
        
    Returns:
        Tuple of (success_count, failure_count)
        
    Raises:
        OSError: If destination path is not writable or doesn't exist
    """
    if not destination.path.exists():
        raise OSError(f"Destination path does not exist: {destination.path}")
    
    if not destination.path.is_dir():
        raise OSError(f"Destination path is not a directory: {destination.path}")
    
    success_count = 0
    failure_count = 0
    
    for img in images:
        try:
            _copy_single_image(img, destination, progress_callback)
            success_count += 1
            log.info(f"Successfully copied image: {img.name}")
        except Exception as e:
            failure_count += 1
            log.error(f"Failed to copy image {img.name}: {e}")
    
    return success_count, failure_count


def _copy_single_image(
    image: DiskImage,
    destination: ImageRepo,
    progress_callback: Callable[[str, float], None] | None = None,
) -> None:
    """Copy a single image to destination repository.
    
    Args:
        image: DiskImage to copy
        destination: Target ImageRepo
        progress_callback: Optional callback for progress updates
        
    Raises:
        ValueError: If image type is unsupported
        OSError: If copy operation fails
    """
    if progress_callback:
        progress_callback(image.name, 0.0)
    
    dest_path = destination.path
    
    # Determine destination subdirectory based on image type
    if image.image_type == ImageType.CLONEZILLA_DIR:
        # Copy to clonezilla/ subdirectory
        dest_subdir = dest_path / "clonezilla"
        dest_subdir.mkdir(exist_ok=True)
        dest_image_path = dest_subdir / image.name
        
        log.info(f"Copying Clonezilla directory {image.name} to {dest_image_path}")
        _copy_directory_with_progress(
            image.path, dest_image_path, image.name, progress_callback
        )
        
    elif image.image_type == ImageType.ISO:
        # Copy ISO to root of repo
        dest_image_path = dest_path / image.name
        
        log.info(f"Copying ISO {image.name} to {dest_image_path}")
        _copy_file_with_progress(
            image.path, dest_image_path, image.name, progress_callback
        )
        
    elif image.image_type == ImageType.IMAGEUSB_BIN:
        # Copy .BIN to root of repo
        dest_image_path = dest_path / image.name
        
        log.info(f"Copying ImageUSB .BIN {image.name} to {dest_image_path}")
        _copy_file_with_progress(
            image.path, dest_image_path, image.name, progress_callback
        )
        
    else:
        raise ValueError(f"Unsupported image type: {image.image_type}")
    
    if progress_callback:
        progress_callback(image.name, 1.0)


def _copy_file_with_progress(
    src: Path,
    dest: Path,
    image_name: str,
    progress_callback: Callable[[str, float], None] | None,
) -> None:
    """Copy a single file with progress reporting.
    
    Args:
        src: Source file path
        dest: Destination file path
        image_name: Name for progress reporting
        progress_callback: Optional callback for progress updates
    """
    if dest.exists():
        log.warning(f"Destination file exists, will be overwritten: {dest}")
    
    file_size = src.stat().st_size
    
    if file_size == 0 or progress_callback is None:
        # Just copy directly if no progress needed or file is empty
        shutil.copy2(src, dest)
        return
    
    # Copy with progress tracking
    bytes_copied = 0
    chunk_size = 1024 * 1024  # 1MB chunks
    
    with open(src, "rb") as src_file, open(dest, "wb") as dest_file:
        while True:
            chunk = src_file.read(chunk_size)
            if not chunk:
                break
            dest_file.write(chunk)
            bytes_copied += len(chunk)
            
            # Report progress
            progress = bytes_copied / file_size
            progress_callback(image_name, progress)
    
    # Copy metadata (timestamps, permissions)
    shutil.copystat(src, dest)


def _copy_directory_with_progress(
    src: Path,
    dest: Path,
    image_name: str,
    progress_callback: Callable[[str, float], None] | None,
) -> None:
    """Copy a directory tree with progress reporting.
    
    Args:
        src: Source directory path
        dest: Destination directory path
        image_name: Name for progress reporting
        progress_callback: Optional callback for progress updates
    """
    if dest.exists():
        log.warning(f"Destination directory exists, merging: {dest}")
    
    # Calculate total size for progress tracking
    total_size = 0
    file_list = []
    
    for root, _, files in src.walk():
        for file in files:
            file_path = root / file
            try:
                size = file_path.stat().st_size
                total_size += size
                file_list.append((file_path, size))
            except OSError as e:
                log.warning(f"Could not stat file {file_path}: {e}")
    
    if total_size == 0:
        # Empty directory or all files errored
        dest.mkdir(parents=True, exist_ok=True)
        return
    
    # Copy files with progress tracking
    bytes_copied = 0
    
    for file_path, file_size in file_list:
        # Calculate relative path and destination
        rel_path = file_path.relative_to(src)
        dest_file = dest / rel_path
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            shutil.copy2(file_path, dest_file)
            bytes_copied += file_size
            
            # Report progress
            if progress_callback and total_size > 0:
                progress = bytes_copied / total_size
                progress_callback(image_name, progress)
                
        except OSError as e:
            log.error(f"Failed to copy {file_path} to {dest_file}: {e}")
            raise
