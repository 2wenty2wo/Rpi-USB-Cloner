from __future__ import annotations

from typing import Iterable, Optional

from rpi_usb_cloner.ui import display


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


def render_menu_screen(
    title: str,
    items: Iterable[str],
    selected_index: int,
    scroll_offset: int,
    status_line: Optional[str] = None,
    visible_rows: int = 4,
    title_font=None,
    items_font=None,
    status_font=None,
) -> None:
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    current_y = context.top
    header_font = title_font or context.fonts.get("title", context.fontdisks)
    if title:
        draw.text((context.x - 11, current_y), title, font=header_font, fill=255)
        title_height = _get_line_height(header_font)
        current_y += title_height + display.TITLE_PADDING

    list_font = items_font or context.fonts.get("items", context.fontdisks)
    line_height = _get_line_height(list_font)
    row_height = line_height + 4
    left_margin = context.x - 11

    items_list = list(items)
    start_index = max(scroll_offset, 0)
    end_index = min(start_index + visible_rows, len(items_list))
    for row_index, item_index in enumerate(range(start_index, end_index)):
        row_top = current_y + row_index * row_height
        is_selected = item_index == selected_index
        if is_selected:
            draw.rectangle((0, row_top - 1, context.width, row_top + row_height - 1), outline=0, fill=1)
        text_color = 0 if is_selected else 255
        draw.text((left_margin, row_top + 1), items_list[item_index], font=list_font, fill=text_color)

    if status_line:
        footer_font = status_font or context.fonts.get("footer", context.fontcopy)
        footer_height = _get_line_height(footer_font)
        footer_y = context.height - footer_height - 2
        draw.text((left_margin, footer_y), status_line, font=footer_font, fill=255)

    context.disp.display(context.image)
