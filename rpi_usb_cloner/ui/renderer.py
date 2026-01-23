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
    # Acquire lock to ensure atomic rendering (prevent partial frame captures)
    with display._display_lock:
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
            if (
                enable_horizontal_scroll
                and item_index == selected_index
                and screen_id == "images"
            ):
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
                draw.text(
                    (left_margin, text_y), selector, font=list_font, fill=text_color
                )

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
                fill=255,
            )
            max_status_width = context.width - left_margin - 1
            footer_text = _truncate_text(status_line, footer_font, max_status_width)
            # Draw text in black on the white background
            draw.text((left_margin, footer_y), footer_text, font=footer_font, fill=0)
        elif footer:
            footer_items = list(footer)
            footer_positions_list = (
                list(footer_positions) if footer_positions is not None else []
            )
            if not footer_positions_list:
                spacing = context.width // (len(footer_items) + 1)
                footer_positions_list = [
                    (spacing * (index + 1)) - 10 for index in range(len(footer_items))
                ]
            for footer_index, label in enumerate(footer_items):
                x_pos = footer_positions_list[footer_index]
                text_bbox = draw.textbbox((x_pos, footer_y), label, font=footer_font)
                if (
                    footer_selected_index is not None
                    and footer_index == footer_selected_index
                ):
                    draw.rectangle(
                        (
                            text_bbox[0] - 3,
                            text_bbox[1] - 1,
                            text_bbox[2] + 3,
                            text_bbox[3] + 2,
                        ),
                        outline=0,
                        fill=1,
                    )
                    draw.text((x_pos, footer_y), label, font=footer_font, fill=0)
                else:
                    draw.text((x_pos, footer_y), label, font=footer_font, fill=255)

        context.disp.display(context.image)
        display.mark_display_dirty()


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


def render_icon_menu_screen(
    title: str,
    items: Iterable[str],
    selected_index: int,
    scroll_offset: int,
    status_line: Optional[str] = None,
    title_font=None,
    title_icon: Optional[str] = None,
    title_icon_font=None,
    items_font=None,
    icon_font=None,
    status_font=None,
    footer: Optional[Iterable[str]] = None,
    footer_positions: Optional[Iterable[int]] = None,
    footer_selected_index: Optional[int] = None,
    footer_font=None,
    item_icons: Optional[Iterable[Optional[str]]] = None,
    clear: bool = True,
) -> None:
    """
    Render a menu screen with icons in horizontal layout.

    Args:
        title: Screen title
        items: Menu item labels
        selected_index: Currently selected item index
        scroll_offset: Horizontal scroll offset (in items)
        status_line: Optional status line at bottom
        title_font: Font for title
        title_icon: Icon for title
        title_icon_font: Font for title icon
        items_font: Font for item labels
        icon_font: Font for item icons (24px Lucide)
        status_font: Font for status line
        footer: Footer items
        footer_positions: Footer item positions
        footer_selected_index: Selected footer item
        footer_font: Font for footer
        item_icons: Icons for each menu item
        clear: Whether to clear screen before rendering
    """
    context = display.get_display_context()
    draw = context.draw

    # Acquire lock to ensure atomic rendering
    with display._display_lock:
        if clear:
            draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

        # Draw title
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

        # Calculate available space
        list_font = items_font or context.fonts.get("items", context.fontdisks)
        icon_display_font = icon_font or display._get_lucide_font(size=24)

        # Footer setup
        footer_height = 0
        footer_padding = 1
        footer_y = 0
        if status_line:
            footer_font = status_font or list_font
            footer_height = _get_line_height(footer_font)
            footer_y = context.height - footer_height - footer_padding
        elif footer:
            footer_font = footer_font or context.fonts.get("footer", context.fontdisks)
            footer_height = _get_line_height(footer_font)
            footer_y = context.height - footer_height - footer_padding

        content_bottom = (
            footer_y - footer_padding if footer or status_line else context.height - 1
        )

        # Icon layout parameters
        icon_size = 24
        label_height = _get_line_height(list_font)

        # Calculate layout to fit maximum icons on screen
        # Total width: 128px, leave 2px margins on each side = 124px available
        left_margin = 2
        available_width = context.width - (left_margin * 2)

        # Calculate how many icons can fit on screen
        items_seq = list(items)
        total_items = len(items_seq)

        # Determine item width based on total items to maximize space usage
        # For main menu (4 items), allocate width to fit all on screen
        if total_items <= 4:
            # Fit all items on screen with equal spacing and a small gap
            item_gap = 2
            available_width = available_width - (item_gap * (total_items - 1))
            icon_width = max(1, available_width // total_items)
            visible_icons = total_items
        else:
            # Default behavior for more items
            icon_width = 32
            visible_icons = max(1, available_width // icon_width)
            item_gap = 0

        # Prepare icons
        icons_seq = list(item_icons) if item_icons else [None] * len(items_seq)

        # Calculate scroll position to keep selected item visible
        if selected_index < scroll_offset:
            scroll_offset = selected_index
        elif selected_index >= scroll_offset + visible_icons:
            scroll_offset = selected_index - visible_icons + 1

        # Calculate content area
        content_height = content_bottom - current_y
        icon_area_height = icon_size + label_height + 4
        icon_start_y = current_y + (content_height - icon_area_height) // 2

        # Draw icons
        start_index = max(0, scroll_offset)
        end_index = min(start_index + visible_icons, len(items_seq))

        for display_index, item_index in enumerate(range(start_index, end_index)):
            x_pos = left_margin + display_index * (icon_width + item_gap)
            is_selected = item_index == selected_index

            # Calculate positions
            icon_x = x_pos + (icon_width - icon_size) // 2
            icon_y = icon_start_y

            # Draw label below icon
            label = items_seq[item_index]
            label_max_width = icon_width
            label_width = _measure_text_width(list_font, label)
            if label_width > label_max_width:
                truncated_label = _truncate_text(label, list_font, label_max_width)
                label_width = _measure_text_width(list_font, truncated_label)
            else:
                truncated_label = label

            label_x = x_pos + (icon_width - label_width) // 2
            label_y = icon_start_y + icon_size + 2

            # Highlight selected item with white background and inverted colors
            if is_selected:
                # Draw filled white background box
                box_padding_top = 1
                draw.rectangle(
                    (
                        x_pos,
                        icon_start_y - box_padding_top,
                        x_pos + icon_width - 1,
                        label_y + label_height - 1,
                    ),
                    outline=255,
                    fill=255,  # White fill for selected item
                )
                # Draw icon and text in black (inverted)
                icon_char = icons_seq[item_index]
                if icon_char:
                    draw.text(
                        (icon_x, icon_y), icon_char, font=icon_display_font, fill=0
                    )
                draw.text((label_x, label_y), truncated_label, font=list_font, fill=0)
            else:
                # Draw normal (white on black)
                icon_char = icons_seq[item_index]
                if icon_char:
                    draw.text(
                        (icon_x, icon_y), icon_char, font=icon_display_font, fill=255
                    )
                draw.text((label_x, label_y), truncated_label, font=list_font, fill=255)

        # Draw horizontal scrollbar only if needed (more items than can fit on screen)
        needs_scrollbar = len(items_seq) > visible_icons
        if needs_scrollbar and visible_icons < len(items_seq):
            scrollbar_height = 2
            scrollbar_y = content_bottom - scrollbar_height - 1
            track_left = 2
            track_right = context.width - 3

            # Draw track (dotted line)
            for track_x in range(track_left, track_right + 1, 3):
                draw.point((track_x, scrollbar_y + 1), fill=255)

            # Draw thumb
            track_width = track_right - track_left + 1
            min_thumb_width = 4
            thumb_width = max(
                min_thumb_width, int(track_width * visible_icons / len(items_seq))
            )
            max_scroll = max(len(items_seq) - visible_icons, 0)
            thumb_range = max(track_width - thumb_width, 0)

            if max_scroll > 0:
                thumb_offset = int(round((scroll_offset / max_scroll) * thumb_range))
            else:
                thumb_offset = 0

            thumb_left = track_left + thumb_offset
            thumb_right = thumb_left + thumb_width

            draw.rectangle(
                (
                    thumb_left,
                    scrollbar_y,
                    thumb_right,
                    scrollbar_y + scrollbar_height - 1,
                ),
                outline=255,
                fill=255,
            )

        # Draw footer/status line
        if status_line:
            # Draw white background bar for footer
            draw.rectangle(
                (0, footer_y - footer_padding + 1, context.width, context.height),
                outline=255,
                fill=255,
            )
            left_margin = context.x - 11
            max_status_width = context.width - left_margin - 1
            footer_text = _truncate_text(status_line, footer_font, max_status_width)
            draw.text((left_margin, footer_y), footer_text, font=footer_font, fill=0)
        elif footer:
            footer_items = list(footer)
            footer_positions_list = (
                list(footer_positions) if footer_positions is not None else []
            )
            if not footer_positions_list:
                spacing = context.width // (len(footer_items) + 1)
                footer_positions_list = [
                    (spacing * (index + 1)) - 10 for index in range(len(footer_items))
                ]
            for footer_index, label in enumerate(footer_items):
                x_pos = footer_positions_list[footer_index]
                text_bbox = draw.textbbox((x_pos, footer_y), label, font=footer_font)
                if (
                    footer_selected_index is not None
                    and footer_index == footer_selected_index
                ):
                    draw.rectangle(
                        (
                            text_bbox[0] - 3,
                            text_bbox[1] - 1,
                            text_bbox[2] + 3,
                            text_bbox[3] + 2,
                        ),
                        outline=0,
                        fill=1,
                    )
                    draw.text((x_pos, footer_y), label, font=footer_font, fill=0)
                else:
                    draw.text((x_pos, footer_y), label, font=footer_font, fill=255)

        context.disp.display(context.image)
        display.mark_display_dirty()
