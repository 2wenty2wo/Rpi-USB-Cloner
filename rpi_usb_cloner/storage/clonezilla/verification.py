"""SHA256 verification for Clonezilla image restoration."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from rpi_usb_cloner.config import settings
from rpi_usb_cloner.storage import devices
from rpi_usb_cloner.storage.clone import get_partition_number

from .compression import get_compression_type
from .file_utils import sorted_clonezilla_volumes
from .models import RestorePlan


def get_verify_hash_timeout(setting_key: str) -> float | None:
    """Get timeout value for hash verification from settings."""
    value = settings.get_setting(setting_key)
    if value is None:
        return None
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return None
    if timeout <= 0:
        return None
    return timeout


def compute_image_sha256(image_files: list[Path], compressed: bool) -> str:
    """Compute SHA256 of image files (decompressing if needed)."""
    if not image_files:
        raise RuntimeError("No image files")

    image_files = sorted_clonezilla_volumes(image_files)

    # Start with cat to concatenate all volume files
    cat_proc = subprocess.Popen(
        ["cat", *[str(path) for path in image_files]],
        stdout=subprocess.PIPE,
    )
    upstream = cat_proc.stdout

    decompress_proc = None
    if compressed:
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
        raise RuntimeError("Failed to create image stream")

    # Pipe to sha256sum
    sha256_path = shutil.which("sha256sum")
    if not sha256_path:
        raise RuntimeError("sha256sum not found")

    sha_proc = subprocess.Popen(
        [sha256_path],
        stdin=upstream,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Close upstream in parent process - close both file descriptors
    if cat_proc.stdout:
        cat_proc.stdout.close()
    if decompress_proc and decompress_proc.stdout:
        decompress_proc.stdout.close()

    timeout = get_verify_hash_timeout("verify_image_hash_timeout_seconds")
    try:
        sha_out, sha_err = sha_proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        sha_proc.kill()
        if decompress_proc:
            decompress_proc.kill()
        cat_proc.kill()
        sha_proc.wait()
        if decompress_proc:
            decompress_proc.wait()
        cat_proc.wait()
        raise RuntimeError(f"Image hash computation timed out after {timeout} seconds")

    # Wait for all processes
    cat_proc.wait()
    if decompress_proc:
        decompress_proc.wait()

    if sha_proc.returncode != 0:
        raise RuntimeError(f"sha256sum failed: {sha_err}")
    if cat_proc.returncode != 0:
        raise RuntimeError("cat failed")
    if decompress_proc and decompress_proc.returncode != 0:
        raise RuntimeError("decompression failed")

    checksum = sha_out.split()[0] if sha_out else ""
    if not checksum:
        raise RuntimeError("No checksum returned")

    return checksum


def compute_partition_sha256(partition_path: str) -> str:
    """Compute SHA256 of a partition."""
    dd_path = shutil.which("dd")
    sha256_path = shutil.which("sha256sum")
    if not dd_path or not sha256_path:
        raise RuntimeError("dd or sha256sum not found")

    dd_proc = subprocess.Popen(
        [dd_path, f"if={partition_path}", "bs=4M", "status=none"],
        stdout=subprocess.PIPE,
    )

    sha_proc = subprocess.Popen(
        [sha256_path],
        stdin=dd_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if dd_proc.stdout:
        dd_proc.stdout.close()

    timeout = get_verify_hash_timeout("verify_partition_hash_timeout_seconds")
    try:
        sha_out, sha_err = sha_proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        sha_proc.kill()
        dd_proc.kill()
        sha_proc.wait()
        dd_proc.wait()
        raise RuntimeError(f"Partition hash computation timed out after {timeout} seconds")

    dd_proc.wait()

    if sha_proc.returncode != 0:
        raise RuntimeError(f"sha256sum failed: {sha_err}")
    if dd_proc.returncode != 0:
        raise RuntimeError("dd failed")

    checksum = sha_out.split()[0] if sha_out else ""
    if not checksum:
        raise RuntimeError("No checksum returned")

    return checksum


def verify_restored_image(
    plan: RestorePlan,
    target_device: str,
    *,
    progress_callback: Optional[Callable[[list[str], Optional[float]], None]] = None,
) -> bool:
    """Verify that restored partitions match the source image using SHA256 checksums.

    Args:
        plan: The restore plan containing image information
        target_device: The target device name (e.g., "sda")
        progress_callback: Optional callback for progress updates

    Returns:
        True if verification succeeds, False otherwise
    """
    sha256_path = shutil.which("sha256sum")
    if not sha256_path:
        if progress_callback:
            progress_callback(["sha256sum", "not found"], None)
        return False

    target_dev = devices.get_device_by_name(target_device)
    if not target_dev:
        if progress_callback:
            progress_callback(["Target device", "not found"], None)
        return False

    # Unmount target device and all partitions before verification
    # This prevents dd from blocking when trying to read mounted partitions
    if not devices.unmount_device(target_dev):
        if progress_callback:
            progress_callback(["Unmount failed", "Target busy"], None)
        return False

    target_parts = [
        child for child in devices.get_children(target_dev)
        if child.get("type") == "part"
    ]

    total_parts = len(plan.partition_ops)
    for index, op in enumerate(plan.partition_ops, start=1):
        part_num = get_partition_number(op.partition)
        if part_num is None:
            if progress_callback:
                progress_callback([f"V {index}/{total_parts}", "Invalid partition"], None)
            return False

        target_part = None
        for tp in target_parts:
            tp_num = get_partition_number(tp.get("name", ""))
            if tp_num == part_num:
                target_part = f"/dev/{tp.get('name')}"
                break

        if not target_part:
            if progress_callback:
                progress_callback([f"V {index}/{total_parts}", "Partition missing"], None)
            return False

        if progress_callback:
            progress_callback([f"V {index}/{total_parts} IMG", op.partition],
                            (index - 0.5) / total_parts)

        # Compute SHA256 of the image file(s)
        try:
            image_hash = compute_image_sha256(op.image_files, op.compressed)
        except Exception as e:
            if progress_callback:
                progress_callback([f"V {index}/{total_parts}", "Image hash error"], None)
            return False

        if progress_callback:
            progress_callback([f"V {index}/{total_parts} DST", op.partition],
                            (index - 0.25) / total_parts)

        # Compute SHA256 of the target partition
        try:
            target_hash = compute_partition_sha256(target_part)
        except Exception as e:
            if progress_callback:
                progress_callback([f"V {index}/{total_parts}", "Target hash error"], None)
            return False

        if image_hash != target_hash:
            if progress_callback:
                progress_callback([f"V {index}/{total_parts}", f"Mismatch {op.partition}"], None)
            return False

    if progress_callback:
        progress_callback(["VERIFY", "Complete"], 1.0)

    return True
