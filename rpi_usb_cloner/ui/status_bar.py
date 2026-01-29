"""Status bar indicators for the OLED footer.

This module provides a comprehensive status bar system that displays
multiple status indicators on the right side of the footer, similar
to a system tray or status area.

Indicators use small 7px icons where available, with text fallback
for drive counts.

Icon indicators (from right to left by priority):
- Drive counts: U2|R1 (USB count, Repo count) - text
- Bluetooth: 7px-bluetooth.png when connected
- WiFi: 7px-wifi.png when connected
- Web Server: 7px-pointer.png when running
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpi_usb_cloner.app.context import AppContext


# Path to assets folder
ASSETS_PATH = Path(__file__).parent / "assets"

# Icon paths (7px high icons for status bar)
ICON_WIFI = ASSETS_PATH / "7px-wifi.png"
ICON_BLUETOOTH = ASSETS_PATH / "7px-bluetooth.png"
ICON_POINTER = ASSETS_PATH / "7px-pointer.png"
ICON_GLOBE = ASSETS_PATH / "7px-globe.png"


@dataclass(frozen=True)
class StatusIndicator:
    """A single status indicator to display in the status bar."""

    label: str
    """Short label text (e.g., "U2") for text-based indicators."""

    priority: int = 0
    """Lower priority = further right. Higher priority = closer to text."""

    inverted: bool = False
    """If True, draw white on black background (default status style).
    If False, draw black on white background (highlighted/warning)."""

    icon_path: Path | None = None
    """Path to icon image file. If set, renders icon instead of text label."""

    @property
    def is_icon(self) -> bool:
        """Return True if this indicator uses an icon."""
        return self.icon_path is not None and self.icon_path.exists()


def get_bluetooth_indicator() -> StatusIndicator | None:
    """Get Bluetooth status indicator.

    Returns:
        StatusIndicator with Bluetooth icon, or None if not connected.
    """
    try:
        # Check if bluetooth is connected
        # For now, check if any bluetooth device is connected via bluetoothctl
        import subprocess

        result = subprocess.run(
            ["bluetoothctl", "devices", "Connected"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        # If there are connected devices, the output won't be empty
        if result.returncode == 0 and result.stdout.strip():
            return StatusIndicator(
                label="BT",
                priority=25,
                icon_path=ICON_BLUETOOTH,
            )
    except Exception:
        pass
    return None


def get_wifi_indicator() -> StatusIndicator | None:
    """Get WiFi status indicator.

    Returns:
        StatusIndicator with WiFi icon, or None if not connected.
    """
    try:
        from rpi_usb_cloner.services.wifi import get_status_cached

        status = get_status_cached(ttl_s=2.0)
        if status.get("connected"):
            return StatusIndicator(
                label="W",
                priority=30,
                icon_path=ICON_WIFI,
            )
    except Exception:
        pass
    return None


def get_web_server_indicator() -> StatusIndicator | None:
    """Get web server status indicator.

    Returns:
        StatusIndicator with pointer icon if web server is running, None otherwise.
    """
    try:
        from rpi_usb_cloner.web.server import is_running

        if is_running():
            return StatusIndicator(
                label="WEB",
                priority=20,
                icon_path=ICON_POINTER,
            )
    except Exception:
        pass
    return None


def get_operation_indicator(app_context: AppContext | None = None) -> StatusIndicator | None:
    """Get operation status indicator.

    Note: Currently disabled/hidden per user request.

    Args:
        app_context: Application context to check operation_active state.

    Returns:
        None (indicator is currently hidden).
    """
    # Hidden for now per user request
    return None


def get_drive_indicators() -> list[StatusIndicator]:
    """Get drive count indicators.

    Returns:
        List of StatusIndicators for USB and Repo counts (solid black boxes with white text).
    """
    indicators: list[StatusIndicator] = []
    try:
        from rpi_usb_cloner.services.drives import get_drive_counts

        usb_count, repo_count = get_drive_counts()
        # Lower priority = further right
        # inverted=True gives solid black box with white text (original style)
        if repo_count > 0:
            indicators.append(StatusIndicator(label=f"R{repo_count}", priority=1, inverted=True))
        if usb_count > 0:
            indicators.append(StatusIndicator(label=f"U{usb_count}", priority=0, inverted=True))
    except Exception:
        pass
    return indicators


def collect_status_indicators(
    app_context: AppContext | None = None,
    *,
    include_bluetooth: bool = True,
    include_wifi: bool = True,
    include_web: bool = True,
    include_operation: bool = False,  # Hidden by default
    include_drives: bool = True,
) -> list[StatusIndicator]:
    """Collect all active status indicators.

    Args:
        app_context: Application context for operation status.
        include_bluetooth: Whether to include Bluetooth indicator.
        include_wifi: Whether to include WiFi indicator.
        include_web: Whether to include web server indicator.
        include_operation: Whether to include operation indicator (hidden by default).
        include_drives: Whether to include drive count indicators.

    Returns:
        List of StatusIndicators sorted by priority (lowest first = rightmost).
    """
    indicators: list[StatusIndicator] = []

    if include_drives:
        indicators.extend(get_drive_indicators())

    if include_operation:
        op_indicator = get_operation_indicator(app_context)
        if op_indicator:
            indicators.append(op_indicator)

    if include_web:
        web_indicator = get_web_server_indicator()
        if web_indicator:
            indicators.append(web_indicator)

    if include_bluetooth:
        bt_indicator = get_bluetooth_indicator()
        if bt_indicator:
            indicators.append(bt_indicator)

    if include_wifi:
        wifi_indicator = get_wifi_indicator()
        if wifi_indicator:
            indicators.append(wifi_indicator)

    # Sort by priority (lowest first = rightmost in display)
    indicators.sort(key=lambda x: x.priority)
    return indicators
