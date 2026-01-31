"""QR code display screen for Bluetooth pairing.

This module provides screens that match the app's standard style.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

from rpi_usb_cloner.logging import LoggerFactory
from rpi_usb_cloner.services.bluetooth import (
    generate_qr_data,
    generate_qr_text,
    get_bluetooth_status,
    get_trusted_bluetooth_devices,
)
from rpi_usb_cloner.ui import display, menus
from rpi_usb_cloner.ui.icons import get_screen_icon

if TYPE_CHECKING:
    from rpi_usb_cloner.app.context import AppContext
    from rpi_usb_cloner.ui.display import DisplayContext

log = LoggerFactory.for_menu()

# QR code dimensions
QR_SIZE = 44


def _generate_qr_matrix(data: str, version: int = 2) -> list[list[bool]]:
    """Generate a QR code matrix."""
    try:
        import qrcode

        error_correction = None
        try:
            from qrcode.constants import ERROR_CORRECT_L

            error_correction = ERROR_CORRECT_L
        except Exception:
            pass

        qr_kwargs = {"version": version, "box_size": 1, "border": 2}
        if error_correction is not None:
            qr_kwargs["error_correction"] = error_correction

        qr = qrcode.QRCode(**qr_kwargs)
        qr.add_data(data)
        qr.make(fit=True)

        return [[bool(m) for m in row] for row in qr.modules]
    except ImportError:
        pass

    # Fallback pattern
    size = 21 if version == 1 else 25 if version == 2 else 29
    matrix = [[False] * size for _ in range(size)]

    def draw_finder(x: int, y: int) -> None:
        for dy in range(7):
            for dx in range(7):
                if dy == 0 or dy == 6 or dx == 0 or dx == 6:
                    matrix[y + dy][x + dx] = True
                elif 2 <= dy <= 4 and 2 <= dx <= 4:
                    matrix[y + dy][x + dx] = True

    draw_finder(0, 0)
    draw_finder(size - 7, 0)
    draw_finder(0, size - 7)

    for i in range(8, size - 8):
        matrix[6][i] = i % 2 == 0
        matrix[i][6] = i % 2 == 0

    matrix[size - 8][8] = True

    data_hash = sum(ord(c) * (i + 1) for i, c in enumerate(data))
    for y in range(size):
        for x in range(size):
            if not matrix[y][x]:
                idx = y * size + x
                matrix[y][x] = ((data_hash + idx * 13) % 17) < 8

    return matrix


def _scale_matrix(matrix: list[list[bool]], scale: int) -> list[list[bool]]:
    """Scale up a matrix."""
    if scale == 1:
        return matrix

    scaled = []
    for row in matrix:
        new_row = []
        for val in row:
            new_row.extend([val] * scale)
        for _ in range(scale):
            scaled.append(new_row[:])
    return scaled


def _draw_qr_on_image(image: Image.Image, qr_text: str, x: int, y: int) -> None:
    """Draw QR code onto existing image."""
    try:
        matrix = _generate_qr_matrix(qr_text, version=2)
        scaled = _scale_matrix(matrix, 2)

        height = len(scaled)
        width = len(scaled[0]) if height > 0 else 0

        for row_y, row in enumerate(scaled):
            for col_x, is_black in enumerate(row):
                if is_black:
                    image.putpixel((x + col_x, y + row_y), 1)

        # Border
        draw = ImageDraw.Draw(image)
        draw.rectangle([x - 1, y - 1, x + width, y + height], outline=1)
    except Exception as e:
        log.warning(f"QR draw failed: {e}")


def render_bluetooth_qr_screen(
    app_ctx: AppContext,
    display_ctx: DisplayContext,
) -> None:
    """Render Bluetooth QR code screen with app-standard styling."""
    data = generate_qr_data()
    title = "BLUETOOTH"
    title_icon = get_screen_icon("bluetooth")

    if "error" in data:
        display.render_paginated_lines(
            title,
            ["Bluetooth not enabled", "", "Press BACK"],
            page_index=0,
            title_icon=title_icon,
        )
        return

    # Get context info
    context = display.get_display_context()
    content_top = menus.get_standard_content_top(title, title_icon=title_icon)

    # Use the display's image buffer
    with display._display_lock:
        draw = context.draw
        draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

        # Title bar (matching app style)
        from rpi_usb_cloner.ui.display import draw_title_with_icon

        draw_title_with_icon(title, title_icon=title_icon)

        # QR code on left
        qr_text = generate_qr_text()
        _draw_qr_on_image(context.image, qr_text, 2, content_top)

        # Info text on right
        items_font = context.fonts.get("items", context.fontdisks)
        info_x = 50
        y = content_top

        draw.text((info_x, y), "1. Pair phone", font=items_font, fill=255)
        y += 10
        draw.text((info_x, y), "2. Scan code", font=items_font, fill=255)
        y += 14

        name = data.get("device_name", "RPI-USB")[:10]
        draw.text((info_x, y), name, font=items_font, fill=255)
        y += 10

        # PIN highlighted
        pin = data.get("pin", "000000")
        draw.rectangle([info_x, y, info_x + 38, y + 9], fill=255)
        draw.text((info_x + 2, y), f"{pin}", font=items_font, fill=0)

        # Footer
        draw.line([(0, 56), (128, 56)], fill=255)
        draw.text((2, 57), "A:Back C:Refresh", font=items_font, fill=255)

        context.disp.display(context.image)
        display.mark_display_dirty()

    app_ctx.current_screen_image = context.image.copy()


def render_bluetooth_status_screen(
    app_ctx: AppContext,
    display_ctx: DisplayContext,
) -> None:
    """Render Bluetooth status screen with app-standard styling."""
    status = get_bluetooth_status()
    trusted_count = len(get_trusted_bluetooth_devices())
    title_icon = get_screen_icon("bluetooth")

    lines = []

    if not status.enabled:
        lines.extend([
            "Status: DISABLED",
            f"Trusted: {trusted_count} devices",
            "",
            "B: Menu  C: Enable",
        ])
    else:
        state = "CONNECTED" if status.connected else "WAITING"
        lines.append(f"Status: {state}")

        if status.mac_address:
            lines.append(f"MAC: {status.mac_address}")

        if status.pin:
            lines.append(f"PIN: {status.pin}")

        if status.ip_address:
            lines.append(f"IP: {status.ip_address}")

        if status.connected and status.connected_device:
            lines.append(f"Device: {status.connected_device[:18]}")
        else:
            lines.append(f"Trusted: {trusted_count} devices")

        lines.extend(["", "B: Menu  C: Toggle"])

    display.render_paginated_lines(
        "BLUETOOTH",
        lines,
        page_index=0,
        title_icon=title_icon,
    )
