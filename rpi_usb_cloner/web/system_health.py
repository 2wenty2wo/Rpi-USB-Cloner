"""System health monitoring for Raspberry Pi USB Cloner.

Collects CPU, memory, disk, and temperature metrics for display in web UI.
"""

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
    disk_used_gb = disk.used / (1024**3)
    disk_total_gb = disk.total / (1024**3)

    # Temperature
    temperature = get_cpu_temperature()

    return SystemHealth(
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        memory_used_mb=memory_used_mb,
        memory_total_mb=memory_total_mb,
        disk_percent=disk_percent,
        disk_used_gb=disk_used_gb,
        disk_total_gb=disk_total_gb,
        temperature_celsius=temperature,
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
    if temp < 75:
        return "warning"
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
    if percent < 85:
        return "warning"
    return "danger"
