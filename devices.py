import json
import re
import subprocess
from typing import Callable, Iterable, Optional

ROOT_MOUNTPOINTS = {"/", "/boot", "/boot/firmware"}

_log_debug: Callable[[str], None]
_error_handler: Optional[Callable[[Iterable[str]], None]]


def _noop_logger(message: str) -> None:
    return None


_log_debug = _noop_logger
_error_handler = None


def configure_device_helpers(
    log_debug: Optional[Callable[[str], None]] = None,
    error_handler: Optional[Callable[[Iterable[str]], None]] = None,
) -> None:
    global _log_debug, _error_handler
    _log_debug = log_debug or _noop_logger
    _error_handler = error_handler


def run_command(command, check=True):
    _log_debug(f"Running command: {' '.join(command)}")
    try:
        result = subprocess.run(command, check=check, text=True, capture_output=True)
    except subprocess.CalledProcessError as error:
        _log_debug(f"Command failed: {' '.join(command)}")
        if error.stdout:
            _log_debug(f"stdout: {error.stdout.strip()}")
        if error.stderr:
            _log_debug(f"stderr: {error.stderr.strip()}")
        raise
    if result.stdout:
        _log_debug(f"stdout: {result.stdout.strip()}")
    if result.stderr:
        _log_debug(f"stderr: {result.stderr.strip()}")
    _log_debug(f"Command completed with return code {result.returncode}")
    return result


def human_size(size_bytes):
    if size_bytes is None:
        return "0B"
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}PB"


def format_device_label(device):
    if isinstance(device, dict):
        name = device.get("name") or ""
        size_label = human_size(device.get("size"))
    else:
        name = str(device or "")
        size_label = ""
    if size_label:
        size_label = re.sub(r"\.0([A-Z])", r"\1", size_label)
        return f"{name} {size_label}".strip()
    return name


def get_block_devices():
    try:
        result = run_command(
            ["lsblk", "-J", "-b", "-o", "NAME,TYPE,SIZE,MODEL,VENDOR,TRAN,RM,MOUNTPOINT,FSTYPE,LABEL"]
        )
        data = json.loads(result.stdout)
        return data.get("blockdevices", [])
    except (subprocess.CalledProcessError, json.JSONDecodeError) as error:
        if _error_handler:
            _error_handler(["LSBLK ERROR", str(error)])
        _log_debug(f"lsblk failed: {error}")
        return []


def get_children(device):
    return device.get("children", []) or []


def get_device_by_name(name):
    if not name:
        return None
    for device in get_block_devices():
        if device.get("name") == name:
            return device
    return None


def has_root_mountpoint(device):
    mountpoint = device.get("mountpoint")
    if mountpoint in ROOT_MOUNTPOINTS:
        return True
    for child in get_children(device):
        if has_root_mountpoint(child):
            return True
    return False


def is_root_device(device):
    if device.get("type") != "disk":
        return False
    return has_root_mountpoint(device)


def list_usb_disks():
    devices = []
    for device in get_block_devices():
        if device.get("type") != "disk":
            continue
        if is_root_device(device):
            continue
        tran = device.get("tran")
        rm = device.get("rm")
        if tran == "usb" or rm == 1:
            devices.append(device)
    return devices


def unmount_device(device):
    mountpoint = device.get("mountpoint")
    if mountpoint:
        try:
            run_command(["umount", mountpoint], check=False)
        except subprocess.CalledProcessError:
            pass
    for child in get_children(device):
        mountpoint = child.get("mountpoint")
        if mountpoint:
            try:
                run_command(["umount", mountpoint], check=False)
            except subprocess.CalledProcessError:
                pass
