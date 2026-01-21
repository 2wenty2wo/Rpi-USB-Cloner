"""System health monitoring for Raspberry Pi USB Cloner.

Collects CPU, memory, disk, and temperature metrics for display in web UI.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil


@dataclass
class SystemHealth:
    """System health metrics."""

    cpu_percent: float
    memory_percent: float
    memory_used_mb: int
    memory_total_mb: int
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    temperature_celsius: Optional[float]
    bluetooth_enabled: bool = False
    bluetooth_active: bool = False
    bluetooth_ip: Optional[str] = None
    bluetooth_paired_count: int = 0


def get_cpu_temperature() -> Optional[float]:
    """Get CPU temperature in Celsius.

    Tries multiple methods to read temperature:
    1. /sys/class/thermal/thermal_zone0/temp (standard Linux)
    2. vcgencmd measure_temp (Raspberry Pi specific)

    Returns:
        Temperature in Celsius, or None if unavailable
    """
    # Try thermal zone (most common on Linux)
    thermal_zone = Path("/sys/class/thermal/thermal_zone0/temp")
    if thermal_zone.exists():
        try:
            temp_str = thermal_zone.read_text().strip()
            # Temperature is in millidegrees
            return float(temp_str) / 1000.0
        except (ValueError, OSError):
            pass

    # Try vcgencmd for Raspberry Pi
    try:
        import subprocess
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        if result.returncode == 0:
            # Output format: temp=42.8'C
            match = re.search(r"temp=([\d.]+)", result.stdout)
            if match:
                return float(match.group(1))
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass

    return None


def get_system_health() -> SystemHealth:
    """Get current system health metrics.

    Returns:
        SystemHealth dataclass with current metrics
    """
    # CPU usage (average across all cores)
    cpu_percent = psutil.cpu_percent(interval=0.1)

    # Memory usage
    memory = psutil.virtual_memory()
    memory_percent = memory.percent
    memory_used_mb = memory.used // (1024 * 1024)
    memory_total_mb = memory.total // (1024 * 1024)

    # Disk usage (root filesystem)
    disk = psutil.disk_usage("/")
    disk_percent = disk.percent
    disk_used_gb = disk.used / (1024 ** 3)
    disk_total_gb = disk.total / (1024 ** 3)

    # Temperature
    temperature = get_cpu_temperature()

    # Bluetooth status
    bluetooth_enabled = False
    bluetooth_active = False
    bluetooth_ip = None
    bluetooth_paired_count = 0

    try:
        from rpi_usb_cloner.config.settings import get_bool
        from rpi_usb_cloner.services.bluetooth import get_bluetooth_status, is_bluetooth_available

        bluetooth_enabled = get_bool("bluetooth_enabled", default=False)

        if is_bluetooth_available():
            status = get_bluetooth_status()
            bluetooth_active = status.pan_active
            bluetooth_ip = status.ip_address
            bluetooth_paired_count = len(status.connected_devices)
    except Exception:
        # Bluetooth module may not be available or may fail
        pass

    return SystemHealth(
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        memory_used_mb=memory_used_mb,
        memory_total_mb=memory_total_mb,
        disk_percent=disk_percent,
        disk_used_gb=disk_used_gb,
        disk_total_gb=disk_total_gb,
        temperature_celsius=temperature,
        bluetooth_enabled=bluetooth_enabled,
        bluetooth_active=bluetooth_active,
        bluetooth_ip=bluetooth_ip,
        bluetooth_paired_count=bluetooth_paired_count,
    )


def get_temperature_status(temp: Optional[float]) -> str:
    """Get color status for temperature.

    Args:
        temp: Temperature in Celsius

    Returns:
        Color status: 'success', 'warning', or 'danger'
    """
    if temp is None:
        return "secondary"

    # Raspberry Pi temperature thresholds
    if temp < 60:
        return "success"
    elif temp < 75:
        return "warning"
    else:
        return "danger"


def get_usage_status(percent: float) -> str:
    """Get color status for usage percentage.

    Args:
        percent: Usage percentage (0-100)

    Returns:
        Color status: 'success', 'warning', or 'danger'
    """
    if percent < 70:
        return "success"
    elif percent < 85:
        return "warning"
    else:
        return "danger"
