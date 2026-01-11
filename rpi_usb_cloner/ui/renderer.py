from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from PIL import ImageFont

from rpi_usb_cloner.ui import display


@dataclass(frozen=True)
class StatusLine:
    text: str
    icon: Optional[str] = None
    icon_size: int = 8


def _resolve_status_line(status_line: Optional[str | StatusLine]) -> tuple[Optional[str], Optional[str], int]:
    if isinstance(status_line, StatusLine):
        return status_line.text, status_line.icon, status_line.icon_size
    return status_line, None, 0


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
    status_line: Optional[str | StatusLine] = None,
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
    content_top = current_y

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

    # Calculate selector width for consistent alignment
    selector = "> "
    selector_width = _measure_text_width(list_font, selector)
    items_seq = list(items)
    needs_scrollbar = len(items_seq) > visible_rows
    scrollbar_width = 2
    scrollbar_padding = 1
    max_item_width = context.width - left_margin - selector_width - 1
    if needs_scrollbar:
        max_item_width -= scrollbar_width + scrollbar_padding
    max_item_width = max(0, max_item_width)
    items_list = [
        _truncate_text(item, list_font, max_item_width) for item in items_seq
    ]
    start_index = max(scroll_offset, 0)
    end_index = min(start_index + visible_rows, len(items_list))
    for row_index, item_index in enumerate(range(start_index, end_index)):
        row_top = current_y + row_index * row_height
        text_y = row_top + max(0, (row_height - line_height) // 2)
        is_selected = item_index == selected_index
        text_color = 255
        # Draw selector for selected item
        if is_selected:
            draw.text((left_margin, text_y), selector, font=list_font, fill=text_color)
        # Draw text with offset for alignment
        draw.text((left_margin + selector_width, text_y), items_list[item_index], font=list_font, fill=text_color)

    status_text, status_icon, status_icon_size = _resolve_status_line(status_line)
    footer_font = None
    footer_height = 0
    footer_padding = 1
    footer_y = 0
    if status_text:
        footer_font = status_font or list_font
        footer_height = _get_line_height(footer_font)
        footer_y = context.height - footer_height - footer_padding
        content_bottom = footer_y - footer_padding
    else:
        content_bottom = context.height - 1

    if needs_scrollbar and content_bottom >= content_top:
        track_top = content_top
        track_bottom = content_bottom
        thumb_bottom_limit = content_bottom - 1
        track_height = track_bottom - track_top + 1
        min_thumb_px = 1
        thumb_height = max(
            min_thumb_px,
            int(track_height * visible_rows / len(items_list)),
        )
        max_thumb_height = max(thumb_bottom_limit - track_top, 0)
        if max_thumb_height < min_thumb_px:
            thumb_height = max_thumb_height
        else:
            thumb_height = min(thumb_height, max_thumb_height)
        max_scroll = max(len(items_list) - visible_rows, 0)
        usable_track_height = max_thumb_height
        thumb_range = max(usable_track_height - thumb_height, 0)
        if max_scroll > 0:
            thumb_offset = int(round((scroll_offset / max_scroll) * thumb_range))
        else:
            thumb_offset = 0
        thumb_offset = max(0, min(thumb_offset, thumb_range))
        thumb_top = track_top + thumb_offset
        thumb_top = min(thumb_top, thumb_bottom_limit - thumb_height)
        thumb_top = max(track_top, thumb_top)
        if thumb_top + thumb_height > thumb_bottom_limit:
            thumb_top = max(track_top, thumb_bottom_limit - thumb_height)
        thumb_bottom = thumb_top + thumb_height
        track_right = context.width - 1
        track_left = track_right - (scrollbar_width - 1)
        for track_y in range(track_top, track_bottom + 1, 3):
            draw.point((track_right, track_y), fill=255)
        draw.rectangle(
            (track_left, thumb_top, track_right, thumb_bottom),
            outline=255,
            fill=255,
        )

    if status_text:
        # Draw white background bar for footer (full screen width)
        draw.rectangle(
            (0, footer_y - footer_padding + 1, context.width, context.height),
            outline=255,
            fill=255
        )
        max_status_width = context.width - left_margin - 1
        icon_width = 0
        icon_height = 0
        icon_padding = 1
        icon_font = None
        if status_icon:
            icon_font = ImageFont.truetype(display.LUCIDE_FONT_PATH, status_icon_size)
            icon_width = _measure_text_width(icon_font, status_icon)
            icon_bbox = icon_font.getbbox(status_icon)
            icon_height = icon_bbox[3] - icon_bbox[1]
            max_status_width = max(0, max_status_width - icon_width - icon_padding)
        footer_text = _truncate_text(status_text, footer_font, max_status_width)
        text_x = left_margin
        if status_icon and icon_font:
            icon_y = footer_y + max(0, (footer_height - icon_height) // 2)
            draw.text((left_margin, icon_y), status_icon, font=icon_font, fill=0)
            text_x = left_margin + icon_width + icon_padding
        # Draw text in black on the white background
        draw.text((text_x, footer_y), footer_text, font=footer_font, fill=0)

    context.disp.display(context.image)


def calculate_visible_rows(
    title: str,
    title_icon: Optional[str] = None,
    status_line: Optional[str | StatusLine] = None,
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
    status_text, _, _ = _resolve_status_line(status_line)
    if status_text:
        footer_font = status_font or list_font
        footer_height = _get_line_height(footer_font)
        # Add minimum gap between menu items and footer to prevent overlap
        footer_gap = 4

    available_height = context.height - current_y - footer_height - footer_gap - padding
    return max(1, available_height // row_height)
