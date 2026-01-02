import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.storage.mount import (
    get_device_name,
    get_model,
    get_size,
    get_vendor,
    list_media_devices,
)


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
_log_debug = None
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
TITLE_PADDING = 2


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


def clear_display() -> None:
    context = get_display_context()
    context.disp.clear()
    context.draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    context.disp.display(context.image)


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
    fontcopy = ImageFont.truetype(ASSETS_DIR / "fonts" / "rainyhearts.ttf", 16)
    fontinsert = ImageFont.truetype(ASSETS_DIR / "fonts" / "slkscr.ttf", 16)
    fontdisks = ImageFont.truetype(ASSETS_DIR / "fonts" / "slkscr.ttf", 8)
    fontkeyboard = ImageFont.truetype(ASSETS_DIR / "fonts" / "Born2bSportyFS.otf", 10)
    fontmain = font
    fonts = {
        "title": fontcopy,
        "items": fontdisks,
        "footer": fontcopy,
        "keyboard": fontkeyboard,
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
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    y = context.top
    font_to_use = font or context.fontdisks
    for line in lines[:6]:
        draw.text((context.x - 11, y), line, font=font_to_use, fill=255)
        y += 10
    context.disp.display(context.image)


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
                wrapped_lines.append(_truncate_text(draw, word, font, available_width))
        if current:
            wrapped_lines.append(current)
    return wrapped_lines


def render_paginated_lines(
    title,
    lines,
    page_index=0,
    items_font=None,
    title_font=None,
    content_top: Optional[int] = None,
):
    context = get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    current_y = context.top
    header_font = title_font or context.fonts.get("title", context.fontdisks)
    if title:
        draw.text((context.x - 11, current_y), title, font=header_font, fill=255)
        from rpi_usb_cloner.ui import menus

        current_y = menus.get_standard_content_top(title, title_font=header_font)
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
        indicator = f"{left_indicator}{page_index + 1}/{total_pages}{right_indicator}"
        indicator_bbox = draw.textbbox((0, 0), indicator, font=items_font)
        indicator_width = indicator_bbox[2] - indicator_bbox[0]
        indicator_height = indicator_bbox[3] - indicator_bbox[1]
        draw.text(
            (context.width - indicator_width - 2, context.height - indicator_height - 2),
            indicator,
            font=items_font,
            fill=255,
        )
    context.disp.display(context.image)
    return total_pages, page_index


def basemenu(state: app_state.AppState) -> None:
    from rpi_usb_cloner.ui.menus import Menu, MenuItem, render_menu

    context = get_display_context()
    devices = list_media_devices()
    devices_present = bool(devices)
    if not devices:
        context.draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
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
            menu_items.append(
                MenuItem(
                    [
                        f"{get_device_name(device)} {get_size(device) / 1024 ** 3:.2f}GB",
                        f"{get_vendor(device)} {get_model(device)}",
                    ]
                )
            )
        start_index = max(0, state.usb_list_index - 1)
        max_start = max(len(menu_items) - app_state.VISIBLE_ROWS, 0)
        if start_index > max_start:
            start_index = max_start
        visible_items = menu_items[start_index : start_index + app_state.VISIBLE_ROWS]
        visible_selected_index = state.usb_list_index - start_index
        if state.index not in (app_state.MENU_COPY, app_state.MENU_VIEW, app_state.MENU_ERASE):
            state.index = app_state.MENU_COPY
        footer_selected = None
        if state.index in (app_state.MENU_COPY, app_state.MENU_VIEW, app_state.MENU_ERASE):
            footer_selected = state.index
        menu = Menu(
            items=visible_items,
            selected_index=visible_selected_index,
            footer=["COPY", "VIEW", "ERASE"],
            footer_selected_index=footer_selected,
            footer_positions=[context.x - 11, context.x + 32, context.x + 71],
        )
        render_menu(menu, context.draw, context.width, context.height, context.fonts)
    context.disp.display(context.image)
    state.lcdstart = datetime.now()
    state.run_once = 0
    if not devices_present:
        state.index = app_state.MENU_NONE
    if _log_debug:
        _log_debug("Base menu drawn")
