import os
import platform
from typing import Optional

import psutil

from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.ui import screens
from rpi_usb_cloner.ui.icons import INFO_ICON


def coming_soon() -> None:
    screens.show_coming_soon(title="TOOLS")


def _format_bytes(num_bytes: int) -> str:
    """Format bytes to human readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f}PB"


def _get_cpu_temp() -> Optional[float]:
    """Get CPU temperature on Raspberry Pi."""
    try:
        # Try reading from thermal zone (Linux)
        temp_path = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(temp_path):
            with open(temp_path) as f:
                return float(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        pass
    return None


def system_info(*, app_context: AppContext) -> None:
    """Display system information (CPU, memory, storage, temperature)."""
    lines = []

    # CPU info
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_count = psutil.cpu_count() or 1
    lines.append(f"CPU: {cpu_percent:.1f}% ({cpu_count} cores)")

    # CPU temperature
    cpu_temp = _get_cpu_temp()
    if cpu_temp is not None:
        lines.append(f"Temp: {cpu_temp:.1f}C")

    # Memory info
    mem = psutil.virtual_memory()
    mem_used = _format_bytes(mem.used)
    mem_total = _format_bytes(mem.total)
    lines.append(f"RAM: {mem_used}/{mem_total}")
    lines.append(f"RAM: {mem.percent:.1f}% used")

    # Disk info (root filesystem)
    try:
        disk = psutil.disk_usage("/")
        disk_used = _format_bytes(disk.used)
        disk_total = _format_bytes(disk.total)
        lines.append(f"Disk: {disk_used}/{disk_total}")
        lines.append(f"Disk: {disk.percent:.1f}% used")
    except OSError:
        lines.append("Disk: unavailable")

    # System uptime
    try:
        boot_time = psutil.boot_time()
        import time

        uptime_secs = int(time.time() - boot_time)
        hours, remainder = divmod(uptime_secs, 3600)
        minutes, _ = divmod(remainder, 60)
        lines.append(f"Uptime: {hours}h {minutes}m")
    except (OSError, AttributeError):
        pass

    # Platform info
    lines.append(f"OS: {platform.system()}")
    lines.append(f"Python: {platform.python_version()}")

    screens.wait_for_paginated_input(
        "SYSTEM INFO",
        lines,
        title_icon=INFO_ICON,
    )
