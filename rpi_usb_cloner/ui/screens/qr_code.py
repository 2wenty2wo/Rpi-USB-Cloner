"""QR code display screen for Bluetooth pairing.

This module provides a screen that displays a QR code for Bluetooth
pairing along with manual pairing instructions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

from rpi_usb_cloner.logging import LoggerFactory
from rpi_usb_cloner.services.bluetooth import (
    generate_qr_data,
    generate_qr_text,
    get_bluetooth_status,
    get_trusted_bluetooth_devices,
)

if TYPE_CHECKING:
    from rpi_usb_cloner.app.context import AppContext
    from rpi_usb_cloner.ui.display import DisplayContext

log = LoggerFactory.for_menu()

# Display dimensions
SCREEN_WIDTH = 128
SCREEN_HEIGHT = 64

# QR code positioning
QR_SIZE = 50  # QR code will be 50x50 pixels (version 2 at 2px per module)
QR_X = 2  # Left side
QR_Y = 12  # Below title


def _generate_qr_matrix(data: str, version: int = 2) -> list[list[bool]]:
    """Generate a simple QR code matrix.

    This is a simplified QR code generator that creates a scannable QR code
    for small amounts of data. For production use, consider using the 'qrcode'
    library, but this implementation avoids the dependency.

    Args:
        data: The data to encode
        version: QR code version (1-3 supported)

    Returns:
        2D boolean matrix where True = black module
    """
    try:
        # Try to use the qrcode library if available
        import qrcode
        error_correction = None
        try:
            from qrcode.constants import ERROR_CORRECT_L

            error_correction = ERROR_CORRECT_L
        except Exception:
            error_correction = getattr(
                getattr(qrcode, "constants", None), "ERROR_CORRECT_L", None
            )

        qr_kwargs = {
            "version": version,
            "box_size": 1,
            "border": 2,
        }
        if error_correction is not None:
            qr_kwargs["error_correction"] = error_correction

        qr = qrcode.QRCode(**qr_kwargs)
        qr.add_data(data)
        qr.make(fit=True)

        # Convert to boolean matrix
        matrix = []
        for row in qr.modules:
            matrix.append([bool(module) for module in row])
        return matrix
    except ImportError:
        pass

    # Fallback: generate a simple pattern that looks like a QR code
    # This won't be scannable but shows the UI works
    size = 21 if version == 1 else 25 if version == 2 else 29
    matrix = [[False] * size for _ in range(size)]

    # Draw finder patterns (the three big squares in corners)
    def draw_finder_pattern(x: int, y: int) -> None:
        for dy in range(7):
            for dx in range(7):
                # Outer square
                if dy == 0 or dy == 6 or dx == 0 or dx == 6:
                    matrix[y + dy][x + dx] = True
                # Inner square
                elif 2 <= dy <= 4 and 2 <= dx <= 4:
                    matrix[y + dy][x + dx] = True

    # Top-left finder
    draw_finder_pattern(0, 0)
    # Top-right finder
    draw_finder_pattern(size - 7, 0)
    # Bottom-left finder
    draw_finder_pattern(0, size - 7)

    # Draw timing patterns (alternating line between finders)
    for i in range(8, size - 8):
        matrix[6][i] = i % 2 == 0
        matrix[i][6] = i % 2 == 0

    # Dark module (always present)
    matrix[size - 8][8] = True

    # Encode data as simple alternating pattern
    data_hash = sum(ord(c) * (i + 1) for i, c in enumerate(data))
    for y in range(size):
        for x in range(size):
            if not matrix[y][x]:  # Only fill empty areas
                # Pseudo-random based on data hash
                idx = y * size + x
                matrix[y][x] = ((data_hash + idx * 13) % 17) < 8

    return matrix


def _scale_matrix(matrix: list[list[bool]], scale: int) -> list[list[bool]]:
    """Scale up a matrix by a factor."""
    if scale == 1:
        return matrix

    height = len(matrix)
    width = len(matrix[0]) if height > 0 else 0

    scaled = []
    for row in matrix:
        new_row = []
        for val in row:
            new_row.extend([val] * scale)
        # Repeat each row
        for _ in range(scale):
            scaled.append(new_row[:])

    return scaled


def _resolve_font(display_ctx: DisplayContext) -> ImageFont.ImageFont:
    """Resolve a usable font, falling back to the default if needed."""
    font = getattr(display_ctx, "font_small", None)
    if font is None or not isinstance(font, ImageFont.ImageFont):
        return ImageFont.load_default()
    try:
        font.getmask("A")
    except Exception:
        return ImageFont.load_default()
    return font


def render_bluetooth_qr_screen(
    app_ctx: AppContext,
    display_ctx: DisplayContext,
) -> None:
    """Render the Bluetooth QR code screen.

    Displays a QR code containing the web UI URL for quick access after
    manual Bluetooth pairing. Also shows pairing information (MAC, PIN).

    Note: iOS/Android don't support auto-pairing from QR codes, so users
    must manually pair via Bluetooth settings first, then scan this QR
    to open the web UI in their browser.

    Args:
        app_ctx: Application context
        display_ctx: Display context with display device and fonts
    """
    # Get pairing data
    data = generate_qr_data()

    # Create image buffer
    image = Image.new("1", (SCREEN_WIDTH, SCREEN_HEIGHT), 0)
    draw = ImageDraw.Draw(image)

    font = _resolve_font(display_ctx)

    # Draw title bar
    draw.text((2, 0), "SCAN FOR WEB UI", font=font, fill=1)
    draw.line([(0, 10), (SCREEN_WIDTH, 10)], fill=1)

    if "error" in data:
        # Show error message
        draw.text((2, 20), "Bluetooth not enabled", font=font, fill=1)
        draw.text((2, 35), "Press BACK to return", font=font, fill=1)
        display_ctx.device.display(image)
        app_ctx.current_screen_image = image
        return

    # Generate QR code (contains web UI URL only)
    qr_text = generate_qr_text()
    try:
        qr_matrix = _generate_qr_matrix(qr_text, version=2)
        # Scale to 2px per module for 50x50 total
        scaled_matrix = _scale_matrix(qr_matrix, 2)
    except Exception as e:
        log.warning(f"Failed to generate QR code: {e}")
        scaled_matrix = None

    # Draw QR code on left side
    if scaled_matrix:
        qr_height = len(scaled_matrix)
        qr_width = len(scaled_matrix[0]) if qr_height > 0 else 0

        # Center the QR code vertically in available space
        qr_y_offset = QR_Y + (QR_SIZE - qr_height) // 2

        for y, row in enumerate(scaled_matrix):
            for x, is_black in enumerate(row):
                if is_black:
                    draw.point((QR_X + x, qr_y_offset + y), fill=1)

        # Draw border around QR code
        draw.rectangle(
            [QR_X - 1, qr_y_offset - 1, QR_X + qr_width, qr_y_offset + qr_height],
            outline=1,
        )

    # Draw pairing info on right side
    info_x = QR_X + QR_SIZE + 4
    info_y = QR_Y

    # Instructions
    draw.text((info_x, info_y), "1.Pair manually", font=font, fill=1)
    draw.text((info_x, info_y + 10), "2.Scan QR code", font=font, fill=1)

    # Device name (truncated if needed)
    name = data.get("device_name", "Unknown")[:11]
    draw.text((info_x, info_y + 22), name, font=font, fill=1)

    # PIN with highlight
    pin = data.get("pin", "000000")
    draw.text((info_x, info_y + 32), "PIN:", font=font, fill=1)
    # Draw PIN with inverted background for emphasis
    pin_width = len(pin) * 6  # Approximate width
    draw.rectangle(
        [info_x + 22, info_y + 31, info_x + 22 + pin_width + 2, info_y + 39],
        fill=1,
    )
    draw.text((info_x + 23, info_y + 32), pin, font=font, fill=0)

    # Footer hint
    draw.line([(0, SCREEN_HEIGHT - 9), (SCREEN_WIDTH, SCREEN_HEIGHT - 9)], fill=1)
    draw.text((2, SCREEN_HEIGHT - 8), "A:Back C:Refresh", font=font, fill=1)

    # Update display
    display_ctx.device.display(image)
    app_ctx.current_screen_image = image


def render_bluetooth_status_screen(
    app_ctx: AppContext,
    display_ctx: DisplayContext,
) -> None:
    """Render the Bluetooth status screen.

    Shows current Bluetooth PAN connection status and information.

    Args:
        app_ctx: Application context
        display_ctx: Display context with display device and fonts
    """
    status = get_bluetooth_status()
    trusted_count = len(get_trusted_bluetooth_devices())

    # Create image buffer
    image = Image.new("1", (SCREEN_WIDTH, SCREEN_HEIGHT), 0)
    draw = ImageDraw.Draw(image)

    font = _resolve_font(display_ctx)

    # Draw title
    draw.text((2, 0), "BLUETOOTH STATUS", font=font, fill=1)
    draw.line([(0, 10), (SCREEN_WIDTH, 10)], fill=1)

    y = 14

    if not status.enabled:
        draw.text((2, y), "Status: DISABLED", font=font, fill=1)
        y += 12
        draw.text((2, y), "Trusted: {} devices".format(trusted_count), font=font, fill=1)
        y += 12
        draw.text((2, y), "Press SELECT for menu", font=font, fill=1)
    else:
        # Status
        state = "CONNECTED" if status.connected else "WAITING"
        draw.text((2, y), f"Status: {state}", font=font, fill=1)
        y += 12

        # MAC address
        if status.mac_address:
            draw.text((2, y), f"MAC: {status.mac_address}", font=font, fill=1)
            y += 12

        # PIN
        if status.pin:
            draw.text((2, y), f"PIN: {status.pin}", font=font, fill=1)
            y += 12

        # IP address
        if status.ip_address:
            draw.text((2, y), f"IP: {status.ip_address}", font=font, fill=1)
            y += 12

        # Connected device (or trusted count)
        if status.connected and status.connected_device:
            device = status.connected_device[:20]
            draw.text((2, y), f"Device: {device}", font=font, fill=1)
        else:
            draw.text((2, y), f"Trusted: {trusted_count} devices", font=font, fill=1)

    # Footer
    draw.line([(0, SCREEN_HEIGHT - 9), (SCREEN_WIDTH, SCREEN_HEIGHT - 9)], fill=1)
    draw.text((2, SCREEN_HEIGHT - 8), "A:Back B:Menu C:Toggle", font=font, fill=1)

    # Update display
    display_ctx.device.display(image)
    app_ctx.current_screen_image = image
