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


def show_lucide_demo(title: str = "LUCIDE") -> None:
    font_path = display.ASSETS_DIR / "fonts" / "lucide.ttf"
    lucide_icons = [chr(57684), chr(57669), chr(57774)]
    _show_icon_font_demo(title, font_path, icons=lucide_icons)


def show_heroicons_demo(title: str = "HEROICONS") -> None:
    """Display all Heroicons in a scrollable grid."""
    # All Heroicons icon codes
    all_icon_codes = [
        0xe900, 0xe901, 0xe902, 0xe903, 0xe904, 0xe905, 0xe906, 0xe907, 0xe908, 0xe909,
        0xe90a, 0xe90b, 0xe90c, 0xe90d, 0xe90e, 0xe90f, 0xe910, 0xe911, 0xe912, 0xe913,
        0xe914, 0xe915, 0xe916, 0xe917, 0xe918, 0xe919, 0xe91a, 0xe91b, 0xe91c, 0xe91d,
        0xe91e, 0xe91f, 0xe920, 0xe921, 0xe922, 0xe923, 0xe924, 0xe925, 0xe926, 0xe927,
        0xe928, 0xe929, 0xe92a, 0xe92b, 0xe92c, 0xe92d, 0xe92e, 0xe92f, 0xe930, 0xe931,
        0xe932, 0xe933, 0xe934, 0xe935, 0xe936, 0xe937, 0xe938, 0xe939, 0xe93a, 0xe93b,
        0xe93c, 0xe93d, 0xe93e, 0xe93f, 0xe940, 0xe941, 0xe942, 0xe943, 0xe944, 0xe945,
        0xe946, 0xe947, 0xe948, 0xe949, 0xe94a, 0xe94b, 0xe94c, 0xe94d, 0xe94e, 0xe94f,
        0xe950, 0xe951, 0xe952, 0xe953, 0xe954, 0xe955, 0xe956, 0xe957, 0xe958, 0xe959,
        0xe95a, 0xe95b, 0xe95c, 0xe95d, 0xe95e, 0xe95f, 0xe960, 0xe961, 0xe962, 0xe963,
        0xe964, 0xe965, 0xe966, 0xe967, 0xe968, 0xe969, 0xe96a, 0xe96b, 0xe96c, 0xe96d,
        0xe96e, 0xe96f, 0xe970, 0xe971, 0xe972, 0xe973, 0xe974, 0xe975, 0xe976, 0xe977,
        0xe978, 0xe979, 0xe97a, 0xe97b, 0xe97c, 0xe97d, 0xe97e, 0xe97f, 0xe980, 0xe981,
        0xe982, 0xe983, 0xe984, 0xe985, 0xe986, 0xe987, 0xe988, 0xe989, 0xe98a, 0xe98b,
        0xe98c, 0xe98d, 0xe98e, 0xe98f, 0xe990, 0xe991, 0xe992, 0xe993, 0xe994, 0xe995,
        0xe996, 0xe997, 0xe998, 0xe999, 0xe99a, 0xe99b, 0xe99c, 0xe99d, 0xe99e, 0xe99f,
        0xe9a0, 0xe9a1, 0xe9a2, 0xe9a3, 0xe9a4, 0xe9a5, 0xe9a6, 0xe9a7, 0xe9a8, 0xe9a9,
        0xe9aa, 0xe9ab, 0xe9ac, 0xe9ad, 0xe9ae, 0xe9af, 0xe9b0, 0xe9b1, 0xe9b2, 0xe9b3,
        0xe9b4, 0xe9b5, 0xe9b6, 0xe9b7, 0xe9b8, 0xe9b9, 0xe9ba, 0xe9bb, 0xe9bc, 0xe9bd,
        0xe9be, 0xe9bf, 0xe9c0, 0xe9c1, 0xe9c2, 0xe9c3, 0xe9c4, 0xe9c5, 0xe9c6, 0xe9c7,
        0xe9c8, 0xe9c9, 0xe9ca, 0xe9cb, 0xe9cc, 0xe9cd, 0xe9ce, 0xe9cf, 0xe9d0, 0xe9d1,
        0xe9d2, 0xe9d3, 0xe9d4, 0xe9d5, 0xe9d6, 0xe9d7, 0xe9d8, 0xe9d9, 0xe9da, 0xe9db,
        0xe9dc, 0xe9dd, 0xe9de, 0xe9df, 0xe9e0, 0xe9e1, 0xe9e2, 0xe9e3, 0xe9e4, 0xe9e5,
        0xe9e6, 0xe9e7, 0xe9e8, 0xe9e9, 0xe9ea, 0xe9eb, 0xe9ec, 0xe9ed, 0xe9ee, 0xe9ef,
        0xe9f0, 0xe9f1, 0xe9f2, 0xe9f3, 0xe9f4, 0xe9f5, 0xe9f6, 0xe9f7, 0xe9f8, 0xe9f9,
        0xe9fa, 0xe9fb, 0xe9fc, 0xe9fd, 0xe9fe, 0xe9ff, 0xea00, 0xea01, 0xea02, 0xea03,
        0xea04, 0xea05, 0xea06, 0xea07, 0xea08, 0xea09, 0xea0a, 0xea0b, 0xea0c, 0xea0d,
        0xea0e, 0xea0f, 0xea10, 0xea11, 0xea12, 0xea13, 0xea14, 0xea15, 0xea16, 0xea17,
        0xea18, 0xea19, 0xea1a, 0xea1b, 0xea1c, 0xea1d, 0xea1e, 0xea1f, 0xea20, 0xea21,
        0xea22, 0xea23, 0xea24, 0xea25, 0xea26, 0xea27,
    ]

    context = display.get_display_context()
    title_font = context.fonts.get("title", context.fontdisks)
    content_top = menus.get_standard_content_top(title, title_font=title_font)

    font_path = display.ASSETS_DIR / "fonts" / "his.ttf"
    icon_size = 16
    icon_font = ImageFont.truetype(str(font_path), icon_size)

    # Grid settings
    icon_spacing = 4
    icons_per_row = 6
    row_height = icon_size + icon_spacing

    # Calculate total rows and scrolling
    total_icons = len(all_icon_codes)
    total_rows = (total_icons + icons_per_row - 1) // icons_per_row
    rows_per_page = max(1, (context.height - content_top - 12) // row_height)
    max_offset = max(0, total_rows - rows_per_page)
    scroll_offset = 0

    def render(offset: int) -> int:
        offset = max(0, min(offset, max_offset))

        draw = context.draw
        draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        draw.text((context.x - 11, context.top), title, font=title_font, fill=255)

        # Draw grid of icons
        start_row = offset
        end_row = min(total_rows, offset + rows_per_page)

        current_y = content_top
        for row in range(start_row, end_row):
            start_idx = row * icons_per_row
            end_idx = min(total_icons, start_idx + icons_per_row)

            # Center the row horizontally
            icons_in_row = end_idx - start_idx
            row_width = icons_in_row * (icon_size + icon_spacing) - icon_spacing
            start_x = (context.width - row_width) // 2

            current_x = start_x
            for idx in range(start_idx, end_idx):
                icon_code = all_icon_codes[idx]
                glyph = chr(icon_code)
                draw.text((current_x, current_y), glyph, font=icon_font, fill=255)
                current_x += icon_size + icon_spacing

            current_y += row_height

        # Show scroll indicator and count
        if total_rows > rows_per_page:
            footer_text = f"▲▼ scroll • {total_icons} icons"
            footer_font = context.fontdisks
            footer_height = display._get_line_height(footer_font)
            footer_y = context.height - footer_height - 1
            footer_x = context.x - 11
            draw.text((footer_x, footer_y), footer_text, font=footer_font, fill=255)
        else:
            # Just show count
            footer_text = f"{total_icons} icons"
            footer_font = context.fontdisks
            footer_height = display._get_line_height(footer_font)
            footer_y = context.height - footer_height - 1
            footer_x = context.x - 11
            draw.text((footer_x, footer_y), footer_text, font=footer_font, fill=255)

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
