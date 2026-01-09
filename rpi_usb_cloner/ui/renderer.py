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


def _measure_text_width(font, text: str) -> float:
    try:
        return font.getlength(text)
    except AttributeError:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]


def _truncate_text(text: str, font, max_width: int) -> str:
    if not text:
        return text
    if _measure_text_width(font, text) <= max_width:
        return text
    ellipsis = "…"
    if _measure_text_width(font, ellipsis) > max_width:
        return ""
    trimmed = text
    while trimmed and _measure_text_width(font, f"{trimmed}{ellipsis}") > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed}{ellipsis}"


def render_menu_screen(
    title: str,
    items: Iterable[str],
    selected_index: int,
    scroll_offset: int,
    status_line: Optional[str] = None,
    visible_rows: int = 4,
    title_font=None,
    title_icon: Optional[str] = None,
    title_icon_font=None,
    items_font=None,
    status_font=None,
) -> None:
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    current_y = context.top
    extra_gap = 1
    header_font = title_font or context.fonts.get("title", context.fontdisks)
    if title:
        layout = display.draw_title_with_icon(
            title,
            title_font=header_font,
            icon=title_icon,
            icon_font=title_icon_font,
            extra_gap=extra_gap,
            left_margin=context.x - 11,
        )
        current_y = layout.content_top

    list_font = items_font or context.fonts.get("items", context.fontdisks)
    line_height = _get_line_height(list_font)
    row_height = line_height + 1
    left_margin = context.x - 11

    max_visible_rows = calculate_visible_rows(
        title=title,
        title_icon=title_icon,
        status_line=status_line,
        title_font=title_font,
        items_font=items_font,
        status_font=status_font,
        title_icon_font=title_icon_font,
    )
    visible_rows = min(visible_rows, max_visible_rows)

    max_item_width = context.width - left_margin - 1
    items_list = [
        _truncate_text(item, list_font, max_item_width) for item in list(items)
    ]
    start_index = max(scroll_offset, 0)
    end_index = min(start_index + visible_rows, len(items_list))
    for row_index, item_index in enumerate(range(start_index, end_index)):
        row_top = current_y + row_index * row_height
        text_y = row_top + max(0, (row_height - line_height) // 2)
        is_selected = item_index == selected_index
        if is_selected:
            draw.rectangle((0, row_top, context.width, row_top + row_height - 1), outline=0, fill=1)
        text_color = 0 if is_selected else 255
        draw.text((left_margin, text_y), items_list[item_index], font=list_font, fill=text_color)

    if status_line:
        footer_font = status_font or list_font
        footer_height = _get_line_height(footer_font)
        footer_padding = 1
        footer_y = context.height - footer_height - footer_padding
        # Draw white background bar for footer (full screen width)
        draw.rectangle(
            (0, footer_y - footer_padding, context.width, context.height),
            outline=255,
            fill=255
        )
        max_status_width = context.width - left_margin - 1
        footer_text = _truncate_text(status_line, footer_font, max_status_width)
        # Draw text in black on the white background
        draw.text((left_margin, footer_y), footer_text, font=footer_font, fill=0)

    context.disp.display(context.image)


def calculate_visible_rows(
    title: str,
    title_icon: Optional[str] = None,
    status_line: Optional[str] = None,
    title_font=None,
    items_font=None,
    status_font=None,
    title_icon_font=None,
    padding: int = 1,
) -> int:
    context = display.get_display_context()
    current_y = context.top
    extra_gap = 1
    header_font = title_font or context.fonts.get("title", context.fontdisks)
    if title:
        icon_height = 0
        if title_icon:
            icon_font = title_icon_font or display._get_lucide_font()
            icon_height = _get_line_height(icon_font)
        title_height = max(_get_line_height(header_font), icon_height)
        current_y += title_height + display.TITLE_PADDING + extra_gap

    list_font = items_font or context.fonts.get("items", context.fontdisks)
    row_height = _get_line_height(list_font) + 1

    footer_height = 0
    footer_gap = 0
    if status_line:
        footer_font = status_font or list_font
        footer_height = _get_line_height(footer_font)
        # Add minimum gap between menu items and footer to prevent overlap
        footer_gap = 4

    available_height = context.height - current_y - footer_height - footer_gap - padding
    return max(1, available_height // row_height)
