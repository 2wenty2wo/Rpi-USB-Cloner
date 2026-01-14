from __future__ import annotations

import time
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


def calculate_horizontal_scroll_offset(
    *,
    now: float,
    scroll_start_time: Optional[float],
    text_width: float,
    max_width: int,
    scroll_gap: int = 20,
    target_cycle_seconds: float = 6.0,
    scroll_start_delay: float = 0.0,
) -> int:
    if scroll_start_time is None or text_width <= max_width:
        return 0
    elapsed = max(0.0, now - scroll_start_time)
    pause_duration = max(0.0, scroll_start_delay)
    cycle_width = text_width + scroll_gap
    target_cycle_seconds = max(0.0, target_cycle_seconds)
    travel_duration = max(0.0, target_cycle_seconds - pause_duration)
    cycle_duration = pause_duration + travel_duration
    if cycle_width > 0 and travel_duration > 0 and cycle_duration > 0:
        scroll_speed = cycle_width / travel_duration
        phase = elapsed % cycle_duration
        if phase >= pause_duration:
            travel_phase = phase - pause_duration
            return -int((travel_phase * scroll_speed) % cycle_width)
    return 0


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
    footer: Optional[Iterable[str]] = None,
    footer_positions: Optional[Iterable[int]] = None,
    footer_selected_index: Optional[int] = None,
    footer_font=None,
    content_top: Optional[int] = None,
    enable_horizontal_scroll: bool = False,
    scroll_start_time: Optional[float] = None,
    scroll_start_delay: float = 0.0,
    target_cycle_seconds: float = 6.0,
    scroll_gap: int = 20,
    screen_id: Optional[str] = None,
    clear: bool = True,
) -> None:
    context = display.get_display_context()
    draw = context.draw
    if clear:
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
    if content_top is not None:
        current_y = max(current_y, content_top)
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
        footer=footer,
        footer_font=footer_font,
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
    items_list: list[str] = []
    item_widths: list[float] = []
    for item_index, item in enumerate(items_seq):
        item_width = _measure_text_width(list_font, item)
        item_widths.append(item_width)
        if enable_horizontal_scroll and item_index == selected_index and screen_id == "images":
            items_list.append(item)
        else:
            items_list.append(_truncate_text(item, list_font, max_item_width))
    start_index = max(scroll_offset, 0)
    end_index = min(start_index + visible_rows, len(items_list))
    for row_index, item_index in enumerate(range(start_index, end_index)):
        row_top = current_y + row_index * row_height
        text_y = row_top + max(0, (row_height - line_height) // 2)
        is_selected = item_index == selected_index
        text_color = 255
        x_offset = 0
        if enable_horizontal_scroll and is_selected and screen_id == "images":
            x_offset = calculate_horizontal_scroll_offset(
                now=time.monotonic(),
                scroll_start_time=scroll_start_time,
                text_width=item_widths[item_index],
                max_width=max_item_width,
                scroll_gap=scroll_gap,
                target_cycle_seconds=target_cycle_seconds,
                scroll_start_delay=scroll_start_delay,
            )
        # Draw text with offset for alignment
        draw.text(
            (left_margin + selector_width + x_offset, text_y),
            items_list[item_index],
            font=list_font,
            fill=text_color,
        )
        if enable_horizontal_scroll and is_selected and screen_id == "images":
            draw.rectangle(
                (
                    0,
                    row_top,
                    left_margin + selector_width,
                    row_top + row_height,
                ),
                outline=0,
                fill=0,
            )
        # Draw selector for selected item
        if is_selected:
            draw.text((left_margin, text_y), selector, font=list_font, fill=text_color)

    footer_font = None
    footer_height = 0
    footer_padding = 1
    footer_y = 0
    if status_line:
        footer_font = status_font or list_font
        footer_height = _get_line_height(footer_font)
        footer_y = context.height - footer_height - footer_padding
        content_bottom = footer_y - footer_padding
    elif footer:
        footer_font = footer_font or context.fonts.get("footer", context.fontdisks)
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

    if status_line:
        # Draw white background bar for footer (full screen width)
        draw.rectangle(
            (0, footer_y - footer_padding + 1, context.width, context.height),
            outline=255,
            fill=255
        )
        max_status_width = context.width - left_margin - 1
        footer_text = _truncate_text(status_line, footer_font, max_status_width)
        # Draw text in black on the white background
        draw.text((left_margin, footer_y), footer_text, font=footer_font, fill=0)
    elif footer:
        footer_items = list(footer)
        footer_positions_list = list(footer_positions) if footer_positions is not None else []
        if not footer_positions_list:
            spacing = context.width // (len(footer_items) + 1)
            footer_positions_list = [
                (spacing * (index + 1)) - 10 for index in range(len(footer_items))
            ]
        for footer_index, label in enumerate(footer_items):
            x_pos = footer_positions_list[footer_index]
            text_bbox = draw.textbbox((x_pos, footer_y), label, font=footer_font)
            if footer_selected_index is not None and footer_index == footer_selected_index:
                draw.rectangle(
                    (text_bbox[0] - 3, text_bbox[1] - 1, text_bbox[2] + 3, text_bbox[3] + 2),
                    outline=0,
                    fill=1,
                )
                draw.text((x_pos, footer_y), label, font=footer_font, fill=0)
            else:
                draw.text((x_pos, footer_y), label, font=footer_font, fill=255)

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
    footer: Optional[Iterable[str]] = None,
    footer_font=None,
    footer_padding: int = 1,
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
    elif footer:
        footer_font = footer_font or context.fonts.get("footer", context.fontdisks)
        footer_height = _get_line_height(footer_font)
        footer_gap = footer_padding

    available_height = context.height - current_y - footer_height - footer_gap - padding
    return max(1, available_height // row_height)
