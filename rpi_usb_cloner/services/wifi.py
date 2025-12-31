from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence

_log_debug: Callable[[str], None]
_error_handler: Optional[Callable[[Iterable[str]], None]]
_command_runner: Optional[Callable[[Sequence[str], bool], subprocess.CompletedProcess[str]]]


def _noop_logger(message: str) -> None:
    return None


_log_debug = _noop_logger
_error_handler = None
_command_runner = None


def configure_wifi_helpers(
    log_debug: Optional[Callable[[str], None]] = None,
    error_handler: Optional[Callable[[Iterable[str]], None]] = None,
    command_runner: Optional[
        Callable[[Sequence[str], bool], subprocess.CompletedProcess[str]]
    ] = None,
) -> None:
    global _log_debug, _error_handler, _command_runner
    _log_debug = log_debug or _noop_logger
    _error_handler = error_handler
    _command_runner = command_runner


def _default_runner(command: Sequence[str], check: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, text=True, capture_output=True)


def _run_command(command: Sequence[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    runner = _command_runner or _default_runner
    _log_debug(f"Running command: {' '.join(command)}")
    try:
        result = runner(command, check)
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


def _notify_error(message: str) -> None:
    _log_debug(message)
    if _error_handler:
        _error_handler(["WIFI ERROR", message])


def list_wifi_interfaces() -> List[str]:
    interfaces: List[str] = []
    try:
        result = _run_command(["iw", "dev"])
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Interface"):
                parts = line.split()
                if len(parts) >= 2:
                    interfaces.append(parts[1])
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        _log_debug(f"iw dev failed: {error}")
    if interfaces:
        return interfaces

    try:
        result = _run_command(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"])
        for line in result.stdout.splitlines():
            if not line:
                continue
            device, device_type = (line.split(":", 1) + [""])[:2]
            if device_type == "wifi" and device:
                interfaces.append(device)
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        _log_debug(f"nmcli device status failed: {error}")

    if not interfaces:
        _notify_error("No Wi-Fi interfaces detected.")
    return interfaces


def _select_active_interface() -> Optional[str]:
    interfaces = list_wifi_interfaces()
    if not interfaces:
        return None
    try:
        result = _run_command(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
        for line in result.stdout.splitlines():
            if not line:
                continue
            parts = line.split(":")
            if len(parts) < 3:
                continue
            device, device_type, state = parts[0], parts[1], parts[2]
            if device_type == "wifi" and state == "connected" and device in interfaces:
                return device
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        _log_debug(f"nmcli device status failed: {error}")
    return interfaces[0]


@dataclass(frozen=True)
class WifiNetwork:
    ssid: str
    signal: Optional[int]
    secured: bool
    in_use: bool


def list_networks() -> List[WifiNetwork]:
    interface = _select_active_interface()
    if not interface:
        return []
    try:
        result = _run_command(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "dev", "wifi", "list", "ifname", interface]
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        _notify_error(f"Wi-Fi scan failed: {error}")
        return []

    networks: List[WifiNetwork] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        parts = line.split(":")
        ssid = parts[0] if parts else ""
        signal_value = None
        if len(parts) > 1 and parts[1].isdigit():
            signal_value = int(parts[1])
        security = parts[2] if len(parts) > 2 else ""
        in_use = len(parts) > 3 and parts[3].strip() == "*"
        networks.append(
            WifiNetwork(
                ssid=ssid,
                signal=signal_value,
                secured=bool(security and security != "--"),
                in_use=in_use,
            )
        )
    if not networks:
        _notify_error("No Wi-Fi networks found.")
    return networks


def connect(ssid: str, password: Optional[str] = None) -> bool:
    interface = _select_active_interface()
    if not interface:
        return False
    if not ssid:
        _notify_error("Wi-Fi connect failed: SSID is required.")
        return False

    command = ["nmcli", "dev", "wifi", "connect", ssid, "ifname", interface]
    if password:
        command.extend(["password", password])
    try:
        _run_command(command)
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        _notify_error(f"Wi-Fi connect failed: {error}")
        return False
    return True


def disconnect() -> bool:
    interface = _select_active_interface()
    if not interface:
        return False
    try:
        _run_command(["nmcli", "dev", "disconnect", interface])
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        _notify_error(f"Wi-Fi disconnect failed: {error}")
        return False
    return True


def get_ip_address() -> Optional[str]:
    interface = _select_active_interface()
    if not interface:
        return None
    try:
        result = _run_command(["ip", "-4", "addr", "show", "dev", interface])
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        _notify_error(f"IP address lookup failed: {error}")
        return None

    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
    if match:
        return match.group(1)
    _notify_error("No IPv4 address assigned.")
    return None
