"""Clonezilla-compatible backup operations.

This module creates Clonezilla-format disk images that are compatible with
the existing restore functionality. It generates the same directory structure,
file formats, and metadata that Clonezilla produces.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from rpi_usb_cloner.logging import get_logger
from rpi_usb_cloner.storage import devices
from rpi_usb_cloner.storage.clone import resolve_device_node

from .image_discovery import get_partclone_tool

log = get_logger(source=__name__)


@dataclass
class BackupResult:
    """Result of a backup operation."""
    image_dir: Path
    partitions_backed_up: list[str]
    total_bytes_written: int
    compression: str
    elapsed_seconds: float


@dataclass
class PartitionInfo:
    """Information about a partition to backup."""
    name: str  # e.g., "sda1"
    node: str  # e.g., "/dev/sda1"
    fstype: Optional[str]  # e.g., "ext4", "vfat", None
    size_bytes: int
    used_bytes: Optional[int]  # None if can't determine


def check_tool_available(tool: str) -> bool:
    """Check if a command-line tool is available."""
    return shutil.which(tool) is not None


def get_compression_tool(compression: str) -> tuple[Optional[str], Optional[list[str]]]:
    """Get the compression tool and arguments.

    Returns:
        (tool_path, arguments) or (None, None) if not available
    """
    if compression == "gzip":
        tool = shutil.which("pigz") or shutil.which("gzip")
        if tool:
            return tool, ["-c"]
        return None, None
    elif compression == "zstd":
        tool = shutil.which("pzstd") or shutil.which("zstd")
        if tool:
            return tool, ["-c"]
        return None, None
    elif compression == "none":
        return None, None
    else:
        raise ValueError(f"Unknown compression type: {compression}")


def get_filesystem_type(partition_node: str) -> Optional[str]:
    """Detect filesystem type of a partition.

    Returns:
        Filesystem type (e.g., "ext4", "vfat") or None if unknown
    """
    try:
        result = subprocess.run(
            ["lsblk", "-n", "-o", "FSTYPE", partition_node],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            fstype = result.stdout.strip()
            return fstype if fstype else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback to blkid
    try:
        result = subprocess.run(
            ["blkid", "-s", "TYPE", "-o", "value", partition_node],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            fstype = result.stdout.strip()
            return fstype if fstype else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def get_partition_used_space(partition_node: str, fstype: Optional[str]) -> Optional[int]:
    """Get used space on a partition in bytes.

    Returns:
        Used space in bytes, or None if can't determine
    """
    # Try to mount and check with df
    try:
        result = subprocess.run(
            ["df", "--output=used", "-B1", partition_node],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                try:
                    return int(lines[1])
                except ValueError:
                    pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def get_partition_info(device_info: dict) -> list[PartitionInfo]:
    """Get information about all partitions on a device.

    Args:
        device_info: Device info dict from devices.get_device_by_name()

    Returns:
        List of PartitionInfo objects
    """
    partitions = []
    children = devices.get_children(device_info)

    for child in children:
        if child.get("type") != "part":
            continue

        name = child.get("name", "")
        if not name:
            continue

        node = f"/dev/{name}"
        fstype = child.get("fstype")
        size_bytes = child.get("size", 0)

        # Try to get used space
        used_bytes = get_partition_used_space(node, fstype)

        partitions.append(PartitionInfo(
            name=name,
            node=node,
            fstype=fstype,
            size_bytes=int(size_bytes) if size_bytes else 0,
            used_bytes=used_bytes,
        ))

    return partitions


def estimate_backup_size(
    device_name: str,
    partition_names: Optional[list[str]] = None,
) -> int:
    """Estimate total backup size in bytes.

    Args:
        device_name: Device name (e.g., "sda")
        partition_names: List of partition names to backup, or None for all

    Returns:
        Estimated size in bytes
    """
    device_info = devices.get_device_by_name(device_name)
    if not device_info:
        raise RuntimeError(f"Device {device_name} not found")

    partitions = get_partition_info(device_info)

    if partition_names:
        partitions = [p for p in partitions if p.name in partition_names]

    total_size = 0
    for partition in partitions:
        if partition.used_bytes is not None:
            # Use used space + 10% overhead
            total_size += int(partition.used_bytes * 1.1)
        else:
            # Conservative: use full partition size
            total_size += partition.size_bytes

    # Add overhead for metadata
    total_size += 10 * 1024 * 1024  # 10MB for metadata files

    return total_size


def save_partition_table_sfdisk(device_node: str, output_path: Path) -> None:
    """Save partition table using sfdisk format.

    Args:
        device_node: Device node path (e.g., "/dev/sda")
        output_path: Output file path (e.g., "sda-pt.sf")
    """
    sfdisk = shutil.which("sfdisk")
    if not sfdisk:
        raise RuntimeError("sfdisk tool not found")

    result = subprocess.run(
        [sfdisk, "-d", device_node],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(f"sfdisk failed: {result.stderr}")

    output_path.write_text(result.stdout)


def save_partition_table_parted(device_node: str, output_path: Path) -> None:
    """Save partition table using parted format.

    Args:
        device_node: Device node path (e.g., "/dev/sda")
        output_path: Output file path (e.g., "sda-pt.parted")
    """
    parted = shutil.which("parted")
    if not parted:
        raise RuntimeError("parted tool not found")

    result = subprocess.run(
        [parted, "-m", "-s", device_node, "unit", "s", "print"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(f"parted failed: {result.stderr}")

    output_path.write_text(result.stdout)


def save_partition_table_sgdisk(device_node: str, output_path: Path) -> None:
    """Save partition table using sgdisk format (for GPT disks).

    Args:
        device_node: Device node path (e.g., "/dev/sda")
        output_path: Output file path (e.g., "sda-pt.sgdisk")
    """
    sgdisk = shutil.which("sgdisk")
    if not sgdisk:
        # sgdisk is optional, only needed for GPT disks
        return

    result = subprocess.run(
        [sgdisk, "-p", device_node],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        # Not a GPT disk, skip
        return

    output_path.write_text(result.stdout)


def save_partition_tables(device_node: str, device_name: str, output_dir: Path) -> None:
    """Save partition tables in all supported formats.

    Args:
        device_node: Device node path (e.g., "/dev/sda")
        device_name: Device name (e.g., "sda")
        output_dir: Output directory for partition table files
    """
    # Save sfdisk format (required)
    try:
        save_partition_table_sfdisk(device_node, output_dir / f"{device_name}-pt.sf")
    except Exception as e:
        log.error(f"Failed to save sfdisk partition table: {e}")
        raise RuntimeError(f"Failed to save partition table: {e}")

    # Save parted format (required)
    try:
        save_partition_table_parted(device_node, output_dir / f"{device_name}-pt.parted")
    except Exception as e:
        log.warning(f"Failed to save parted partition table: {e}")

    # Save sgdisk format (optional, only for GPT)
    try:
        save_partition_table_sgdisk(device_node, output_dir / f"{device_name}-pt.sgdisk")
    except Exception as e:
        log.debug(f"Failed to save sgdisk partition table: {e}")


def create_metadata_files(device_name: str, partitions: list[str], output_dir: Path) -> None:
    """Create Clonezilla metadata files (parts, disk).

    Args:
        device_name: Device name (e.g., "sda")
        partitions: List of partition names (e.g., ["sda1", "sda2"])
        output_dir: Output directory
    """
    # Create 'parts' file - space-separated list of partitions
    parts_content = " ".join(partitions)
    (output_dir / "parts").write_text(parts_content + "\n")

    # Create 'disk' file - just the device name
    (output_dir / "disk").write_text(device_name + "\n")


def parse_partclone_progress(line: str) -> Optional[dict]:
    """Parse partclone progress output.

    Partclone outputs progress to stderr in formats like:
    "Elapsed: 00:01:23, Rate: 45.2MB/s, Remaining: 00:05:30, 45.2% completed"

    Returns:
        dict with 'percentage', 'rate_str', 'bytes_str' or None
    """
    # Look for percentage
    percent_match = re.search(r'(\d+\.?\d*)%', line)
    if percent_match:
        percentage = float(percent_match.group(1))

        # Look for rate
        rate_match = re.search(r'Rate:\s*([\d.]+\s*[KMGT]?B/s)', line)
        rate_str = rate_match.group(1) if rate_match else None

        return {
            'percentage': percentage,
            'rate_str': rate_str,
            'bytes_str': None,
        }

    return None


def parse_dd_progress(line: str) -> Optional[dict]:
    """Parse dd progress output.

    DD outputs progress to stderr in format:
    "2415919104 bytes (2.4 GB, 2.2 GiB) copied, 45 s, 53.7 MB/s"

    Returns:
        dict with 'bytes', 'rate_str' or None
    """
    # Look for "bytes (size) copied"
    match = re.search(r'(\d+)\s+bytes\s+\(([\d.]+\s+[KMGT]?B)', line)
    if match:
        bytes_written = int(match.group(1))
        size_str = match.group(2)

        # Look for rate at the end
        rate_match = re.search(r'([\d.]+\s+[KMGT]?B/s)\s*$', line)
        rate_str = rate_match.group(1) if rate_match else None

        return {
            'bytes': bytes_written,
            'size_str': size_str,
            'rate_str': rate_str,
        }

    return None


def backup_partition(
    partition_info: PartitionInfo,
    output_dir: Path,
    compression: str = "gzip",
    split_size_mb: int = 4096,
    progress_callback: Optional[Callable[[list[str], Optional[float]], None]] = None,
) -> list[Path]:
    """Backup a single partition.

    Args:
        partition_info: Partition information
        output_dir: Output directory for image files
        compression: Compression type ("gzip", "zstd", or "none")
        split_size_mb: Volume split size in MB (0 = no splitting)
        progress_callback: Progress callback function

    Returns:
        List of created image file paths
    """
    partition_name = partition_info.name
    partition_node = partition_info.node
    fstype = partition_info.fstype

    # Determine backup tool
    use_partclone = False
    if fstype:
        partclone_tool = get_partclone_tool(fstype)
        if partclone_tool:
            use_partclone = True
            backup_command = [partclone_tool, "-c", "-s", partition_node]
        else:
            # Fallback to dd
            backup_command = ["dd", f"if={partition_node}", "bs=64K", "status=progress"]
    else:
        # No filesystem detected, use dd
        backup_command = ["dd", f"if={partition_node}", "bs=64K", "status=progress"]

    # Build output filename
    if use_partclone and fstype:
        base_name = f"{partition_name}.{fstype}-ptcl-img"
    else:
        base_name = f"{partition_name}.dd-img"

    # Add compression extension
    comp_ext = ""
    if compression == "gzip":
        comp_ext = ".gz"
    elif compression == "zstd":
        comp_ext = ".zst"

    output_base = output_dir / f"{base_name}{comp_ext}"

    # Build pipeline
    processes = []

    try:
        # Stage 1: Backup tool (partclone or dd)
        backup_proc = subprocess.Popen(
            backup_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append(backup_proc)
        upstream = backup_proc.stdout

        # Stage 2: Compression (optional)
        compress_proc = None
        if compression != "none":
            comp_tool, comp_args = get_compression_tool(compression)
            if not comp_tool:
                raise RuntimeError(f"Compression tool not available: {compression}")

            compress_proc = subprocess.Popen(
                [comp_tool] + comp_args,
                stdin=upstream,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            processes.append(compress_proc)
            upstream = compress_proc.stdout

        # Stage 3: Split (optional)
        split_proc = None
        output_files = []

        if split_size_mb > 0:
            split_suffix = "."
            output_files_pattern = str(output_base) + "."

            split_proc = subprocess.Popen(
                ["split", "-b", f"{split_size_mb}M", "-", output_files_pattern],
                stdin=upstream,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            processes.append(split_proc)
        else:
            # No splitting, write directly to file
            with open(output_base, "wb") as f:
                if upstream:
                    while True:
                        chunk = upstream.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
            output_files = [output_base]

        # Monitor progress
        total_size = partition_info.size_bytes
        last_update = time.time()

        if use_partclone:
            # Monitor partclone stderr for progress
            while backup_proc.poll() is None:
                if backup_proc.stderr:
                    line = backup_proc.stderr.readline()
                    if line:
                        line_str = line.decode('utf-8', errors='ignore').strip()
                        progress_data = parse_partclone_progress(line_str)

                        if progress_data and progress_callback:
                            percentage = progress_data.get('percentage', 0)
                            rate_str = progress_data.get('rate_str', '')

                            status_lines = [
                                f"Backing up {partition_name}",
                            ]
                            if rate_str:
                                status_lines.append(f"Rate: {rate_str}")

                            progress_callback(status_lines, percentage / 100.0)

                # Update at most every 0.5 seconds
                current_time = time.time()
                if current_time - last_update > 0.5:
                    last_update = current_time
                else:
                    time.sleep(0.1)
        else:
            # For dd, we can't easily track progress in real-time
            # Just show a generic progress message
            if progress_callback:
                progress_callback([f"Backing up {partition_name}", "Using dd..."], None)

            backup_proc.wait()

        # Wait for all processes to complete
        for proc in processes:
            proc.wait()

        # Check for errors
        if backup_proc.returncode != 0:
            stderr = backup_proc.stderr.read().decode('utf-8', errors='ignore') if backup_proc.stderr else ""
            raise RuntimeError(f"Backup failed: {stderr}")

        if compress_proc and compress_proc.returncode != 0:
            stderr = compress_proc.stderr.read().decode('utf-8', errors='ignore') if compress_proc.stderr else ""
            raise RuntimeError(f"Compression failed: {stderr}")

        if split_proc and split_proc.returncode != 0:
            stderr = split_proc.stderr.read().decode('utf-8', errors='ignore') if split_proc.stderr else ""
            raise RuntimeError(f"Split failed: {stderr}")

        # Find created files if we used split
        if split_size_mb > 0:
            output_files = sorted(output_dir.glob(f"{output_base.name}.*"))

        return output_files

    finally:
        # Clean up processes
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()


def create_clonezilla_backup(
    source_device: str,
    output_dir: Path,
    partitions: Optional[list[str]] = None,
    compression: str = "gzip",
    split_size_mb: int = 4096,
    progress_callback: Optional[Callable[[list[str], Optional[float]], None]] = None,
) -> BackupResult:
    """Create a Clonezilla-compatible backup image.

    Args:
        source_device: Source device name (e.g., "sda")
        output_dir: Output directory for the backup image
        partitions: List of partition names to backup (None = all)
        compression: Compression type ("gzip", "zstd", or "none")
        split_size_mb: Volume split size in MB (0 = no splitting)
        progress_callback: Progress callback function(lines, ratio)

    Returns:
        BackupResult with backup details
    """
    start_time = time.time()

    # Validate compression type
    if compression not in ("gzip", "zstd", "none"):
        raise ValueError(f"Invalid compression type: {compression}")

    # Check compression tool availability
    if compression != "none":
        comp_tool, _ = get_compression_tool(compression)
        if not comp_tool:
            raise RuntimeError(f"Compression tool not available: {compression}")

    # Get device info
    device_info = devices.get_device_by_name(source_device)
    if not device_info:
        raise RuntimeError(f"Device {source_device} not found")

    device_node = resolve_device_node(device_info)

    # Unmount all partitions
    if not devices.unmount_device(device_info):
        log.error("Failed to unmount device; aborting backup")
        raise RuntimeError("Failed to unmount device before backup")

    # Get partition information
    all_partitions = get_partition_info(device_info)

    if partitions:
        # Filter to requested partitions
        partitions_to_backup = [p for p in all_partitions if p.name in partitions]
        if len(partitions_to_backup) != len(partitions):
            found = {p.name for p in partitions_to_backup}
            missing = set(partitions) - found
            raise RuntimeError(f"Partitions not found: {', '.join(missing)}")
    else:
        # Backup all partitions
        partitions_to_backup = all_partitions

    if not partitions_to_backup:
        raise RuntimeError("No partitions to backup")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    total_bytes_written = 0

    try:
        # Step 1: Save partition tables
        if progress_callback:
            progress_callback(["Saving partition table..."], 0.0)

        save_partition_tables(device_node, source_device, output_dir)

        # Step 2: Create metadata files
        partition_names = [p.name for p in partitions_to_backup]
        create_metadata_files(source_device, partition_names, output_dir)

        # Step 3: Backup each partition
        num_partitions = len(partitions_to_backup)

        for idx, partition in enumerate(partitions_to_backup):
            # Calculate progress weight for this partition
            base_progress = idx / num_partitions
            partition_weight = 1.0 / num_partitions

            def partition_progress_callback(lines: list[str], ratio: Optional[float]) -> None:
                if progress_callback:
                    overall_ratio = base_progress
                    if ratio is not None:
                        overall_ratio += ratio * partition_weight
                    progress_callback(lines, overall_ratio)

            # Backup partition
            created_files = backup_partition(
                partition,
                output_dir,
                compression=compression,
                split_size_mb=split_size_mb,
                progress_callback=partition_progress_callback,
            )

            # Track total bytes written
            for file_path in created_files:
                if file_path.exists():
                    total_bytes_written += file_path.stat().st_size

        # Complete
        elapsed_seconds = time.time() - start_time

        return BackupResult(
            image_dir=output_dir,
            partitions_backed_up=partition_names,
            total_bytes_written=total_bytes_written,
            compression=compression,
            elapsed_seconds=elapsed_seconds,
        )

    except Exception as e:
        # Clean up partial backup
        log.error(f"Backup failed: {e}")
        cleanup_partial_backup(output_dir)
        raise


def cleanup_partial_backup(image_dir: Path) -> None:
    """Remove a partial/failed backup directory.

    Args:
        image_dir: Backup image directory to remove
    """
    if image_dir.exists() and image_dir.is_dir():
        try:
            shutil.rmtree(image_dir)
            log.info(f"Cleaned up partial backup: {image_dir}")
        except Exception as e:
            log.error(f"Failed to clean up partial backup {image_dir}: {e}")


def verify_backup_image(
    source_device: str,
    image_dir: Path,
    progress_callback: Optional[Callable[[list[str], Optional[float]], None]] = None,
) -> bool:
    """Verify a backup image by comparing checksums.

    This is the reverse of verify_restored_image - we compare the source
    device partitions against the backup image files.

    Args:
        source_device: Source device name (e.g., "sda")
        image_dir: Backup image directory
        progress_callback: Progress callback function

    Returns:
        True if verification succeeded, False otherwise
    """
    # Import here to avoid circular dependency
    from .verification import verify_restored_image
    from .image_discovery import load_image

    try:
        # Load the backup image
        image = load_image(image_dir)

        # Verify (source device acts as the "target" in verification)
        success = verify_restored_image(
            image,
            source_device,
            progress_callback=progress_callback,
        )

        return success

    except Exception as e:
        log.error(f"Verification failed: {e}")
        return False
