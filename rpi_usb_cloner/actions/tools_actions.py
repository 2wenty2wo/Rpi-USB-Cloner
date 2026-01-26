from __future__ import annotations

import platform
from pathlib import Path

import psutil

from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.ui import screens
from rpi_usb_cloner.ui.icons import ACTIVITY_ICON


def coming_soon() -> None:
    screens.show_coming_soon(title="TOOLS")


def _format_bytes(num_bytes: int) -> str:
    """Format bytes to human readable string."""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024.0:
            return f"{value:.1f}{unit}"
        value /= 1024.0
    return f"{value:.1f}PB"


def _get_cpu_temp() -> float | None:
    """Get CPU temperature on Raspberry Pi."""
    try:
        # Try reading from thermal zone (Linux)
        temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if temp_path.exists():
            with temp_path.open() as f:
                return float(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        pass
    return None


def system_info(*, app_context: AppContext) -> None:
    """Display system information (CPU, memory, storage, temperature)."""
    lines: list[tuple[str, str]] = []

    # CPU info
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_count = psutil.cpu_count() or 1
    lines.append(("CPU:", f"{cpu_percent:.1f}% ({cpu_count} cores)"))

    # CPU temperature
    cpu_temp = _get_cpu_temp()
    if cpu_temp is not None:
        lines.append(("Temp:", f"{cpu_temp:.1f}C"))

    # Memory info
    mem = psutil.virtual_memory()
    mem_used = _format_bytes(mem.used)
    mem_total = _format_bytes(mem.total)
    lines.append(("RAM:", f"{mem_used}/{mem_total}"))
    lines.append(("RAM:", f"{mem.percent:.1f}% used"))

    # Disk info (root filesystem)
    try:
        disk = psutil.disk_usage("/")
        disk_used = _format_bytes(disk.used)
        disk_total = _format_bytes(disk.total)
        lines.append(("Disk:", f"{disk_used}/{disk_total}"))
        lines.append(("Disk:", f"{disk.percent:.1f}% used"))
    except OSError:
        lines.append(("Disk:", "unavailable"))

    # System uptime
    try:
        boot_time = psutil.boot_time()
        import time

        uptime_secs = int(time.time() - boot_time)
        hours, remainder = divmod(uptime_secs, 3600)
        minutes, _ = divmod(remainder, 60)
        lines.append(("Uptime:", f"{hours}h {minutes}m"))
    except (OSError, AttributeError):
        pass

    # Platform info
    lines.append(("OS:", f"{platform.system()}"))
    lines.append(("Python:", f"{platform.python_version()}"))

    screens.wait_for_scrollable_key_value_input(
        "SYSTEM INFO",
        lines,
        title_icon=ACTIVITY_ICON,
    )
