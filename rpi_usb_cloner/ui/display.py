"""OLED display management and rendering utilities for 128x64 SSD1306 displays.

This module provides the display abstraction layer for the Adafruit 128x64 OLED Bonnet,
handling:
- Display initialization and configuration
- Text rendering with custom fonts
- Icon rendering from icon fonts (Lucide, Heroicons)
- Simple multi-line text display
- Display context management

Hardware Configuration:
    - Display: SSD1306 OLED (128x64 pixels, I2C interface)
    - I2C Address: 0x3C or 0x3D (configurable in code)
    - Interface: i2c via luma.oled library
    - Bus: I2C bus 1 (standard on Raspberry Pi)

Display Context:
    The DisplayContext dataclass encapsulates all display-related resources:
    - disp: luma.oled device instance
    - draw: PIL ImageDraw object for rendering
    - image: PIL Image buffer (1-bit monochrome)
    - fonts: Dictionary of loaded TrueType fonts
    - Geometry: width, height, x, top, bottom coordinates

Font Assets:
    The module uses custom fonts from the assets/fonts directory:
    - lucide.ttf: Lucide icon font for UI icons
    - his.ttf: Heroicons icon font

    Icon fonts are rendered using Unicode codepoints that map to glyphs.
    Standard text uses PIL's default font.

Key Functions:
    - initialize_display(): Create and configure SSD1306 device
    - get_display_context(): Retrieve singleton display context
    - display_lines(): Simple text output for status messages
    - clear_display(): Blank the screen
    - get_lucide_font(): Load Lucide icon font with size

Rendering Pipeline:
    1. Create PIL Image buffer (1-bit mode for monochrome)
    2. Use ImageDraw to render text/shapes to buffer
    3. Call disp.display(image) to push buffer to hardware
    4. Hardware updates visible pixels

Display Layout:
    - Resolution: 128x64 pixels
    - Typical layout:
      - Title bar: Top 12-16 pixels (with optional icon)
      - Content area: Remaining space for text/menus
      - Status line: Bottom row for context info

Performance Notes:
    - Full screen refresh takes ~50ms
    - Avoid excessive redraws (causes flicker)
    - Cache font objects to avoid repeated loading
    - Use dirty region tracking where possible (not implemented)

Initialization:
    Display must be initialized before use via initialize_display().
    Subsequent calls return the cached DisplayContext singleton.

Example:
    >>> from rpi_usb_cloner.ui import display
    >>> display.initialize_display()
    >>> display.display_lines(["USB Cloner", "Ready"])
    >>> # Display now shows two lines of text

Thread Safety:
    This module is NOT thread-safe. All display operations must occur
    on the main thread. Concurrent display updates will corrupt output.

Error Handling:
    - I2C errors are not caught; will propagate to caller
    - Missing fonts will raise FileNotFoundError
    - Invalid display operations will raise luma.oled exceptions

See Also:
    - rpi_usb_cloner.ui.screens: Higher-level screen rendering
    - rpi_usb_cloner.ui.menus: Menu rendering utilities
    - luma.oled documentation: https://luma-oled.readthedocs.io/
"""

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional

from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import Image, ImageDraw, ImageFont

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.config.settings import get_setting
from rpi_usb_cloner.logging import get_logger


@dataclass
class DisplayContext:
    disp: ssd1306
    draw: ImageDraw.ImageDraw
    image: Image.Image
    fonts: Dict[str, ImageFont.ImageFont]
    width: int
    height: int
    x: int
    top: int
    bottom: int
    fontcopy: ImageFont.ImageFont
    fontinsert: ImageFont.ImageFont
    fontdisks: ImageFont.ImageFont
    fontmain: ImageFont.ImageFont


_context: Optional[DisplayContext] = None
_log_debug = get_logger(tags=["display"], source=__name__).debug
_display_lock = threading.RLock()


def _device_menu_lines(device: dict) -> list[str]:
    name = device.get("name", "")
    size_bytes = device.get("size") or 0
    size_gb = size_bytes / 1024**3
    vendor = (device.get("vendor") or "").strip()
    model = (device.get("model") or "").strip()
    return [
        f"{name} {size_gb:.2f}GB",
        f"{vendor} {model}".strip(),
    ]


_display_dirty = threading.Event()
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
TITLE_PADDING = 0
TITLE_ICON_PADDING = 2
TITLE_TEXT_Y_OFFSET = -2
LUCIDE_FONT_PATH = ASSETS_DIR / "fonts" / "lucide.ttf"
LUCIDE_FONT_SIZE = 16
ICON_BASELINE_ADJUST = -1
_lucide_fonts: Dict[int, ImageFont.ImageFont] = {}


@dataclass(frozen=True)
class TitleLayout:
    content_top: int
    title_x: int
    max_title_width: int
    icon_width: int
    icon_height: int


def configure_display_helpers(log_debug=None):
    global _log_debug
    _log_debug = log_debug


def set_display_context(context: DisplayContext) -> None:
    global _context
    _context = context


def get_display_context() -> DisplayContext:
    if _context is None:
        raise RuntimeError("Display context has not been initialized")
    return _context


def mark_display_dirty() -> None:
    """Mark the display as dirty (changed) to notify websocket clients."""
    _display_dirty.set()


def wait_for_display_update(timeout: float = 1.0) -> bool:
    """Wait for the display to be updated (dirty flag set).

    Args:
        timeout: Maximum time to wait in seconds

    Returns:
        True if display was updated, False if timeout occurred
    """
    return _display_dirty.wait(timeout)


def clear_dirty_flag() -> None:
    """Clear the dirty flag after consuming an update."""
    _display_dirty.clear()


def clear_display() -> None:
    context = get_display_context()
    with _display_lock:
        context.disp.clear()
        context.draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        context.disp.display(context.image)
        mark_display_dirty()


def capture_screenshot() -> Optional[Path]:
    """Capture the current OLED display as a screenshot.

    Returns:
        Path to the saved screenshot file, or None if capture failed.
    """
    try:
        context = get_display_context()
        screenshot = context.image.copy()
        configured_dir = get_setting("screenshots_dir", "/home/pi/oled_screenshots")
        base_dir = Path("/home/pi").resolve()
        screenshots_dir = Path(configured_dir).expanduser()
        if not screenshots_dir.is_absolute():
            screenshots_dir = base_dir / screenshots_dir
        resolved_dir = screenshots_dir.resolve(strict=False)
        try:
            resolved_dir.relative_to(base_dir)
        except ValueError:
            resolved_dir = base_dir / resolved_dir.name
        resolved_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(resolved_dir, 0o775)
        except (PermissionError, OSError) as error:
            if _log_debug:
                _log_debug(f"Screenshot dir permissions unchanged: {error}")
        try:
            import pwd

            pi_user = pwd.getpwnam("pi")
            os.chown(resolved_dir, pi_user.pw_uid, pi_user.pw_gid)
        except (KeyError, PermissionError, OSError) as error:
            if _log_debug:
                _log_debug(f"Screenshot dir ownership unchanged: {error}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = resolved_dir / f"screenshot_{timestamp}.png"
        screenshot.save(screenshot_path)
        if _log_debug:
            _log_debug(f"Screenshot saved: {screenshot_path}")
        return screenshot_path
    except Exception as error:
        if _log_debug:
            _log_debug(f"Screenshot failed: {error}")
        return None


def get_display_png_bytes() -> bytes:
    """Return the current OLED frame buffer as PNG bytes.

    This function is thread-safe and will acquire the display lock
    to ensure a consistent snapshot of the display buffer.
    """
    context = get_display_context()
    with _display_lock:
        buffer = BytesIO()
        image = context.image.copy()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def init_display() -> DisplayContext:
    serial = i2c(port=1, address=0x3C)
    disp = ssd1306(serial)
    disp.clear()

    width = disp.width
    height = disp.height

    splash = Image.open(ASSETS_DIR / "splash.png").convert("1")
    if splash.size != (width, height):
        splash = splash.resize((width, height))
    disp.display(splash)
    time.sleep(1.5)

    image = Image.new("1", (width, height))
    draw = ImageDraw.Draw(image)

    x = 12
    padding = -2
    top = padding
    bottom = height - padding

    font = ImageFont.load_default()
    fontcopy = ImageFont.truetype(ASSETS_DIR / "fonts" / "Born2bSportyFS.otf", 16)
    fontinsert = ImageFont.truetype(ASSETS_DIR / "fonts" / "slkscr.ttf", 16)
    fontdisks = ImageFont.truetype(ASSETS_DIR / "fonts" / "slkscr.ttf", 8)
    fontmain = font
    fonts = {
        "title": fontcopy,
        "items": fontdisks,
        "footer": fontcopy,
    }

    context = DisplayContext(
        disp=disp,
        draw=draw,
        image=image,
        fonts=fonts,
        width=width,
        height=height,
        x=x,
        top=top,
        bottom=bottom,
        fontcopy=fontcopy,
        fontinsert=fontinsert,
        fontdisks=fontdisks,
        fontmain=fontmain,
    )
    return context


def display_lines(lines, font=None):
    context = get_display_context()
    draw = context.draw
    with _display_lock:
        draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        y = context.top
        font_to_use = font or context.fontdisks
        for line in lines[:6]:
            draw.text((context.x - 11, y), line, font=font_to_use, fill=255)
            y += 10
        context.disp.display(context.image)
        mark_display_dirty()


def _get_line_height(font, min_height=8):
    line_height = min_height
    try:
        bbox = font.getbbox("Ag")
        line_height = max(bbox[3] - bbox[1], line_height)
    except AttributeError:
        if hasattr(font, "getmetrics"):
            ascent, descent = font.getmetrics()
            line_height = max(ascent + descent, line_height)
    return line_height


def _measure_text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _truncate_text(draw, text, font, max_width):
    if _measure_text_width(draw, text, font) <= max_width:
        return text
    if max_width <= 0:
        return ""
    ellipsis = "…"
    truncated = text
    while truncated:
        candidate = f"{truncated}{ellipsis}" if truncated != text else truncated
        if _measure_text_width(draw, candidate, font) <= max_width:
            return candidate
        truncated = truncated[:-1]
    return ""


def _split_long_word(draw, word, font, available_width):
    if available_width <= 0:
        return [""]
    chunks = []
    current = ""
    for char in word:
        candidate = f"{current}{char}"
        if _measure_text_width(draw, candidate, font) <= available_width:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = char
        else:
            chunks.append(char)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def _wrap_lines_to_width(lines, font, available_width):
    context = get_display_context()
    draw = context.draw
    wrapped_lines = []
    for line in lines:
        words = line.split()
        if not words:
            wrapped_lines.append("")
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if _measure_text_width(draw, candidate, font) <= available_width:
                current = candidate
                continue
            if current:
                wrapped_lines.append(current)
                current = ""
            if _measure_text_width(draw, word, font) <= available_width:
                current = word
            else:
                chunks = _split_long_word(draw, word, font, available_width)
                wrapped_lines.extend(chunks[:-1])
                current = chunks[-1] if chunks else ""
        if current:
            wrapped_lines.append(current)
    return wrapped_lines


def _get_lucide_font(size: int | None = None) -> ImageFont.ImageFont:
    size = LUCIDE_FONT_SIZE if size is None else size
    cached_font = _lucide_fonts.get(size)
    if cached_font is not None:
        return cached_font
    try:
        cached_font = ImageFont.truetype(LUCIDE_FONT_PATH, size)
    except OSError:
        cached_font = get_display_context().fontdisks
    _lucide_fonts[size] = cached_font
    return cached_font


def draw_title_with_icon(
    title: str,
    *,
    title_font: Optional[ImageFont.ImageFont] = None,
    icon: Optional[str] = None,
    icon_font: Optional[ImageFont.ImageFont] = None,
    extra_gap: int = 2,
    left_margin: Optional[int] = None,
    max_width: Optional[int] = None,
    draw: Optional[ImageDraw.ImageDraw] = None,
) -> TitleLayout:
    context = get_display_context()
    draw = draw or context.draw
    left_margin = context.x - 11 if left_margin is None else left_margin
    header_font = title_font or context.fonts.get("title", context.fontdisks)

    # Calculate dimensions and baseline info
    icon_width = 0
    icon_bbox = None
    title_bbox = None
    title_text = ""
    title_ascent = title_descent = 0
    icon_ascent = icon_descent = 0
    is_image_icon = False
    icon_image = None

    if icon:
        # Check if icon is a file path to a PNG image
        if icon.endswith(".png"):
            is_image_icon = True
            try:
                icon_path = Path(icon) if os.path.isabs(icon) else ASSETS_DIR / icon
                icon_image = Image.open(icon_path).convert("1")
                icon_width = icon_image.width
                icon_ascent = icon_image.height
                icon_descent = 0
            except (OSError, FileNotFoundError):
                # Fall back to no icon if image can't be loaded
                is_image_icon = False
                icon_image = None
                icon_width = 0
                icon = None
        else:
            # Lucide icon (Unicode character)
            icon_font = icon_font or _get_lucide_font()
            icon_width = _measure_text_width(draw, icon, icon_font)
            icon_bbox = icon_font.getbbox(icon)
            try:
                icon_ascent, icon_descent = icon_font.getmetrics()
            except AttributeError:
                icon_ascent = max(0, icon_bbox[3] - icon_bbox[1])
                icon_descent = 0

    title_x = left_margin + (icon_width + TITLE_ICON_PADDING if icon_width else 0)
    if title:
        available_width = (
            max_width if max_width is not None else max(0, context.width - title_x - 1)
        )
        title_text = _truncate_text(draw, title, header_font, available_width)
        if title_text:
            title_bbox = draw.textbbox((0, 0), title_text, font=header_font)
            try:
                title_ascent, title_descent = header_font.getmetrics()
            except AttributeError:
                title_ascent = max(0, title_bbox[3] - title_bbox[1])
                title_descent = 0
    else:
        available_width = 0

    if not title_text:
        return TitleLayout(
            content_top=context.top,
            title_x=title_x,
            max_title_width=available_width,
            icon_width=icon_width,
            icon_height=0,
        )

    # Calculate line height based on font metrics for consistent spacing
    title_line_height = title_ascent + title_descent
    icon_line_height = icon_ascent + icon_descent
    line_height = max(title_line_height, icon_line_height)

    # Draw title at fixed position for consistency
    if title_text:
        title_y = context.top + TITLE_TEXT_Y_OFFSET
        draw.text((title_x, title_y), title_text, font=header_font, fill=255)

        # Position icon at consistent Y coordinate
        if icon:
            if is_image_icon and icon_image:
                # Use PIL Image.paste to draw the image icon
                icon_y = 0
                context.image.paste(icon_image, (left_margin, icon_y))
            else:
                # Use fixed Y position to keep all icons at same height
                # Positioned slightly above screen edge to align with title text
                icon_y = -1
                draw.text((left_margin, icon_y), icon, font=icon_font, fill=255)

    content_top = context.top + line_height + TITLE_PADDING + extra_gap
    return TitleLayout(
        content_top=content_top,
        title_x=title_x,
        max_title_width=available_width,
        icon_width=icon_width,
        icon_height=icon_line_height,
    )


def render_paginated_lines(
    title,
    lines,
    page_index=0,
    items_font=None,
    title_font=None,
    title_icon: Optional[str] = None,
    title_icon_font: Optional[ImageFont.ImageFont] = None,
    content_top: Optional[int] = None,
):
    context = get_display_context()
    draw = context.draw
    with _display_lock:
        draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        current_y = context.top
        header_font = title_font or context.fonts.get("title", context.fontdisks)
        if title:
            layout = draw_title_with_icon(
                title,
                title_font=header_font,
                icon=title_icon,
                icon_font=title_icon_font,
                extra_gap=2,
                left_margin=context.x - 11,
            )
            current_y = layout.content_top
        if content_top is not None:
            current_y = max(current_y, content_top)
        items_font = items_font or context.fontdisks
        left_margin = context.x - 11
        available_width = max(0, context.width - left_margin)
        lines = _wrap_lines_to_width(lines, items_font, available_width)
        line_height = _get_line_height(items_font)
        line_step = line_height + 2
        available_height = context.height - current_y - 2
        lines_per_page = max(1, available_height // line_step)
        total_pages = max(1, (len(lines) + lines_per_page - 1) // lines_per_page)
        page_index = max(0, min(page_index, total_pages - 1))
        start = page_index * lines_per_page
        end = start + lines_per_page
        page_lines = lines[start:end]
        for line in page_lines:
            draw.text((context.x - 11, current_y), line, font=items_font, fill=255)
            current_y += line_step
        if total_pages > 1:
            left_indicator = "<" if page_index > 0 else ""
            right_indicator = ">" if page_index < total_pages - 1 else ""
            indicator = (
                f"{left_indicator}{page_index + 1}/{total_pages}{right_indicator}"
            )
            indicator_bbox = draw.textbbox((0, 0), indicator, font=items_font)
            indicator_width = indicator_bbox[2] - indicator_bbox[0]
            indicator_height = indicator_bbox[3] - indicator_bbox[1]
            draw.text(
                (
                    context.width - indicator_width - 2,
                    context.height - indicator_height - 2,
                ),
                indicator,
                font=items_font,
                fill=255,
            )
        context.disp.display(context.image)
        mark_display_dirty()
        return total_pages, page_index


def basemenu(state: app_state.AppState) -> None:
    from rpi_usb_cloner.services.drives import list_usb_disks_filtered
    from rpi_usb_cloner.ui.menus import Menu, MenuItem, render_menu

    context = get_display_context()
    devices = list_usb_disks_filtered()
    devices_present = bool(devices)
    with _display_lock:
        if not devices:
            context.draw.rectangle(
                (0, 0, context.width, context.height), outline=0, fill=0
            )
            text = "INSERT USB"
            text_bbox = context.draw.textbbox((0, 0), text, font=context.fontinsert)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            text_x = (context.width - text_width) // 2
            text_y = (context.height - text_height) // 2
            context.draw.text((text_x, text_y), text, font=context.fontinsert, fill=255)
            state.usb_list_index = 0
        else:
            if state.usb_list_index >= len(devices):
                state.usb_list_index = max(len(devices) - 1, 0)
            menu_items = []
            for device in devices:
                menu_items.append(MenuItem(_device_menu_lines(device)))
            start_index = max(0, state.usb_list_index - 1)
            max_start = max(len(menu_items) - app_state.VISIBLE_ROWS, 0)
            if start_index > max_start:
                start_index = max_start
            visible_items = menu_items[
                start_index : start_index + app_state.VISIBLE_ROWS
            ]
            visible_selected_index = state.usb_list_index - start_index
            if state.index not in (
                app_state.MENU_COPY,
                app_state.MENU_VIEW,
                app_state.MENU_ERASE,
            ):
                state.index = app_state.MENU_COPY
            footer_selected = None
            if state.index in (
                app_state.MENU_COPY,
                app_state.MENU_VIEW,
                app_state.MENU_ERASE,
            ):
                footer_selected = state.index
            menu = Menu(
                items=visible_items,
                selected_index=visible_selected_index,
                footer=["COPY", "VIEW", "ERASE"],
                footer_selected_index=footer_selected,
                footer_positions=[context.x - 11, context.x + 32, context.x + 71],
            )
            render_menu(
                menu, context.draw, context.width, context.height, context.fonts
            )
        context.disp.display(context.image)
        mark_display_dirty()
    state.lcdstart = datetime.now()
    state.run_once = 0
    if not devices_present:
        state.index = app_state.MENU_NONE
    if _log_debug:
        _log_debug("Base menu drawn")
