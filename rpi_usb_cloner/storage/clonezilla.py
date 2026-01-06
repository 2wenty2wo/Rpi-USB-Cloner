from __future__ import annotations

import logging
import os
import re
import shutil
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from rpi_usb_cloner.storage import clone, devices
from rpi_usb_cloner.storage.clone import get_partition_number, resolve_device_node

logger = logging.getLogger(__name__)

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


def restore_clonezilla_image(
    plan: RestorePlan,
    target_device: str,
    *,
    partition_mode: str = "k0",
) -> None:
    if os.geteuid() != 0:
        raise RuntimeError("Run as root")
    partition_mode = _normalize_partition_mode(partition_mode)
    target_node = resolve_device_node(target_device)
    target_name = Path(target_node).name
    target_info = devices.get_device_by_name(target_name)
    if target_info:
        devices.unmount_device(target_info)
    required_size = _estimate_required_size_bytes(
        plan.disk_layout_ops,
        image_dir=plan.image_dir,
    )
    target_size = _get_device_size_bytes(target_info, target_node)
    if required_size is None or target_size is None:
        print("Warning: unable to determine size information; skipping size check.")
    elif target_size < required_size:
        raise RuntimeError(
            f"Target device too small ({devices.human_size(target_size)} < {devices.human_size(required_size)})"
        )
    required_partitions = len(plan.parts)
    disk_layout_ops = _build_partition_mode_layout_ops(
        plan.disk_layout_ops,
        partition_mode=partition_mode,
        target_size=target_size,
    )
    applied_layout = False
    attempt_results: list[str] = []
    for op in disk_layout_ops:
        try:
            applied_layout = _apply_disk_layout_op(op, target_node)
        except Exception as exc:
            raise RuntimeError(f"Partition table apply failed ({op.kind}): {exc}") from exc
        if not applied_layout:
            continue
        _reread_partition_table(target_node)
        _settle_udev()
        _, observed_count = _wait_for_partition_count(
            target_name,
            required_partitions,
            timeout_seconds=10,
            allow_short=True,
        )
        if observed_count >= required_partitions:
            break
        if observed_count < required_partitions:
            logger.warning(
                "Partition count mismatch after %s layout op (expected %s, saw %s).",
                op.kind,
                required_partitions,
                observed_count,
            )
            attempt_results.append(f"{op.kind}: expected {required_partitions}, saw {observed_count}")
            applied_layout = False
    if disk_layout_ops and not applied_layout:
        attempts = "; ".join(attempt_results) if attempt_results else "no successful layout ops"
        raise RuntimeError(
            "Partition table apply failed to produce expected partition count "
            f"(expected {required_partitions}). Attempts: {attempts}."
        )
    refreshed, target_parts = _wait_for_target_partitions(
        target_name,
        plan.parts,
        timeout_seconds=10,
    )
    total_parts = len(plan.partition_ops)
    for index, op in enumerate(plan.partition_ops, start=1):
        target_part = target_parts.get(op.partition)
        if not target_part:
            raise RuntimeError(f"Missing target partition for {op.partition}")
        title = f"PART {index}/{total_parts}"
        try:
            _restore_partition_op(op, target_part, title=title)
        except Exception as exc:
            raise RuntimeError(f"Partition restore failed ({title}): {exc}") from exc


def _is_clonezilla_image_dir(path: Path) -> bool:
    parts_file = path / "parts"
    if not parts_file.exists():
        return False
    has_table = _find_partition_table(path) is not None
    has_images = any(path.glob("*-ptcl-img*")) or any(path.glob("*dd-img*"))
    return has_table or has_images


def _reread_partition_table(target_node: str) -> None:
    partprobe = shutil.which("partprobe")
    if partprobe:
        subprocess.run([partprobe, target_node], check=False)
        return
    blockdev = shutil.which("blockdev")
    if blockdev:
        subprocess.run([blockdev, "--rereadpt", target_node], check=False)


def _settle_udev() -> None:
    udevadm = shutil.which("udevadm")
    if udevadm:
        subprocess.run([udevadm, "settle"], check=False)


def _wait_for_target_partitions(
    target_name: str,
    parts: Iterable[str],
    *,
    timeout_seconds: int,
    poll_interval: float = 1.0,
) -> tuple[dict, dict[str, str]]:
    deadline = time.monotonic() + timeout_seconds
    last_info = None
    last_mapping: dict[str, str] = {}
    while time.monotonic() < deadline:
        last_info = devices.get_device_by_name(target_name)
        if last_info:
            last_mapping = _map_target_partitions(parts, last_info)
            missing = [part for part in parts if not last_mapping.get(part)]
            if not missing:
                return last_info, last_mapping
        time.sleep(poll_interval)
    if not last_info:
        raise RuntimeError("Unable to refresh target device after partition table update.")
    missing = [part for part in parts if not last_mapping.get(part)]
    missing_label = ", ".join(missing) if missing else "unknown"
    raise RuntimeError(f"Timed out waiting for partitions to appear: {missing_label}")


def _wait_for_partition_count(
    target_name: str,
    required_count: int,
    *,
    timeout_seconds: int,
    poll_interval: float = 0.5,
    allow_short: bool = False,
) -> tuple[dict, int]:
    deadline = time.monotonic() + timeout_seconds
    last_info = None
    last_count = 0
    while time.monotonic() < deadline:
        last_info = devices.get_device_by_name(target_name)
        if last_info:
            last_count = _count_target_partitions(last_info)
            if last_count >= required_count:
                return last_info, last_count
        time.sleep(poll_interval)
    if not last_info:
        raise RuntimeError("Unable to refresh target device after partition table update.")
    if allow_short:
        return last_info, last_count
    raise RuntimeError(
        "Partition table applied but kernel did not create all partitions "
        f"(expected {required_count}, saw {last_count})."
    )


def _collect_disk_layout_ops(image_dir: Path, *, select: bool = True) -> list[DiskLayoutOp]:
    disk_layout_ops: list[DiskLayoutOp] = []
    for name, kind in (("disk", "disk"), ("sfdisk", "sfdisk")):
        path = image_dir / name
        if path.exists():
            disk_layout_ops.append(_read_disk_layout_op(kind, path))
    for path in sorted(image_dir.glob("*-pt.sf")):
        disk_layout_ops.append(_read_disk_layout_op("pt.sf", path))
    for path in sorted(image_dir.glob("*-pt.parted")):
        disk_layout_ops.append(_read_disk_layout_op("pt.parted", path))
    for path in sorted(image_dir.glob("*-pt.sgdisk")):
        disk_layout_ops.append(_read_disk_layout_op("pt.sgdisk", path))
    for path in sorted(image_dir.glob("*-mbr")):
        disk_layout_ops.append(_read_disk_layout_op("mbr", path))
    for path in sorted(image_dir.glob("*-gpt")):
        disk_layout_ops.append(_read_disk_layout_op("gpt", path))
    if select:
        return _select_disk_layout_ops(disk_layout_ops)
    return disk_layout_ops


def _select_disk_layout_ops(disk_layout_ops: list[DiskLayoutOp]) -> list[DiskLayoutOp]:
    if not disk_layout_ops:
        return []
    priority = ["pt.sgdisk", "gpt", "pt.parted", "pt.sf", "mbr", "sfdisk", "disk"]
    priority_index = {kind: index for index, kind in enumerate(priority)}
    return sorted(
        disk_layout_ops,
        key=lambda op: priority_index.get(op.kind, len(priority)),
    )


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
    dd_files = _find_image_files(image_dir, part_name, "img")
    if partclone_files:
        fstype = _extract_partclone_fstype(part_name, partclone_files[0].name)
        if not dd_files:
            return PartitionRestoreOp(
                partition=part_name,
                image_files=partclone_files,
                tool="partclone",
                fstype=fstype,
                compressed=_is_compressed(partclone_files),
            )
        tool = _get_partclone_tool((fstype or "").lower())
        if tool:
            return PartitionRestoreOp(
                partition=part_name,
                image_files=partclone_files,
                tool="partclone",
                fstype=fstype,
                compressed=_is_compressed(partclone_files),
            )
    if dd_files:
        return PartitionRestoreOp(
            partition=part_name,
            image_files=dd_files,
            tool="dd",
            fstype=None,
            compressed=_is_compressed(dd_files),
        )
    if _has_partition_image_files(image_dir, part_name):
        raise RuntimeError(f"Image set does not match partclone/dd naming convention for partition {part_name}")
    return None


def _estimate_required_size_bytes(
    disk_layout_ops: list[DiskLayoutOp],
    *,
    image_dir: Optional[Path] = None,
) -> Optional[int]:
    ops = list(disk_layout_ops)
    if image_dir:
        extra_ops = _collect_disk_layout_ops(image_dir, select=False)
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
                max_lba = _estimate_last_lba_from_sgdisk_backup(op.path)
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


def _get_device_size_bytes(target_info: Optional[dict], target_node: str) -> Optional[int]:
    if target_info and target_info.get("size"):
        return int(target_info.get("size"))
    blockdev = shutil.which("blockdev")
    if not blockdev:
        return None
    result = subprocess.run(
        [blockdev, "--getsize64", target_node],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _normalize_partition_mode(partition_mode: Optional[str]) -> str:
    if not partition_mode:
        return "k0"
    normalized = str(partition_mode).strip().lower()
    if normalized.startswith("-"):
        normalized = normalized[1:]
    return normalized


def _build_partition_mode_layout_ops(
    disk_layout_ops: list[DiskLayoutOp],
    *,
    partition_mode: str,
    target_size: Optional[int],
) -> list[DiskLayoutOp]:
    if partition_mode not in {"k0", "k", "k1", "k2"}:
        raise RuntimeError(f"Unsupported partition mode: {partition_mode}")
    if partition_mode in {"k", "k2"}:
        return []
    if partition_mode == "k1" and target_size:
        for op in disk_layout_ops:
            scaled = _scale_sfdisk_layout(op, target_size)
            if scaled:
                return [scaled]
    return list(disk_layout_ops)


def _scale_sfdisk_layout(op: DiskLayoutOp, target_size: int) -> Optional[DiskLayoutOp]:
    if op.kind not in {"disk", "sfdisk", "pt.sf"} or not op.contents:
        return None
    lines = op.contents.splitlines()
    sector_size = 512
    partitions: list[dict[str, int | str]] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("sector-size:"):
            match = re.search(r"sector-size:\s*(\d+)", stripped)
            if match:
                sector_size = int(match.group(1))
            continue
        if not stripped.startswith("/dev/") or ":" not in stripped:
            continue
        prefix, rest = stripped.split(":", 1)
        fields = _parse_sfdisk_fields(rest)
        start = _get_sfdisk_int_field(fields, "start")
        size = _get_sfdisk_int_field(fields, "size")
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
    max_end = max(int(part["start"]) + int(part["size"]) - 1 for part in partitions)
    target_sectors = target_size // sector_size
    if target_sectors <= max_end + 1:
        return None
    scale = target_sectors / float(max_end + 1)
    last_end = -1
    for part in partitions:
        start = int(part["start"])
        size = int(part["size"])
        scaled_start = max(1, int(round(start * scale)))
        scaled_size = max(1, int(round(size * scale)))
        if scaled_start <= last_end:
            scaled_start = last_end + 1
        if scaled_start + scaled_size > target_sectors:
            scaled_size = max(1, target_sectors - scaled_start)
        last_end = scaled_start + scaled_size - 1
        part["start"] = scaled_start
        part["size"] = scaled_size
        part["fields"] = _set_sfdisk_field(part["fields"], "start", str(scaled_start))
        part["fields"] = _set_sfdisk_field(part["fields"], "size", str(scaled_size))
        lines[part["index"]] = _format_sfdisk_line(part["prefix"], part["fields"])
    return DiskLayoutOp(kind=op.kind, path=op.path, contents="\n".join(lines), size_bytes=op.size_bytes)


def _parse_sfdisk_fields(rest: str) -> list[tuple[str, str]]:
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


def _get_sfdisk_int_field(fields: list[tuple[str, str]], key: str) -> Optional[int]:
    for field_key, value in fields:
        if field_key != key:
            continue
        match = re.match(r"^(\d+)s?$", value)
        if match:
            return int(match.group(1))
    return None


def _set_sfdisk_field(fields: list[tuple[str, str]], key: str, value: str) -> list[tuple[str, str]]:
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


def _format_sfdisk_line(prefix: str, fields: list[tuple[str, str]]) -> str:
    rendered = []
    for key, value in fields:
        if value:
            rendered.append(f"{key}={value}")
        else:
            rendered.append(key)
    return f"{prefix} : {', '.join(rendered)}"


def _apply_disk_layout_op(op: DiskLayoutOp, target_node: str) -> bool:
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
            message = _format_command_failure("sfdisk failed", [sfdisk, "--force", target_node], result)
            raise RuntimeError(message)
        return True
    if op.kind == "pt.parted":
        if not op.contents:
            raise RuntimeError("Missing parted data")
        if _is_parted_print_output(op.contents):
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
            message = _format_command_failure("parted failed", [parted, "--script", target_node], result)
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
            message = _format_command_failure("dd failed", result.args, result)
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
            message = _format_command_failure("sgdisk failed", result.args, result)
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
            message = _format_command_failure("sgdisk failed", result.args, result)
            raise RuntimeError(message)
        return True
    raise RuntimeError(f"Unsupported disk layout op: {op.kind}")


def _is_parted_print_output(contents: str) -> bool:
    stripped = contents.lstrip()
    if stripped.startswith("Model:"):
        return True
    if "Partition Table:" in contents:
        return True
    if re.search(r"^Number\s+Start", contents, flags=re.MULTILINE):
        return True
    return False


def _format_command_failure(summary: str, command: list[str], result: subprocess.CompletedProcess) -> str:
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


def _estimate_last_lba_from_sgdisk_backup(path: Path) -> Optional[int]:
    data = path.read_bytes()
    signature = b"EFI PART"
    offset = data.find(signature)
    if offset == -1 or len(data) < offset + 56:
        return None
    current_lba = struct.unpack_from("<Q", data, offset + 24)[0]
    backup_lba = struct.unpack_from("<Q", data, offset + 32)[0]
    last_usable = struct.unpack_from("<Q", data, offset + 48)[0]
    return max(current_lba, backup_lba, last_usable)


def _restore_partition_op(op: PartitionRestoreOp, target_part: str, *, title: str) -> None:
    restore_command = _build_restore_command_from_plan(op, target_part)
    _run_restore_pipeline(op.image_files, restore_command, title=title)


def _select_clonezilla_volume_set(primary: list[Path], secondary: list[Path]) -> list[Path]:
    if primary and secondary:
        return primary if len(primary) >= len(secondary) else secondary
    return primary or secondary


def _find_image_files(image_dir: Path, part_name: str, suffix: str) -> list[Path]:
    if suffix == "ptcl-img":
        prefixed_matches = list(image_dir.glob(f"*-{part_name}.*-{suffix}*"))
        direct_matches = list(image_dir.glob(f"{part_name}.*-{suffix}*"))
        matches = _select_clonezilla_volume_set(direct_matches, prefixed_matches)
        return _sorted_clonezilla_volumes(matches)
    elif suffix == "img":
        dd_prefixed = list(image_dir.glob(f"*-{part_name}.*-dd-img*"))
        dd_direct = list(image_dir.glob(f"{part_name}.*-dd-img*"))
        dd_matches = _select_clonezilla_volume_set(dd_direct, dd_prefixed)
        if dd_matches:
            return _sorted_clonezilla_volumes(dd_matches)
        img_prefixed = list(image_dir.glob(f"*-{part_name}.*.img*"))
        img_direct = list(image_dir.glob(f"{part_name}.*.img*"))
        img_matches = _select_clonezilla_volume_set(img_direct, img_prefixed)
        return _sorted_clonezilla_volumes(img_matches)
    else:
        pattern = f"*-{part_name}.*.{suffix}*"
    return _sorted_clonezilla_volumes(image_dir.glob(pattern))


def _has_partition_image_files(image_dir: Path, part_name: str) -> bool:
    return any(image_dir.glob(f"*-{part_name}.*-img*"))


def _extract_volume_suffix(path: Path) -> Optional[str]:
    match = re.search(r"\.([a-z]{2})$", path.name)
    if not match:
        return None
    return match.group(1)


def _volume_suffix_index(suffix: Optional[str]) -> int:
    if not suffix:
        return -1
    first = ord(suffix[0]) - ord("a")
    second = ord(suffix[1]) - ord("a")
    if first < 0 or first > 25 or second < 0 or second > 25:
        return -1
    return first * 26 + second


def _sorted_clonezilla_volumes(paths: Iterable[Path]) -> list[Path]:
    def sort_key(path: Path) -> tuple[str, int, str]:
        suffix = _extract_volume_suffix(path)
        base = path.name
        if suffix:
            base = base[: -len(suffix) - 1]
        return (base, _volume_suffix_index(suffix), path.name)

    return sorted({path for path in paths}, key=sort_key)


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


def _count_target_partitions(target_device: dict) -> int:
    return sum(1 for child in devices.get_children(target_device) if child.get("type") == "part")


def _restore_partition(image_dir: Path, part_name: str, target_part: str) -> None:
    partclone_files = _find_image_files(image_dir, part_name, "ptcl-img")
    dd_files = _find_image_files(image_dir, part_name, "img")
    if not partclone_files and not dd_files:
        if _has_partition_image_files(image_dir, part_name):
            raise RuntimeError(f"Image set does not match partclone/dd naming convention for partition {part_name}")
        raise RuntimeError(f"Image data missing for {part_name}")
    if partclone_files:
        fstype = _extract_partclone_fstype(part_name, partclone_files[0].name)
        if not dd_files or _get_partclone_tool((fstype or "").lower()):
            descriptor = {
                "mode": "partclone",
                "fstype": fstype,
                "compressed": _is_compressed(partclone_files),
            }
            image_files = partclone_files
        else:
            descriptor = {"mode": "dd", "compressed": _is_compressed(dd_files)}
            image_files = dd_files
    else:
        descriptor = {"mode": "dd", "compressed": _is_compressed(dd_files)}
        image_files = dd_files
    command, supports_progress = _build_restore_command(descriptor, target_part)
    _run_pipeline(image_files, command, supports_progress)


def _get_partition_descriptor(part_name: str, image_files: list[Path]) -> dict:
    file_name = image_files[0].name
    partclone_match = re.search(rf"{re.escape(part_name)}\.(.+?)-ptcl-img", file_name)
    if partclone_match:
        return {
            "mode": "partclone",
            "fstype": partclone_match.group(1),
            "compressed": _is_compressed(image_files),
        }
    if "dd-img" in file_name:
        return {"mode": "dd", "compressed": _is_compressed(image_files)}
    return {"mode": "dd", "compressed": _is_compressed(image_files)}


def _is_gzip_compressed(image_files: list[Path]) -> bool:
    for image_file in image_files:
        if ".gz" in image_file.suffixes:
            return True
        if image_file.name.endswith(".gz"):
            return True
    return False


def _is_zstd_compressed(image_files: list[Path]) -> bool:
    for image_file in image_files:
        if ".zst" in image_file.suffixes:
            return True
        if image_file.name.endswith(".zst"):
            return True
    return False


def _get_compression_type(image_files: list[Path]) -> Optional[str]:
    if _is_zstd_compressed(image_files):
        return "zstd"
    if _is_gzip_compressed(image_files):
        return "gzip"
    return None


def _is_compressed(image_files: list[Path]) -> bool:
    return _get_compression_type(image_files) is not None


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
    found = shutil.which(tool)
    if found:
        return found
    for prefix in ("/usr/sbin", "/sbin", "/usr/local/sbin"):
        candidate = Path(prefix) / tool
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _build_restore_command_from_plan(op: PartitionRestoreOp, target_part: str) -> list[str]:
    if op.tool == "partclone":
        fstype = (op.fstype or "").lower()
        tool = _get_partclone_tool(fstype)
        if not tool:
            raise RuntimeError(f"partclone tool not found for filesystem '{fstype}'")
        return [tool, "-r", "-s", "-", "-o", target_part, "-F"]
    dd_path = shutil.which("dd")
    if not dd_path:
        raise RuntimeError("dd not found")
    return [dd_path, f"of={target_part}", "bs=4M", "status=progress", "conv=fsync"]


def _run_pipeline(image_files: list[Path], restore_command: list[str], supports_progress: bool) -> None:
    if not image_files:
        raise RuntimeError("No image files")
    image_files = _sorted_clonezilla_volumes(image_files)
    cat_proc = subprocess.Popen(["cat", *[str(path) for path in image_files]], stdout=subprocess.PIPE)
    upstream = cat_proc.stdout
    decompress_proc = None
    compression_type = _get_compression_type(image_files)
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
        raise RuntimeError("Restore pipeline failed")
    restore_proc = subprocess.Popen(
        restore_command,
        stdin=upstream,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
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


def _run_restore_pipeline(image_files: list[Path], restore_command: list[str], *, title: str) -> None:
    if not image_files:
        raise RuntimeError("No image files")
    image_files = _sorted_clonezilla_volumes(image_files)
    cat_proc = subprocess.Popen(["cat", *[str(path) for path in image_files]], stdout=subprocess.PIPE)
    upstream = cat_proc.stdout
    decompress_proc = None
    compression_type = _get_compression_type(image_files)
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
        raise RuntimeError("Restore pipeline failed")
    error: Optional[Exception] = None
    try:
        clone.run_checked_with_progress(
            restore_command,
            title=title,
            stdin_source=upstream,
        )
    except Exception as exc:
        error = exc
    finally:
        if cat_proc.stdout:
            cat_proc.stdout.close()
        cat_proc.wait()
        if decompress_proc:
            if decompress_proc.stdout:
                decompress_proc.stdout.close()
            decompress_proc.wait()
    if error:
        raise error
    if cat_proc.returncode != 0:
        raise RuntimeError("Image stream failed")
    if decompress_proc and decompress_proc.returncode != 0:
        raise RuntimeError("Image decompression failed")
