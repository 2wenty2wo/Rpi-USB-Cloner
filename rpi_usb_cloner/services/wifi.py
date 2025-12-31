from __future__ import annotations

import re
import time
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


def _format_command(command: Sequence[str], redactions: Optional[Iterable[int]] = None) -> str:
    if not redactions:
        return " ".join(command)
    redacted_indexes = set(redactions)
    redacted_parts = [
        "******" if index in redacted_indexes else part for index, part in enumerate(command)
    ]
    return " ".join(redacted_parts)


def _nmcli_unescape(value: str) -> str:
    if not value:
        return value
    unescaped = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            next_char = value[index + 1]
            if next_char in {":", "|", "\\"}:
                unescaped.append(next_char)
                index += 2
                continue
        unescaped.append(char)
        index += 1
    return "".join(unescaped)


def _split_nmcli_line(line: str, separator: str = ":", maxsplit: int = 3) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    index = 0
    splits = 0
    while index < len(line):
        char = line[index]
        if char == "\\" and index + 1 < len(line):
            current.append(char)
            current.append(line[index + 1])
            index += 2
            continue
        if char == separator and splits < maxsplit:
            parts.append("".join(current))
            current = []
            splits += 1
            index += 1
            continue
        current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def _run_command(
    command: Sequence[str],
    check: bool = True,
    redactions: Optional[Iterable[int]] = None,
) -> subprocess.CompletedProcess[str]:
    runner = _command_runner or _default_runner
    command_display = _format_command(command, redactions)
    _log_debug(f"Running command: {command_display}")
    try:
        result = runner(command, check)
    except subprocess.CalledProcessError as error:
        _log_debug(f"Command failed: {command_display}")
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
    backoff_schedule = [0.0, 0.5, 1.0]

    def _prepare_interface_for_scan() -> None:
        try:
            _run_command(["rfkill", "unblock", "wifi"])
        except FileNotFoundError as error:
            _log_debug(f"rfkill not available: {error}")
        except subprocess.CalledProcessError as error:
            _log_debug(f"rfkill unblock failed: {error}")

        try:
            _run_command(["ip", "link", "set", interface, "up"])
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            _log_debug(f"ip link set up failed: {error}")

    def _parse_signal_line(value: str) -> Optional[int]:
        match = re.search(r"(-?\d+(?:\.\d+)?)", value)
        if not match:
            return None
        try:
            signal_value = int(round(float(match.group(1))))
        except ValueError:
            return None
        if signal_value < 0:
            normalized = (signal_value + 100) * 2
            return max(0, min(100, normalized))
        return signal_value

    def _parse_quality_value(value: str) -> Optional[int]:
        match = re.search(r"(\d+)\s*/\s*(\d+)", value)
        if not match:
            return None
        try:
            current = int(match.group(1))
            total = int(match.group(2))
        except ValueError:
            return None
        if total <= 0:
            return None
        return int(round((current / total) * 100))

    def _parse_iw_scan(output: str) -> List[WifiNetwork]:
        networks: List[WifiNetwork] = []
        current_ssid: Optional[str] = None
        current_signal: Optional[int] = None
        current_secured = False

        def _flush_current() -> None:
            nonlocal current_ssid, current_signal, current_secured
            if current_ssid:
                networks.append(
                    WifiNetwork(
                        ssid=current_ssid,
                        signal=current_signal,
                        secured=current_secured,
                        in_use=False,
                    )
                )
            current_ssid = None
            current_signal = None
            current_secured = False

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if line.startswith("BSS "):
                _flush_current()
                continue
            if line.startswith("SSID:"):
                current_ssid = line.split("SSID:", 1)[1].strip()
                continue
            if line.startswith("signal:"):
                current_signal = _parse_signal_line(line)
                continue
            if line.startswith("RSN:") or line.startswith("WPA:"):
                current_secured = True
                continue
            if line.startswith("capability:") and "Privacy" in line:
                current_secured = True
                continue

        _flush_current()
        return networks

    def _parse_iwlist_scan(output: str) -> List[WifiNetwork]:
        networks: List[WifiNetwork] = []
        current_ssid: Optional[str] = None
        current_signal: Optional[int] = None
        current_secured = False

        def _flush_current() -> None:
            nonlocal current_ssid, current_signal, current_secured
            if current_ssid:
                networks.append(
                    WifiNetwork(
                        ssid=current_ssid,
                        signal=current_signal,
                        secured=current_secured,
                        in_use=False,
                    )
                )
            current_ssid = None
            current_signal = None
            current_secured = False

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if line.startswith("Cell "):
                _flush_current()
                continue
            if "ESSID:" in line:
                match = re.search(r'ESSID:"(.*)"', line)
                if match:
                    current_ssid = match.group(1)
                continue
            if "Signal level" in line:
                signal_match = re.search(r"Signal level[=:-]\s*(-?\d+)", line)
                if signal_match:
                    current_signal = _parse_signal_line(signal_match.group(1))
                elif "Quality" in line:
                    quality_match = re.search(r"Quality[=:-]\s*([\d/]+)", line)
                    if quality_match:
                        current_signal = _parse_quality_value(quality_match.group(1))
                continue
            if line.startswith("Quality"):
                quality_match = re.search(r"Quality[=:-]\s*([\d/]+)", line)
                if quality_match:
                    current_signal = _parse_quality_value(quality_match.group(1))
                continue
            if "Encryption key:" in line and "on" in line:
                current_secured = True

        _flush_current()
        return networks

    def _scan_with_iw() -> List[WifiNetwork]:
        iw_command = ["iw", "dev", interface, "scan"]
        iw_command_display = _format_command(iw_command)
        try:
            _log_debug(f"Running command: {iw_command_display}")
            result = subprocess.run(
                iw_command,
                check=True,
                text=True,
                capture_output=True,
                timeout=10,
            )
            if result.stdout:
                _log_debug(f"stdout: {result.stdout.strip()}")
            if result.stderr:
                _log_debug(f"stderr: {result.stderr.strip()}")
            _log_debug(f"Command completed with return code {result.returncode}")
            networks = _parse_iw_scan(result.stdout)
            if networks:
                return networks
        except subprocess.TimeoutExpired:
            _log_debug("iw scan timed out")
            _notify_error("Wi-Fi scan timed out.")
            return []
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            _log_debug(f"iw scan failed: {error}")
            if isinstance(error, subprocess.CalledProcessError):
                if error.stdout:
                    _log_debug(f"stdout: {error.stdout.strip()}")
                if error.stderr:
                    _log_debug(f"stderr: {error.stderr.strip()}")

        try:
            result = _run_command(["iwlist", interface, "scan"])
            networks = _parse_iwlist_scan(result.stdout)
            if networks:
                return networks
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            _log_debug(f"iwlist scan failed: {error}")

        _notify_error("No Wi-Fi networks found.")
        return []

    _prepare_interface_for_scan()

    for delay in backoff_schedule:
        if delay:
            time.sleep(delay)
        try:
            result = _run_command(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "SSID,SIGNAL,SECURITY,IN-USE",
                    "dev",
                    "wifi",
                    "list",
                    "--rescan",
                    "yes",
                    "ifname",
                    interface,
                ]
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            _log_debug(f"nmcli scan failed: {error}")
            return _scan_with_iw()

        if not result.stdout.strip():
            _log_debug("nmcli stdout empty or whitespace-only; nmcli returned no APs.")

        networks: List[WifiNetwork] = []
        non_empty_ssid = False
        for line in result.stdout.splitlines():
            if not line:
                continue
            parts = _split_nmcli_line(line, separator=":")
            ssid = _nmcli_unescape(parts[0]) if parts else ""
            if ssid:
                non_empty_ssid = True
            signal_value = None
            if len(parts) > 1 and parts[1].isdigit():
                signal_value = int(parts[1])
            security = _nmcli_unescape(parts[2]) if len(parts) > 2 else ""
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
            _log_debug(
                "nmcli parsing produced no networks; retrying nmcli before falling back."
            )
            continue
        if networks and non_empty_ssid:
            return networks

    return _scan_with_iw()


def connect(ssid: str, password: Optional[str] = None) -> bool:
    interface = _select_active_interface()
    if not interface:
        return False
    if not ssid:
        _notify_error("Wi-Fi connect failed: SSID is required.")
        return False

    def _active_ssid_matches() -> bool:
        try:
            result = _run_command(
                ["nmcli", "-t", "-f", "ACTIVE,SSID,DEVICE", "dev", "wifi"]
            )
            for line in result.stdout.splitlines():
                if not line:
                    continue
                parts = _split_nmcli_line(line, separator=":", maxsplit=2)
                active = parts[0].strip().lower() if parts else ""
                current_ssid = _nmcli_unescape(parts[1]) if len(parts) > 1 else ""
                device = parts[2].strip() if len(parts) > 2 else ""
                if active == "yes" and device == interface and current_ssid == ssid:
                    return True
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            _log_debug(f"nmcli active SSID lookup failed: {error}")

        try:
            result = _run_command(["iw", "dev"])
            current_interface = None
            for raw_line in result.stdout.splitlines():
                line = raw_line.strip()
                if line.startswith("Interface"):
                    parts = line.split()
                    current_interface = parts[1] if len(parts) > 1 else None
                    continue
                if current_interface == interface and line.startswith("ssid "):
                    current_ssid = line.split("ssid", 1)[1].strip()
                    if current_ssid == ssid:
                        return True
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            _log_debug(f"iw dev SSID lookup failed: {error}")

        return False

    if _active_ssid_matches():
        _log_debug(f"Already connected to SSID {ssid} on {interface}")
        return True

    if not password:
        command = ["nmcli", "dev", "wifi", "connect", ssid, "ifname", interface]
        try:
            _run_command(command)
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            _notify_error(f"Wi-Fi connect failed: {error}")
            return False
        return True

    connection_name = ssid

    def _connection_exists() -> bool:
        result = _run_command(["nmcli", "-t", "-f", "NAME", "connection", "show"])
        return any(
            _nmcli_unescape(line) == connection_name
            for line in result.stdout.splitlines()
        )

    redactions = [7]
    try:
        if _connection_exists():
            _run_command(
                [
                    "nmcli",
                    "connection",
                    "modify",
                    connection_name,
                    "802-11-wireless-security.key-mgmt",
                    "wpa-psk",
                    "802-11-wireless-security.psk",
                    password,
                ],
                redactions=redactions,
            )
        else:
            _run_command(
                [
                    "nmcli",
                    "connection",
                    "add",
                    "type",
                    "wifi",
                    "ifname",
                    interface,
                    "con-name",
                    connection_name,
                    "ssid",
                    ssid,
                ]
            )
            _run_command(
                [
                    "nmcli",
                    "connection",
                    "modify",
                    connection_name,
                    "802-11-wireless-security.key-mgmt",
                    "wpa-psk",
                    "802-11-wireless-security.psk",
                    password,
                ],
                redactions=redactions,
            )
        _run_command(["nmcli", "connection", "up", connection_name])
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
