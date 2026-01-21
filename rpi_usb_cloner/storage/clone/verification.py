"""Device verification using SHA256 checksums."""

import os
import re
import shutil
import subprocess
import time
from typing import Any, Optional, Union

from rpi_usb_cloner.logging import get_logger
from rpi_usb_cloner.storage.devices import get_children, get_device_by_name, human_size
from rpi_usb_cloner.ui.display import display_lines

from .models import get_partition_number, resolve_device_node

log = get_logger(source=__name__, tags=["verify"])


def compute_sha256(
    device_node: str,
    total_bytes: Optional[Union[int, float, str]] = None,
    title: str = "VERIFY",
) -> str:
    """Compute SHA256 checksum of a device or partition."""
    dd_path = shutil.which("dd")
    sha_path = shutil.which("sha256sum")
    if not dd_path or not sha_path:
        raise RuntimeError("dd or sha256sum not found")
    log.debug(f"Computing sha256 for {device_node}")
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
            log.debug(f"dd: {line.strip()}")
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
    log.debug(f"sha256 for {device_node}: {checksum}")
    return checksum


def verify_clone(
    source: Union[str, dict[str, Any]], target: Union[str, dict[str, Any]]
) -> bool:
    """Verify that target matches source using SHA256 checksums.

    Verifies each partition individually for partition-based clones,
    or the entire device for raw clones.

    Args:
        source: Source device dict or path
        target: Target device dict or path

    Returns:
        True if verification succeeds, False otherwise
    """
    source_node = resolve_device_node(source)
    target_node = resolve_device_node(target)
    source_name = os.path.basename(source_node)
    target_name = os.path.basename(target_node)
    source_device = get_device_by_name(source_name) or (
        source if isinstance(source, dict) else None
    )
    target_device = get_device_by_name(target_name) or (
        target if isinstance(target, dict) else None
    )
    if not source_device or not target_device:
        return verify_clone_device(
            source_node,
            target_node,
            source.get("size") if isinstance(source, dict) else None,
        )
    source_parts = [
        child for child in get_children(source_device) if child.get("type") == "part"
    ]
    if not source_parts:
        return verify_clone_device(source_node, target_node, source_device.get("size"))
    target_parts = [
        child for child in get_children(target_device) if child.get("type") == "part"
    ]
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
            log.error(f"Verify failed: no target partition for {src_part}")
            return False
        log.info(f"Verifying {src_part} -> {dst_part}")
        try:
            src_hash = compute_sha256(
                src_part,
                total_bytes=part.get("size"),
                title=f"V {index}/{total_parts} SRC",
            )
            dst_hash = compute_sha256(
                dst_part,
                total_bytes=part.get("size"),
                title=f"V {index}/{total_parts} DST",
            )
        except RuntimeError as error:
            display_lines(["VERIFY", "Error"])
            log.error(f"Verify failed ({src_part} -> {dst_part}): {error}")
            return False
        if src_hash != dst_hash:
            display_lines(["VERIFY", "Mismatch"])
            log.error(f"Verify mismatch for {src_part} -> {dst_part}")
            log.error(f"Verify failed: {src_part} -> {dst_part}")
            return False
    display_lines(["VERIFY", "Complete"])
    log.info("Verify complete: all partitions match")
    return True


def verify_clone_device(
    source_node: str,
    target_node: str,
    total_bytes: Optional[Union[int, float, str]] = None,
) -> bool:
    """Verify entire device using SHA256 checksums.

    Args:
        source_node: Source device node path
        target_node: Target device node path
        total_bytes: Optional size limit for verification

    Returns:
        True if verification succeeds, False otherwise
    """
    log.info(f"Verifying {source_node} -> {target_node}")
    try:
        src_hash = compute_sha256(
            source_node, total_bytes=total_bytes, title="VERIFY SRC"
        )
        dst_hash = compute_sha256(
            target_node, total_bytes=total_bytes, title="VERIFY DST"
        )
    except RuntimeError as error:
        display_lines(["VERIFY", "Error"])
        log.error(f"Verify failed: {error}")
        return False
    if src_hash != dst_hash:
        display_lines(["VERIFY", "Mismatch"])
        log.error(f"Verify mismatch for {source_node} -> {target_node}")
        log.error("Verify failed: checksum mismatch")
        return False
    display_lines(["VERIFY", "Complete"])
    log.info("Verify complete: checksums match")
    return True
