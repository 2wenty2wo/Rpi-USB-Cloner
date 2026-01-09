"""USB drive cloning operations with verification and progress tracking.

This module implements the core USB drive cloning functionality for the Rpi-USB-Cloner,
supporting multiple cloning modes with real-time progress display and verification.

Cloning Modes:
    smart:  Intelligent partition-aware cloning using partclone for filesystem-specific
            operations. Copies only used blocks for efficiency. Automatically handles
            partition tables and filesystem-specific operations.

    exact:  Raw block-level cloning using dd. Creates bit-for-bit copies of entire
            devices regardless of filesystem or used space. Slower but more thorough.

    verify: Performs smart clone followed by SHA256 verification of source and target
            to ensure data integrity. Adds verification time but guarantees accuracy.

Progress Monitoring:
    All operations provide real-time progress feedback on the OLED display, including:
    - Current operation and percentage complete
    - Data transfer rate and throughput
    - Estimated time remaining
    - Spinner animations for long-running tasks

Operations:
    - clone_device(): Main entry point for cloning with mode selection
    - clone_dd(): Raw block-level copy with progress tracking
    - clone_partclone(): Filesystem-aware partition cloning
    - erase_device(): Quick or full disk erasure
    - verify_devices(): SHA256 hash verification

Implementation Details:
    - Uses subprocess pipelines for efficient data streaming
    - Monitors stderr for progress information using regex patterns
    - Handles partition table copying with sfdisk
    - Automatically unmounts devices before operations
    - Supports progress callbacks for UI updates

Security Notes:
    - All operations require root privileges
    - Devices should be validated before cloning to prevent system disk overwrites
    - No input validation on device nodes (see security analysis)

Example:
    >>> from rpi_usb_cloner.storage.clone import clone_device
    >>> source_device = {"name": "sda", "size": 8000000000}
    >>> target_device = {"name": "sdb", "size": 8000000000}
    >>> success = clone_device(source_device, target_device, mode="smart")
"""
import os
import re
import select
import shutil
import subprocess
import time

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.storage.devices import (
    format_device_label,
    get_children,
    get_device_by_name,
    human_size,
    unmount_device,
)
from rpi_usb_cloner.ui.display import display_lines

_log_debug = None


def configure_clone_helpers(log_debug=None) -> None:
    global _log_debug
    _log_debug = log_debug


def log_debug(message: str) -> None:
    if _log_debug:
        _log_debug(message)


def get_partition_display_name(part):
    """Get a friendly display name for a partition.

    Returns the partition label if available, otherwise the partition name.
    """
    # Try partition label first (GPT)
    partlabel = part.get("partlabel", "").strip()
    if partlabel:
        return partlabel

    # Try filesystem label
    label = part.get("label", "").strip()
    if label:
        return label

    # Fall back to partition name (e.g., "sda1")
    name = part.get("name", "")
    if name:
        return name

    return "partition"


def format_filesystem_type(fstype):
    """Convert filesystem type to user-friendly display name.

    Args:
        fstype: Filesystem type string (e.g., "ext4", "vfat", "ntfs")

    Returns:
        Friendly display name (e.g., "ext4", "FAT32", "NTFS")
    """
    if not fstype:
        return "unknown"

    fstype_lower = fstype.lower()

    # Map filesystem types to friendly names
    friendly_names = {
        "vfat": "FAT32",
        "fat16": "FAT16",
        "fat32": "FAT32",
        "ntfs": "NTFS",
        "exfat": "exFAT",
        "ext2": "ext2",
        "ext3": "ext3",
        "ext4": "ext4",
        "xfs": "XFS",
        "btrfs": "Btrfs",
    }

    return friendly_names.get(fstype_lower, fstype)


def normalize_clone_mode(mode):
    if not mode:
        return "smart"
    mode = mode.lower()
    if mode == "raw":
        return "exact"
    if mode in ("smart", "exact", "verify"):
        return mode
    return "smart"


def resolve_device_node(device):
    if isinstance(device, str):
        return device if device.startswith("/dev/") else f"/dev/{device}"
    return f"/dev/{device.get('name')}"


def run_checked_command(command, input_text=None):
    log_debug(f"Running command: {' '.join(command)}")
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        message = stderr or stdout or "Command failed"
        raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")
    return result.stdout


def copy_partition_table(src, dst):
    src_node = resolve_device_node(src)
    dst_node = resolve_device_node(dst)
    sfdisk_path = shutil.which("sfdisk")
    if not sfdisk_path:
        raise RuntimeError("sfdisk not found")
    dump_output = run_checked_command([sfdisk_path, "--dump", src_node])
    label = None
    for line in dump_output.splitlines():
        if line.startswith("label:"):
            label = line.split(":", 1)[1].strip().lower()
            break
    if not label:
        raise RuntimeError("Unable to detect partition table label")
    if label == "gpt":
        sgdisk_path = shutil.which("sgdisk")
        if not sgdisk_path:
            raise RuntimeError("sgdisk not found for GPT replicate")
        run_checked_command([sgdisk_path, f"--replicate={dst_node}", "--randomize-guids", src_node])
        log_debug(f"GPT partition table replicated from {src_node} to {dst_node}")
        return
    if label in ("dos", "mbr", "msdos"):
        run_checked_command([sfdisk_path, dst_node], input_text=dump_output)
        log_debug(f"MBR partition table cloned from {src_node} to {dst_node}")
        return
    raise RuntimeError(f"Unsupported partition table label: {label}")


def format_eta(seconds):
    if seconds is None:
        return None
    seconds = int(seconds)
    if seconds < 0:
        return None
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_progress_lines(title, device, mode, bytes_copied, total_bytes, rate, eta):
    lines = []
    if title:
        lines.append(title)
    if device:
        lines.append(device)
    if mode:
        lines.append(f"Mode {mode}")
    if bytes_copied is not None:
        percent = ""
        if total_bytes:
            percent = f"{(bytes_copied / total_bytes) * 100:.1f}%"
        written_line = f"Wrote {human_size(bytes_copied)}"
        if percent:
            written_line = f"{written_line} {percent}"
        lines.append(written_line)
    else:
        lines.append("Working...")
    if rate:
        rate_line = f"{human_size(rate)}/s"
        if eta:
            rate_line = f"{rate_line} ETA {eta}"
        lines.append(rate_line)
    return lines[:6]


def format_progress_display(title, device, mode, bytes_copied, total_bytes, percent, rate, eta, spinner=None, subtitle=None):
    lines = []
    if title:
        title_line = title
        if spinner:
            title_line = f"{title} {spinner}"
        lines.append(title_line)
    if subtitle:
        lines.append(subtitle)
    if device:
        lines.append(device)
    if mode:
        lines.append(f"Mode {mode}")
    if bytes_copied is not None:
        percent_display = ""
        if total_bytes:
            percent_display = f"{(bytes_copied / total_bytes) * 100:.1f}%"
        elif percent is not None:
            percent_display = f"{percent:.1f}%"
        written_line = f"Wrote {human_size(bytes_copied)}"
        if percent_display:
            written_line = f"{written_line} {percent_display}"
        lines.append(written_line)
    else:
        # Don't show standalone percentage - it's now displayed in the progress bar
        lines.append("Working...")
    if rate:
        rate_line = f"{human_size(rate)}/s"
        if eta:
            rate_line = f"{rate_line} ETA {eta}"
        lines.append(rate_line)
    return lines[:6]


def get_partition_number(name):
    if not name:
        return None
    match = re.search(r"(?:p)?(\d+)$", name)
    if not match:
        return None
    return int(match.group(1))


def run_progress_command(command, total_bytes=None, title="WORKING", device_label=None, mode_label=None):
    display_lines(format_progress_display(title, device_label, mode_label, 0 if total_bytes else None, total_bytes, None, None, None))
    log_debug(f"Starting command: {' '.join(command)}")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    last_update = time.time()
    last_bytes = None
    last_time = None
    last_rate = None
    last_eta = None
    last_percent = None
    spinner_frames = ["|", "/", "-", "\\"]
    spinner_index = 0
    refresh_interval = 1.0
    while True:
        ready, _, _ = select.select([process.stderr], [], [], refresh_interval)
        now = time.time()
        line = None
        if ready:
            line = process.stderr.readline()
        if line:
            log_debug(f"stderr: {line.strip()}")
            bytes_match = re.search(r"(\d+)\s+bytes", line)
            percent_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            rate_match = re.search(r"(\d+(?:\.\d+)?)\s*MiB/s", line)
            # Don't use stale bytes - prevents mixing old bytes with new percentage
            bytes_copied = None
            rate = last_rate
            eta = last_eta
            if bytes_match:
                bytes_copied = int(bytes_match.group(1))
                if rate_match:
                    rate = float(rate_match.group(1)) * 1024 * 1024
                else:
                    rate = None
                    if last_bytes is not None and last_time is not None:
                        delta_bytes = bytes_copied - last_bytes
                        delta_time = now - last_time
                        if delta_bytes >= 0 and delta_time > 0:
                            rate = delta_bytes / delta_time
                if rate and total_bytes and bytes_copied <= total_bytes:
                    eta_seconds = (total_bytes - bytes_copied) / rate if rate > 0 else None
                    eta = format_eta(eta_seconds)
                last_bytes = bytes_copied
                last_time = now
                last_rate = rate or last_rate
                last_eta = eta or last_eta
            if percent_match:
                last_percent = float(percent_match.group(1))
            rate_display = rate if rate is not None else last_rate
            eta_display = eta if eta is not None else last_eta
            display_lines(
                format_progress_display(
                    title,
                    device_label,
                    mode_label,
                    bytes_copied,
                    total_bytes,
                    last_percent,
                    rate_display,
                    eta_display,
                    spinner_frames[spinner_index],
                )
            )
            last_update = now
        if now - last_update >= refresh_interval:
            spinner_index = (spinner_index + 1) % len(spinner_frames)
            display_lines(
                format_progress_display(
                    title,
                    device_label,
                    mode_label,
                    last_bytes,
                    total_bytes,
                    last_percent,
                    last_rate,
                    last_eta,
                    spinner_frames[spinner_index],
                )
            )
            last_update = now
        if process.poll() is not None and not line:
            break
    if process.returncode != 0:
        error_output = process.stderr.read().strip()
        message = error_output.splitlines()[-1] if error_output else "Command failed"
        display_lines(["FAILED", message[:20]])
        log_debug(f"Command failed with code {process.returncode}: {message}")
        return False
    display_lines([title, "Complete"])
    log_debug("Command completed successfully")
    return True


def parse_progress(stderr_output, total_bytes=None, title="WORKING"):
    if not stderr_output:
        return
    for line in stderr_output.splitlines():
        log_debug(f"stderr: {line.strip()}")
        bytes_match = re.search(r"(\d+)\s+bytes", line)
        percent_match = re.search(r"(\d+(?:\.\d+)?)%", line)
        if bytes_match:
            bytes_copied = int(bytes_match.group(1))
            percent = ""
            if total_bytes:
                percent = f"{(bytes_copied / total_bytes) * 100:.1f}%"
            elif percent_match:
                percent = f"{percent_match.group(1)}%"
            display_lines([title, f"{human_size(bytes_copied)} {percent}".strip()])
            continue
        if percent_match and not total_bytes:
            display_lines([title, f"{percent_match.group(1)}%"])


def run_checked_with_progress(
    command,
    total_bytes=None,
    title="WORKING",
    stdout_target=None,
    stdin_source=None,
):
    display_lines([title, "Starting..."])
    log_debug(f"Running command: {' '.join(command)}")
    result = subprocess.run(
        command,
        stdin=stdin_source,
        stdout=stdout_target or subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    parse_progress(result.stderr, total_bytes=total_bytes, title=title)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip() if result.stdout else ""
        message = stderr or stdout or "Command failed"
        raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")
    display_lines([title, "Complete"])
    return result


def run_checked_with_streaming_progress(
    command,
    total_bytes=None,
    title="WORKING",
    stdout_target=None,
    stdin_source=None,
    progress_callback=None,
    subtitle=None,
):
    def emit_progress(lines, ratio=None):
        if progress_callback:
            progress_callback(lines, ratio)
        else:
            display_lines(lines)

    def clamp_ratio(value):
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))

    def compute_ratio(bytes_copied, percent_value):
        if bytes_copied is not None and total_bytes:
            return clamp_ratio(bytes_copied / total_bytes)
        if percent_value is not None:
            return clamp_ratio(percent_value / 100.0)
        return None

    emit_progress(
        format_progress_display(
            title,
            None,
            None,
            0 if total_bytes else None,
            total_bytes,
            None,
            None,
            None,
            subtitle=subtitle,
        ),
        ratio=compute_ratio(0 if total_bytes else None, None),
    )
    log_debug(f"Running command: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        stdin=stdin_source,
        stdout=stdout_target or subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr_lines = []
    last_update = time.time()
    last_bytes = None
    last_time = None
    last_rate = None
    last_eta = None
    last_percent = None
    spinner_frames = ["|", "/", "-", "\\"]
    spinner_index = 0
    refresh_interval = 1.0
    while True:
        ready, _, _ = select.select([process.stderr], [], [], refresh_interval)
        now = time.time()
        line = None
        if ready:
            line = process.stderr.readline()
        if line:
            stderr_lines.append(line)
            log_debug(f"stderr: {line.strip()}")
            bytes_match = re.search(r"(\d+)\s+bytes", line)
            percent_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            rate_match = re.search(r"(\d+(?:\.\d+)?)\s*MiB/s", line)
            # Don't use stale bytes - prevents mixing old bytes with new percentage
            bytes_copied = None
            rate = last_rate
            eta = last_eta
            if bytes_match:
                bytes_copied = int(bytes_match.group(1))
                if rate_match:
                    rate = float(rate_match.group(1)) * 1024 * 1024
                else:
                    rate = None
                    if last_bytes is not None and last_time is not None:
                        delta_bytes = bytes_copied - last_bytes
                        delta_time = now - last_time
                        if delta_bytes >= 0 and delta_time > 0:
                            rate = delta_bytes / delta_time
                if rate and total_bytes and bytes_copied <= total_bytes:
                    eta_seconds = (total_bytes - bytes_copied) / rate if rate > 0 else None
                    eta = format_eta(eta_seconds)
                last_bytes = bytes_copied
                last_time = now
                last_rate = rate or last_rate
                last_eta = eta or last_eta
            if percent_match:
                last_percent = float(percent_match.group(1))
            rate_display = rate if rate is not None else last_rate
            eta_display = eta if eta is not None else last_eta
            emit_progress(
                format_progress_display(
                    title,
                    None,
                    None,
                    bytes_copied,
                    total_bytes,
                    last_percent,
                    rate_display,
                    eta_display,
                    spinner_frames[spinner_index],
                    subtitle=subtitle,
                ),
                ratio=compute_ratio(bytes_copied, last_percent),
            )
            last_update = now
        if now - last_update >= refresh_interval:
            spinner_index = (spinner_index + 1) % len(spinner_frames)
            emit_progress(
                format_progress_display(
                    title,
                    None,
                    None,
                    last_bytes,
                    total_bytes,
                    last_percent,
                    last_rate,
                    last_eta,
                    spinner_frames[spinner_index],
                    subtitle=subtitle,
                ),
                ratio=compute_ratio(last_bytes, last_percent),
            )
            last_update = now
        if process.poll() is not None and not line:
            break
    remaining_stderr = process.stderr.read() if process.stderr else ""
    if remaining_stderr:
        stderr_lines.append(remaining_stderr)
    stdout_data = ""
    if stdout_target is None and process.stdout:
        stdout_data = process.stdout.read()
    process.wait()
    stderr_output = "".join(stderr_lines)
    if process.returncode != 0:
        stderr = stderr_output.strip()
        stdout = stdout_data.strip()
        message = stderr or stdout or "Command failed"
        raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")
    emit_progress([title, "Complete"], ratio=1.0)
    return subprocess.CompletedProcess(command, process.returncode, stdout=stdout_data, stderr=stderr_output)


def clone_dd(src, dst, total_bytes=None, title="CLONING", subtitle=None):
    dd_path = shutil.which("dd")
    if not dd_path:
        raise RuntimeError("dd not found")
    src_node = resolve_device_node(src)
    dst_node = resolve_device_node(dst)
    run_checked_with_streaming_progress(
        [dd_path, f"if={src_node}", f"of={dst_node}", "bs=4M", "status=progress", "conv=fsync"],
        total_bytes=total_bytes,
        title=title,
        subtitle=subtitle,
    )


def clone_partclone(source, target):
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
    source_node = resolve_device_node(source)
    target_node = resolve_device_node(target)
    source_name = os.path.basename(source_node)
    target_name = os.path.basename(target_node)
    source_device = get_device_by_name(source_name) or (source if isinstance(source, dict) else None)
    target_device = get_device_by_name(target_name) or (target if isinstance(target, dict) else None)
    if not source_device or not target_device:
        clone_dd(source_node, target_node, total_bytes=source.get("size") if isinstance(source, dict) else None)
        return
    source_parts = [child for child in get_children(source_device) if child.get("type") == "part"]
    if not source_parts:
        clone_dd(source_node, target_node, total_bytes=source_device.get("size"))
        return
    target_parts = [child for child in get_children(target_device) if child.get("type") == "part"]
    target_parts_by_number = {}
    for child in target_parts:
        part_number = get_partition_number(child.get("name"))
        if part_number is None:
            continue
        target_parts_by_number.setdefault(part_number, child)
    for index, part in enumerate(source_parts, start=1):
        src_part = f"/dev/{part.get('name')}"
        part_number = get_partition_number(part.get("name"))
        dst_part = None
        if part_number is not None:
            target_part = target_parts_by_number.get(part_number)
            if target_part:
                dst_part = f"/dev/{target_part.get('name')}"
        if not dst_part and index - 1 < len(target_parts):
            dst_part = f"/dev/{target_parts[index - 1].get('name')}"
        if not dst_part:
            raise RuntimeError(f"Unable to map {src_part} to target partition")
        fstype = (part.get("fstype") or "").lower()
        tool = partclone_tools.get(fstype)
        tool_path = shutil.which(tool) if tool else None

        # Get friendly partition information for display
        part_name = get_partition_display_name(part)
        part_size_str = human_size(part.get("size")) if part.get("size") else ""
        fs_friendly = format_filesystem_type(fstype)

        # Build title line: "partition_name (1/4)"
        title_line = f"{part_name} ({index}/{len(source_parts)})"

        # Build info line: "8.2GB ext4" or "512MB FAT32"
        info_parts = []
        if part_size_str:
            info_parts.append(part_size_str)
        if fs_friendly:
            info_parts.append(fs_friendly)
        info_line = " ".join(info_parts) if info_parts else ""

        if not tool_path:
            # Use raw copy when no partclone tool available
            clone_dd(src_part, dst_part, total_bytes=part.get("size"), title=title_line, subtitle=info_line)
            continue

        display_lines([title_line, info_line])
        with open(dst_part, "wb") as dst_handle:
            run_checked_with_streaming_progress(
                [tool_path, "-s", src_part, "-o", "-", "-F"],
                total_bytes=part.get("size"),
                title=title_line,
                subtitle=info_line,
                stdout_target=dst_handle,
            )


def compute_sha256(device_node, total_bytes=None, title="VERIFY"):
    dd_path = shutil.which("dd")
    sha_path = shutil.which("sha256sum")
    if not dd_path or not sha_path:
        raise RuntimeError("dd or sha256sum not found")
    log_debug(f"Computing sha256 for {device_node}")
    display_lines([title, "Starting..."])
    dd_cmd = [dd_path, f"if={device_node}", "bs=4M", "status=progress"]
    if total_bytes:
        total_bytes = int(total_bytes)
        dd_cmd.extend([f"count={total_bytes}", "iflag=count_bytes"])
    dd_proc = subprocess.Popen(
        dd_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    sha_proc = subprocess.Popen(
        [sha_path],
        stdin=dd_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if dd_proc.stdout:
        dd_proc.stdout.close()
    last_update = time.time()
    while True:
        line = dd_proc.stderr.readline()
        if line:
            log_debug(f"dd: {line.strip()}")
            match = re.search(r"(\d+)\s+bytes", line)
            if match:
                bytes_copied = int(match.group(1))
                percent = ""
                if total_bytes:
                    percent = f"{(bytes_copied / total_bytes) * 100:.1f}%"
                display_lines([title, f"{human_size(bytes_copied)} {percent}".strip()])
                last_update = time.time()
        if dd_proc.poll() is not None:
            break
        if time.time() - last_update > 5:
            display_lines([title, "Working..."])
            last_update = time.time()
    dd_proc.wait()
    sha_out, sha_err = sha_proc.communicate()
    if dd_proc.returncode != 0:
        error_output = dd_proc.stderr.read().strip()
        message = error_output.splitlines()[-1] if error_output else "dd failed"
        raise RuntimeError(message)
    if sha_proc.returncode != 0:
        message = sha_err.strip() or "sha256sum failed"
        raise RuntimeError(message)
    checksum = sha_out.split()[0] if sha_out else ""
    display_lines([title, "Complete"])
    log_debug(f"sha256 for {device_node}: {checksum}")
    return checksum


def verify_clone(source, target):
    source_node = resolve_device_node(source)
    target_node = resolve_device_node(target)
    source_name = os.path.basename(source_node)
    target_name = os.path.basename(target_node)
    source_device = get_device_by_name(source_name) or (source if isinstance(source, dict) else None)
    target_device = get_device_by_name(target_name) or (target if isinstance(target, dict) else None)
    if not source_device or not target_device:
        return verify_clone_device(source_node, target_node, source.get("size") if isinstance(source, dict) else None)
    source_parts = [child for child in get_children(source_device) if child.get("type") == "part"]
    if not source_parts:
        return verify_clone_device(source_node, target_node, source_device.get("size"))
    target_parts = [child for child in get_children(target_device) if child.get("type") == "part"]
    target_parts_by_number = {}
    for child in target_parts:
        part_number = get_partition_number(child.get("name"))
        if part_number is None:
            continue
        target_parts_by_number.setdefault(part_number, child)
    total_parts = len(source_parts)
    for index, part in enumerate(source_parts, start=1):
        src_part = f"/dev/{part.get('name')}"
        part_number = get_partition_number(part.get("name"))
        dst_part = None
        if part_number is not None:
            target_part = target_parts_by_number.get(part_number)
            if target_part:
                dst_part = f"/dev/{target_part.get('name')}"
        if not dst_part and index - 1 < len(target_parts):
            dst_part = f"/dev/{target_parts[index - 1].get('name')}"
        if not dst_part:
            display_lines(["VERIFY", "No target part"])
            log_debug(f"Verify failed: no target partition for {src_part}")
            return False
        print(f"Verifying {src_part} -> {dst_part}")
        try:
            src_hash = compute_sha256(src_part, total_bytes=part.get("size"), title=f"V {index}/{total_parts} SRC")
            dst_hash = compute_sha256(dst_part, total_bytes=part.get("size"), title=f"V {index}/{total_parts} DST")
        except RuntimeError as error:
            display_lines(["VERIFY", "Error"])
            log_debug(f"Verify failed ({src_part} -> {dst_part}): {error}")
            return False
        if src_hash != dst_hash:
            display_lines(["VERIFY", "Mismatch"])
            log_debug(f"Verify mismatch for {src_part} -> {dst_part}")
            print(f"Verify failed: {src_part} -> {dst_part}")
            return False
    display_lines(["VERIFY", "Complete"])
    print("Verify complete: all partitions match")
    return True


def verify_clone_device(source_node, target_node, total_bytes=None):
    print(f"Verifying {source_node} -> {target_node}")
    try:
        src_hash = compute_sha256(source_node, total_bytes=total_bytes, title="VERIFY SRC")
        dst_hash = compute_sha256(target_node, total_bytes=total_bytes, title="VERIFY DST")
    except RuntimeError as error:
        display_lines(["VERIFY", "Error"])
        log_debug(f"Verify failed: {error}")
        return False
    if src_hash != dst_hash:
        display_lines(["VERIFY", "Mismatch"])
        log_debug(f"Verify mismatch for {source_node} -> {target_node}")
        print("Verify failed: checksum mismatch")
        return False
    display_lines(["VERIFY", "Complete"])
    print("Verify complete: checksums match")
    return True


def clone_device(source, target, mode=None):
    if mode is None:
        mode = os.environ.get("CLONE_MODE", "smart")
    mode = normalize_clone_mode(mode)
    if mode in ("smart", "verify"):
        success = clone_device_smart(source, target)
        if not success:
            return False
        if mode == "verify":
            return verify_clone(source, target)
        return True
    unmount_device(target)
    try:
        clone_dd(source, target, total_bytes=source.get("size"), title="CLONING")
    except RuntimeError as error:
        display_lines(["FAILED", str(error)[:20]])
        log_debug(f"Clone failed: {error}")
        return False
    return True


def clone_device_smart(source, target):
    source_node = f"/dev/{source.get('name')}"
    target_node = f"/dev/{target.get('name')}"
    unmount_device(target)
    try:
        display_lines(["CLONING", "Copy table"])
        copy_partition_table(source, target)
    except RuntimeError as error:
        display_lines(["FAILED", "Partition tbl"])
        log_debug(f"Partition table copy failed: {error}")
        return False
    try:
        clone_partclone(source, target)
    except RuntimeError as error:
        display_lines(["FAILED", str(error)[:20]])
        log_debug(f"Smart clone failed ({source_node} -> {target_node}): {error}")
        return False
    display_lines(["CLONING", "Complete"])
    log_debug(f"Smart clone completed from {source_node} to {target_node}")
    return True


def erase_device(target, mode):
    target_node = f"/dev/{target.get('name')}"
    unmount_device(target)
    mode = (mode or "").lower()
    device_label = format_device_label(target)
    mode_label = mode.upper() if mode else None
    if mode == "secure":
        shred_path = shutil.which("shred")
        if not shred_path:
            display_lines(["ERROR", "no shred tool"])
            log_debug("Erase failed: shred not available")
            return False
        return run_progress_command(
            [shred_path, "-v", "-n", "1", "-z", target_node],
            total_bytes=target.get("size"),
            title="ERASING",
            device_label=device_label,
            mode_label=mode_label,
        )
    if mode == "discard":
        discard_path = shutil.which("blkdiscard")
        if not discard_path:
            display_lines(["ERROR", "no discard"])
            log_debug("Erase failed: blkdiscard not available")
            return False
        return run_progress_command(
            [discard_path, target_node],
            title="ERASING",
            device_label=device_label,
            mode_label=mode_label,
        )
    if mode == "zero":
        dd_path = shutil.which("dd")
        if not dd_path:
            display_lines(["ERROR", "no dd tool"])
            log_debug("Erase failed: dd not available")
            return False
        return run_progress_command(
            [dd_path, "if=/dev/zero", f"of={target_node}", "bs=4M", "status=progress", "conv=fsync"],
            total_bytes=target.get("size"),
            title="ERASING",
            device_label=device_label,
            mode_label=mode_label,
        )
    if mode != "quick":
        display_lines(["ERROR", "unknown mode"])
        log_debug(f"Erase failed: unknown mode {mode}")
        return False
    wipefs_path = shutil.which("wipefs")
    if not wipefs_path:
        display_lines(["ERROR", "no wipefs"])
        log_debug("Erase failed: wipefs not available")
        return False
    dd_path = shutil.which("dd")
    if not dd_path:
        display_lines(["ERROR", "no dd tool"])
        log_debug("Erase failed: dd not available")
        return False
    if not run_progress_command(
        [wipefs_path, "-a", target_node],
        title="ERASING",
        device_label=device_label,
        mode_label=mode_label,
    ):
        return False
    size_bytes = target.get("size") or 0
    bytes_per_mib = 1024 * 1024
    size_mib = size_bytes // bytes_per_mib if size_bytes else 0
    wipe_mib = min(app_state.QUICK_WIPE_MIB, size_mib) if size_mib else app_state.QUICK_WIPE_MIB
    wipe_bytes = wipe_mib * bytes_per_mib
    if not run_progress_command(
        [dd_path, "if=/dev/zero", f"of={target_node}", "bs=1M", f"count={wipe_mib}", "status=progress", "conv=fsync"],
        total_bytes=wipe_bytes,
        title="ERASING",
        device_label=device_label,
        mode_label=mode_label,
    ):
        return False
    if size_mib > wipe_mib:
        seek_mib = size_mib - wipe_mib
        return run_progress_command(
            [
                dd_path,
                "if=/dev/zero",
                f"of={target_node}",
                "bs=1M",
                f"count={wipe_mib}",
                f"seek={seek_mib}",
                "status=progress",
                "conv=fsync",
            ],
            total_bytes=wipe_bytes,
            title="ERASING",
            device_label=device_label,
            mode_label=mode_label,
        )
    return True
