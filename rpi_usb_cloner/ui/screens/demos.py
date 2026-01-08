"""Demo screen functions for testing icons and fonts."""

import time
from pathlib import Path
from typing import Iterable, Optional

from PIL import ImageFont

from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.ui import display, menus


def _show_icon_font_demo(title: str, font_path, *, icons: Optional[Iterable[str]] = None) -> None:
    context = display.get_display_context()
    title_font = context.fonts.get("title", context.fontdisks)
    content_top = menus.get_standard_content_top(title, title_font=title_font)
    if icons is None:
        icons = ["\uf55a", "\uf060", "\uf30a", "\uf00c"]
    icons = list(icons)
    sizes = [8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 26, 28, 30]
    label_font = context.fontdisks
    icon_font = ImageFont.truetype(font_path, max(sizes))
    max_icon_height = 0
    for glyph in icons:
        bbox = context.draw.textbbox((0, 0), glyph, font=icon_font)
        max_icon_height = max(max_icon_height, bbox[3] - bbox[1])
    label_line_height = display._get_line_height(label_font)
    line_step = max(max_icon_height, label_line_height) + 2
    rows_per_page = max(1, (context.height - content_top - 2) // line_step)
    max_offset = max(0, len(sizes) - rows_per_page)
    scroll_offset = 0

    def render(offset: int) -> int:
        offset = max(0, min(offset, max_offset))
        page_sizes = sizes[offset : offset + rows_per_page]

        draw = context.draw
        draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        draw.text((context.x - 11, context.top), title, font=title_font, fill=255)

        current_y = content_top
        left_x = context.x - 11
        for size in page_sizes:
            icon_font = ImageFont.truetype(font_path, size)
            icon_height = display._get_line_height(icon_font)
            icon_y = current_y + max(0, (line_step - icon_height) // 2)
            label_y = current_y + max(0, (line_step - label_line_height) // 2)
            label_text = f"{size}px"
            draw.text((left_x, label_y), label_text, font=label_font, fill=255)
            label_width = display._measure_text_width(draw, label_text, label_font)
            current_x = left_x + label_width + 6
            for glyph in icons:
                glyph_width = display._measure_text_width(draw, glyph, icon_font)
                if current_x + glyph_width > context.width - 2:
                    break
                draw.text((current_x, icon_y), glyph, font=icon_font, fill=255)
                current_x += glyph_width + 6
            current_y += line_step

        if len(sizes) > rows_per_page:
            footer_text = "▲▼ to scroll"
            footer_height = display._get_line_height(label_font)
            footer_y = context.height - footer_height - 1
            footer_x = left_x
            draw.text((footer_x, footer_y), footer_text, font=label_font, fill=255)

        context.disp.display(context.image)
        return offset

    scroll_offset = render(scroll_offset)
    menus.wait_for_buttons_release([gpio.PIN_A, gpio.PIN_B, gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D])
    prev_states = {
        "A": gpio.read_button(gpio.PIN_A),
        "B": gpio.read_button(gpio.PIN_B),
        "L": gpio.read_button(gpio.PIN_L),
        "R": gpio.read_button(gpio.PIN_R),
        "U": gpio.read_button(gpio.PIN_U),
        "D": gpio.read_button(gpio.PIN_D),
    }
    while True:
        current_a = gpio.read_button(gpio.PIN_A)
        if prev_states["A"] and not current_a:
            return
        current_b = gpio.read_button(gpio.PIN_B)
        if prev_states["B"] and not current_b:
            return
        current_l = gpio.read_button(gpio.PIN_L)
        if prev_states["L"] and not current_l:
            return
        current_r = gpio.read_button(gpio.PIN_R)
        current_u = gpio.read_button(gpio.PIN_U)
        if prev_states["U"] and not current_u:
            scroll_offset = max(0, scroll_offset - 1)
            scroll_offset = render(scroll_offset)
        current_d = gpio.read_button(gpio.PIN_D)
        if prev_states["D"] and not current_d:
            scroll_offset = min(max_offset, scroll_offset + 1)
            scroll_offset = render(scroll_offset)
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        time.sleep(0.05)


def show_font_awesome_demo(title: str = "FONT AWESOME") -> None:
    font_path = display.ASSETS_DIR / "fonts" / "Font-Awesome-7-Free-Solid-900.otf"
    _show_icon_font_demo(title, font_path)


def show_lucide_demo(title: str = "LUCIDE") -> None:
    font_path = display.ASSETS_DIR / "fonts" / "lucide.ttf"
    lucide_icons = [chr(57684), chr(57669), chr(57774)]
    _show_icon_font_demo(title, font_path, icons=lucide_icons)


def show_heroicons_demo(title: str = "HEROICONS") -> None:
    font_path = display.ASSETS_DIR / "fonts" / "his.ttf"
    heroicons_icons = [chr(0xE934), chr(0xE963), chr(0xE964), chr(0xEA27)]
    _show_icon_font_demo(title, font_path, icons=heroicons_icons)


def _format_font_label(font_path: Path) -> str:
    return font_path.stem.replace("_", " ").replace("-", " ").upper()


def show_title_font_preview(title: str = "TITLE FONT PREVIEW") -> None:
    context = display.get_display_context()
    fonts_dir = display.ASSETS_DIR / "fonts"
    font_paths = sorted(
        [path for path in fonts_dir.glob("*") if path.suffix.lower() in {".ttf", ".otf"}]
    )
    if not font_paths:
        display.display_lines([title, "No fonts found"])
        time.sleep(1.5)
        return

    reset_label = "RESET TO DEFAULT"
    items = [reset_label] + [_format_font_label(path) for path in font_paths]
    selected_index = 0
    default_size = getattr(context.fontcopy, "size", 16)

    while True:
        selection = menus.render_menu_list(title, items, selected_index=selected_index)
        if selection is None:
            return
        selected_index = selection
        if selection == 0:
            context.fonts["title"] = context.fontcopy
            display.display_lines([title, "Reset to default"])
            time.sleep(1)
            continue

        font_path = font_paths[selection - 1]
        try:
            preview_font = ImageFont.truetype(str(font_path), default_size)
        except Exception:
            display.display_lines([title, "Load failed"])
            time.sleep(1.5)
            continue
        context.fonts["title"] = preview_font
        display.display_lines([title, "Preview applied"])
        time.sleep(1)
