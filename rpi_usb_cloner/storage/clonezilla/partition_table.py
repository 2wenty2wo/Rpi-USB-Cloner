"""Partition table operations for Clonezilla restoration.

This module handles partition table manipulation including:
- Reading and parsing partition tables (sfdisk, parted, sgdisk formats)
- Scaling partition tables for different disk sizes
- Applying partition tables to target devices
"""
from __future__ import annotations

import logging
import re
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Optional

from rpi_usb_cloner.storage import devices

from .models import DiskLayoutOp

logger = logging.getLogger(__name__)


def collect_disk_layout_ops(image_dir: Path, *, select: bool = True) -> list[DiskLayoutOp]:
    """Collect all disk layout operations from a Clonezilla image directory."""
    disk_layout_ops: list[DiskLayoutOp] = []

    for name, kind in (("disk", "disk"), ("sfdisk", "sfdisk")):
        path = image_dir / name
        if path.exists():
            disk_layout_ops.append(read_disk_layout_op(kind, path))

    for path in sorted(image_dir.glob("*-pt.parted.compact")):
        disk_layout_ops.append(read_disk_layout_op("pt.parted.compact", path))
    for path in sorted(image_dir.glob("*-pt.sf")):
        disk_layout_ops.append(read_disk_layout_op("pt.sf", path))
    for path in sorted(image_dir.glob("*-chs.sf")):
        disk_layout_ops.append(read_disk_layout_op("chs.sf", path))
    for path in sorted(image_dir.glob("*-pt.parted")):
        disk_layout_ops.append(read_disk_layout_op("pt.parted", path))
    for path in sorted(image_dir.glob("*-pt.sgdisk")):
        disk_layout_ops.append(read_disk_layout_op("pt.sgdisk", path))
    for path in sorted(image_dir.glob("*-mbr")):
        disk_layout_ops.append(read_disk_layout_op("mbr", path))
    for path in sorted(image_dir.glob("*-hidden-data-after-mbr")):
        disk_layout_ops.append(read_disk_layout_op("hidden-data-after-mbr", path))
    for path in sorted(image_dir.glob("*-gpt")):
        disk_layout_ops.append(read_disk_layout_op("gpt", path))

    if select:
        return select_disk_layout_ops(disk_layout_ops)
    return disk_layout_ops


def select_disk_layout_ops(disk_layout_ops: list[DiskLayoutOp]) -> list[DiskLayoutOp]:
    """Select and prioritize disk layout operations."""
    if not disk_layout_ops:
        return []
    priority = [
        "pt.sgdisk",
        "gpt",
        "pt.parted",
        "pt.parted.compact",
        "pt.sf",
        "chs.sf",
        "mbr",
        "hidden-data-after-mbr",
        "sfdisk",
        "disk",
    ]
    priority_index = {kind: index for index, kind in enumerate(priority)}
    return sorted(
        disk_layout_ops,
        key=lambda op: priority_index.get(op.kind, len(priority)),
    )


def read_disk_layout_op(kind: str, path: Path) -> DiskLayoutOp:
    """Read a disk layout operation from a file."""
    data = path.read_bytes()
    size_bytes = len(data)
    contents: Optional[str]
    if b"\x00" in data[:1024]:
        contents = None
    else:
        contents = data.decode("utf-8", errors="replace")
    return DiskLayoutOp(kind=kind, path=path, contents=contents, size_bytes=size_bytes)


def estimate_required_size_bytes(
    disk_layout_ops: list[DiskLayoutOp],
    *,
    image_dir: Optional[Path] = None,
) -> Optional[int]:
    """Estimate the minimum disk size required for restoration."""
    ops = list(disk_layout_ops)
    if image_dir:
        extra_ops = collect_disk_layout_ops(image_dir, select=False)
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
                max_lba = estimate_last_lba_from_sgdisk_backup(op.path)
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


def estimate_last_lba_from_sgdisk_backup(path: Path) -> Optional[int]:
    """Extract the last LBA from an sgdisk backup file."""
    data = path.read_bytes()
    signature = b"EFI PART"
    offset = data.find(signature)
    if offset == -1 or len(data) < offset + 56:
        return None
    current_lba = struct.unpack_from("<Q", data, offset + 24)[0]
    backup_lba = struct.unpack_from("<Q", data, offset + 32)[0]
    last_usable = struct.unpack_from("<Q", data, offset + 48)[0]
    return max(current_lba, backup_lba, last_usable)


def normalize_partition_mode(partition_mode: Optional[str]) -> str:
    """Normalize partition mode string."""
    if not partition_mode:
        return "k0"
    normalized = str(partition_mode).strip().lower()
    if normalized.startswith("-"):
        normalized = normalized[1:]
    return normalized


def build_partition_mode_layout_ops(
    disk_layout_ops: list[DiskLayoutOp],
    *,
    partition_mode: str,
    target_size: Optional[int],
) -> list[DiskLayoutOp]:
    """Build layout operations based on partition mode."""
    if partition_mode not in {"k0", "k", "k1", "k2"}:
        raise RuntimeError(f"Unsupported partition mode: {partition_mode}")
    if partition_mode in {"k", "k2"}:
        return []
    if partition_mode == "k1" and target_size:
        scaled = build_scaled_sfdisk_layout(disk_layout_ops, target_size)
        if scaled:
            return [scaled]
    return list(disk_layout_ops)


def build_scaled_sfdisk_layout(
    disk_layout_ops: list[DiskLayoutOp],
    target_size: int,
) -> Optional[DiskLayoutOp]:
    """Build a scaled sfdisk layout for the target size."""
    for op in disk_layout_ops:
        if op.kind in {"disk", "sfdisk", "pt.sf"}:
            scaled = scale_sfdisk_layout(op, target_size)
            if scaled:
                return scaled
        if op.kind == "pt.parted":
            scaled = scale_parted_layout(op, target_size)
            if scaled:
                return scaled
    return None


def parse_sfdisk_fields(rest: str) -> list[tuple[str, str]]:
    """Parse sfdisk field entries."""
    fields: list[tuple[str, str]] = []
    for entry in rest.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" in entry:
            key, value = entry.split("=", 1)
            fields.append((key.strip(), value.strip()))
        else:
            fields.append((entry, ""))
    return fields


def get_sfdisk_int_field(fields: list[tuple[str, str]], key: str) -> Optional[int]:
    """Extract an integer field value from sfdisk fields."""
    for field_key, value in fields:
        if field_key != key:
            continue
        match = re.match(r"^(\d+)s?$", value)
        if match:
            return int(match.group(1))
    return None


def set_sfdisk_field(fields: list[tuple[str, str]], key: str, value: str) -> list[tuple[str, str]]:
    """Update or add a field in sfdisk field list."""
    updated = []
    found = False
    for field_key, field_value in fields:
        if field_key == key:
            updated.append((field_key, value))
            found = True
        else:
            updated.append((field_key, field_value))
    if not found:
        updated.append((key, value))
    return updated


def format_sfdisk_line(prefix: str, fields: list[tuple[str, str]]) -> str:
    """Format an sfdisk line from prefix and fields."""
    rendered = []
    for key, value in fields:
        if value:
            rendered.append(f"{key}={value}")
        else:
            rendered.append(key)
    return f"{prefix} : {', '.join(rendered)}"


def scale_sfdisk_layout(op: DiskLayoutOp, target_size: int) -> Optional[DiskLayoutOp]:
    """Scale an sfdisk partition table to fit target size."""
    if op.kind not in {"disk", "sfdisk", "pt.sf"} or not op.contents:
        return None

    lines = op.contents.splitlines()
    sector_size = 512
    partitions: list[dict[str, int | str]] = []
    last_lba_index = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("sector-size:"):
            match = re.search(r"sector-size:\s*(\d+)", stripped)
            if match:
                sector_size = int(match.group(1))
            continue
        if stripped.startswith("last-lba:"):
            last_lba_index = index
            continue
        if not stripped.startswith("/dev/") or ":" not in stripped:
            continue

        prefix, rest = stripped.split(":", 1)
        fields = parse_sfdisk_fields(rest)
        start = get_sfdisk_int_field(fields, "start")
        size = get_sfdisk_int_field(fields, "size")
        if start is None or size is None or size <= 0:
            continue

        partitions.append(
            {
                "index": index,
                "prefix": prefix.strip(),
                "fields": fields,
                "start": start,
                "size": size,
            }
        )

    if not partitions:
        return None

    target_sectors = target_size // sector_size
    scaled = scale_partition_geometry(
        partitions,
        target_sectors=target_sectors,
        sector_size=sector_size,
        layout_label="sfdisk",
    )
    if not scaled:
        return None

    for part in scaled:
        part["fields"] = set_sfdisk_field(part["fields"], "start", str(part["new_start"]))
        part["fields"] = set_sfdisk_field(part["fields"], "size", str(part["new_size"]))
        lines[part["index"]] = format_sfdisk_line(part["prefix"], part["fields"])

    if last_lba_index is not None:
        lines[last_lba_index] = f"last-lba: {target_sectors - 1}"

    return DiskLayoutOp(kind="sfdisk", path=op.path, contents="\n".join(lines), size_bytes=op.size_bytes)


def parse_parted_sector(value: str, unit_is_sectors: bool) -> Optional[int]:
    """Parse a parted sector value."""
    match = re.match(r"(\d+)(s)?$", value)
    if not match:
        return None
    if match.group(2) or unit_is_sectors:
        return int(match.group(1))
    return None


def parse_parted_layout(contents: str) -> Optional[tuple[int, Optional[str], list[dict[str, int | str | list[str]]]]]:
    """Parse a parted partition table layout."""
    sector_size = 512
    label: Optional[str] = None
    script_partitions: list[dict[str, int | str | list[str]]] = []
    print_partitions: list[dict[str, int | str | list[str]]] = []
    unit_is_sectors = False

    for line in contents.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "Sector size" in stripped:
            match = re.search(r"Sector size .*?:\s*(\d+)B", stripped)
            if match:
                sector_size = int(match.group(1))
        if stripped.startswith("Partition Table:"):
            label = stripped.split(":", 1)[1].strip()
        if stripped.startswith("unit "):
            unit_is_sectors = stripped.split()[-1] == "s"
        if stripped.startswith("mklabel"):
            parts = stripped.split()
            if len(parts) >= 2:
                label = parts[1].strip()
        if stripped.startswith("mkpart"):
            match = re.search(r"(\d+)s\s+(\d+)s", stripped)
            if match:
                start = int(match.group(1))
                end = int(match.group(2))
                size = end - start + 1
                if size > 0:
                    script_partitions.append(
                        {
                            "number": len(script_partitions) + 1,
                            "start": start,
                            "size": size,
                            "flags": [],
                            "fstype": None,
                        }
                    )

    for line in contents.splitlines():
        stripped = line.strip()
        if not stripped or not stripped[:1].isdigit():
            continue
        columns = re.split(r"\s+", stripped)
        if len(columns) < 4 or not columns[0].isdigit():
            continue
        start = parse_parted_sector(columns[1], unit_is_sectors)
        end = parse_parted_sector(columns[2], unit_is_sectors)
        if start is None or end is None:
            continue
        size = end - start + 1
        if size <= 0:
            continue
        number = int(columns[0])
        fstype = None
        flags: list[str] = []
        for column in columns[4:]:
            if "," in column:
                flags.extend(flag.strip() for flag in column.split(",") if flag.strip())
            elif column in {"boot", "esp", "bios_grub", "legacy_boot"}:
                flags.append(column)
            elif fstype is None:
                fstype = column
        print_partitions.append(
            {
                "number": number,
                "start": start,
                "size": size,
                "flags": flags,
                "fstype": fstype,
            }
        )

    partitions = print_partitions or script_partitions
    if not partitions:
        return None
    return sector_size, label, partitions


def normalize_parted_label(label: Optional[str]) -> Optional[str]:
    """Normalize a parted partition table label."""
    if not label:
        return None
    label = label.strip().lower()
    if label in {"msdos", "mbr"}:
        return "dos"
    if label in {"gpt", "dos"}:
        return label
    return None


def build_sfdisk_script_from_parted(
    *,
    label: Optional[str],
    sector_size: int,
    partitions: list[dict[str, int | str | list[str]]],
) -> Optional[str]:
    """Convert a parted layout to sfdisk script format."""
    normalized_label = normalize_parted_label(label)
    if not normalized_label:
        return None

    lines = [
        f"label: {normalized_label}",
        "unit: sectors",
    ]
    if sector_size:
        lines.append(f"sector-size: {sector_size}")

    for index, part in enumerate(sorted(partitions, key=lambda item: int(item["start"]))):
        start = int(part["new_start"])
        size = int(part["new_size"])
        fields: list[tuple[str, str]] = [
            ("start", str(start)),
            ("size", str(size)),
        ]
        flags = [flag.lower() for flag in part.get("flags") or []]
        fstype = str(part.get("fstype") or "").lower()
        if normalized_label == "gpt" and ("esp" in flags or (fstype == "fat32" and "boot" in flags)):
            fields.append(("type", "EF00"))
        if normalized_label == "dos" and "boot" in flags:
            fields.append(("bootable", ""))
        part_number = int(part.get("number") or index + 1)
        prefix = f"/dev/sda{part_number}"
        lines.append(format_sfdisk_line(prefix, fields))

    return "\n".join(lines)


def scale_parted_layout(op: DiskLayoutOp, target_size: int) -> Optional[DiskLayoutOp]:
    """Scale a parted partition table to fit target size."""
    if op.kind != "pt.parted" or not op.contents:
        return None
    layout = parse_parted_layout(op.contents)
    if not layout:
        return None
    sector_size, label, partitions = layout
    target_sectors = target_size // sector_size
    scaled = scale_partition_geometry(
        partitions,
        target_sectors=target_sectors,
        sector_size=sector_size,
        layout_label="parted",
    )
    if not scaled:
        return None
    sfdisk_contents = build_sfdisk_script_from_parted(
        label=label,
        sector_size=sector_size,
        partitions=scaled,
    )
    if not sfdisk_contents:
        return None
    return DiskLayoutOp(kind="sfdisk", path=op.path, contents=sfdisk_contents, size_bytes=op.size_bytes)


def scale_partition_geometry(
    partitions: list[dict[str, int | str | list[str]]],
    *,
    target_sectors: int,
    sector_size: int,
    layout_label: str,
) -> Optional[list[dict[str, int | str | list[str]]]]:
    """Scale partition geometry to fit target disk size.

    Implements proportional scaling while maintaining alignment and gaps.
    """
    if not partitions:
        return None
    source_sectors = max(int(part["start"]) + int(part["size"]) for part in partitions)
    if target_sectors <= source_sectors:
        return None
    scale = target_sectors / float(source_sectors)
    logger.info(
        "Scaling %s partition layout from %s to %s sectors (scale %.3f).",
        layout_label,
        source_sectors,
        target_sectors,
        scale,
    )

    ordered = sorted(partitions, key=lambda item: int(item["start"]))
    last_end = -1
    for index, part in enumerate(ordered, start=1):
        orig_start = int(part["start"])
        orig_size = int(part["size"])
        scaled_size = max(1, int(round(orig_size * scale)))
        start = orig_start if orig_start > last_end else last_end + 1
        if start >= target_sectors:
            raise RuntimeError("Scaled partition start exceeds target disk size.")
        if index == len(ordered):
            size = max(1, target_sectors - start)
        else:
            size = scaled_size
            if start + size > target_sectors:
                size = max(1, target_sectors - start)
        end = start + size - 1
        if end >= target_sectors:
            raise RuntimeError("Scaled partition exceeds target disk size.")
        part["new_start"] = start
        part["new_size"] = size
        label = part.get("prefix") or part.get("number") or index
        logger.info(
            "Partition %s resize: start %ss size %ss (%s) -> start %ss size %ss (%s)",
            label,
            orig_start,
            orig_size,
            devices.human_size(orig_size * sector_size),
            start,
            size,
            devices.human_size(size * sector_size),
        )
        last_end = end

    return ordered


def format_command_failure(summary: str, command: list[str], result: subprocess.CompletedProcess) -> str:
    """Format a command failure message."""
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


def is_parted_print_output(contents: str) -> bool:
    """Check if contents appear to be parted print output rather than a script."""
    stripped = contents.lstrip()
    if stripped.startswith("Model:"):
        return True
    if "Partition Table:" in contents:
        return True
    if re.search(r"^Number\s+Start", contents, flags=re.MULTILINE):
        return True
    return False


def expand_parted_compact_script(contents: str) -> str:
    """Expand a compact parted script (semicolon-separated) into multi-line format."""
    cleaned = contents.strip()
    if not cleaned:
        raise RuntimeError("Compact parted file is empty")
    commands: list[str] = []
    for line in cleaned.splitlines():
        for fragment in line.split(";"):
            command = fragment.strip()
            if command:
                commands.append(command)
    if not commands:
        raise RuntimeError("Compact parted file does not contain any commands")
    return "\n".join(commands)


def looks_like_sfdisk_script(contents: str) -> bool:
    """Check if contents appear to be an sfdisk script."""
    for line in contents.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("/dev/", "label:", "label-id:", "unit:", "sector-size:", "first-lba:", "last-lba:")):
            return True
    return False


def apply_disk_layout_op(op: DiskLayoutOp, target_node: str) -> bool:
    """Apply a disk layout operation to a target device.

    Returns:
        True if operation was applied successfully, False if skipped
    """
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
            message = format_command_failure("sfdisk failed", [sfdisk, "--force", target_node], result)
            raise RuntimeError(message)
        return True

    if op.kind == "chs.sf":
        if not op.contents:
            raise RuntimeError("chs.sf data missing or unreadable")
        if not looks_like_sfdisk_script(op.contents):
            logger.warning("Skipping chs.sf layout op %s: does not look like sfdisk input.", op.path)
            return False
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
            message = format_command_failure("sfdisk failed for chs.sf", [sfdisk, "--force", target_node], result)
            raise RuntimeError(message)
        return True

    if op.kind == "pt.parted":
        if not op.contents:
            raise RuntimeError("Missing parted data")
        if is_parted_print_output(op.contents):
            logger.debug(
                "Skipping parted layout op %s: detected parted print output instead of script.",
                op.path,
            )
            return False
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
            message = format_command_failure("parted failed", [parted, "--script", target_node], result)
            raise RuntimeError(message)
        return True

    if op.kind == "pt.parted.compact":
        if not op.contents:
            raise RuntimeError("Missing compact parted data")
        expanded = expand_parted_compact_script(op.contents)
        if is_parted_print_output(expanded):
            logger.debug(
                "Skipping compact parted layout op %s: detected parted print output instead of script.",
                op.path,
            )
            return False
        parted = shutil.which("parted")
        if not parted:
            raise RuntimeError("parted not found")
        result = subprocess.run(
            [parted, "-s", target_node],
            input=expanded,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            message = format_command_failure("parted failed", [parted, "--script", target_node], result)
            raise RuntimeError(message)
        return True

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
            message = format_command_failure("dd failed", result.args, result)
            raise RuntimeError(message)
        return True

    if op.kind == "hidden-data-after-mbr":
        if op.size_bytes <= 0:
            raise RuntimeError("hidden-data-after-mbr file is empty")
        dd_path = shutil.which("dd")
        if not dd_path:
            raise RuntimeError("dd not found")
        result = subprocess.run(
            [
                dd_path,
                f"if={op.path}",
                f"of={target_node}",
                "bs=1",
                "seek=512",
                f"count={op.size_bytes}",
                "conv=fsync",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            message = format_command_failure("dd failed", result.args, result)
            raise RuntimeError(message)
        return True

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
            message = format_command_failure("sgdisk failed", result.args, result)
            raise RuntimeError(message)
        return True

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
            message = format_command_failure("sgdisk failed", result.args, result)
            raise RuntimeError(message)
        return True

    raise RuntimeError(f"Unsupported disk layout op: {op.kind}")
