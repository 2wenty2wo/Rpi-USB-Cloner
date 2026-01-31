from __future__ import annotations

import time
from typing import Iterable

from PIL import Image, ImageDraw

from rpi_usb_cloner.ui import display
from rpi_usb_cloner.ui.toggle import (
    TOGGLE_HEIGHT,
    TOGGLE_WIDTH,
    get_toggle,
    parse_toggle_label,
)


# Default visible rows - matches app.state.VISIBLE_ROWS
DEFAULT_VISIBLE_ROWS = 4

# Font metrics cache: {font_id: line_height}
_line_height_cache: dict[int, int] = {}

# Status indicator cache: (timestamp, indicators_list)
_status_indicators_cache: tuple[float, list] | None = None
_STATUS_INDICATORS_TTL = 1.0  # 1 second cache


def _get_cached_line_height(font, min_height=8) -> int:
    """Get line height for font with caching.
    
    Font metrics don't change during runtime, so we cache by font object id.
    """
    font_id = id(font)
    if font_id not in _line_height_cache:
        _line_height_cache[font_id] = _compute_line_height(font, min_height)
    return _line_height_cache[font_id]


def _compute_line_height(font, min_height=8) -> int:
    """Compute line height for font (without caching)."""
    line_height = min_height
    try:
        bbox = font.getbbox("Ag")
        line_height = max(bbox[3] - bbox[1], line_height)
    except AttributeError:
        if hasattr(font, "getmetrics"):
            ascent, descent = font.getmetrics()
            line_height = max(ascent + descent, line_height)
    return line_height


def _get_line_height(font, min_height=8) -> int:
    """Get line height for font (with caching).
    
    Deprecated: Use _get_cached_line_height directly for new code.
    Kept for backward compatibility.
    """
    return _get_cached_line_height(font, min_height)


def _get_status_indicators(app_context=None) -> list:
    """Collect all status indicators for the status bar.

    Returns:
        List of StatusIndicator objects sorted by priority.
    """
    global _status_indicators_cache
    
    now = time.monotonic()
    
    # Return cached result if within TTL
    if _status_indicators_cache is not None:
        cached_time, cached_indicators = _status_indicators_cache
        if now - cached_time < _STATUS_INDICATORS_TTL:
            return cached_indicators
    
    # Compute fresh indicators
    try:
        from rpi_usb_cloner.ui.status_bar import collect_status_indicators

        indicators = collect_status_indicators(app_context)
    except Exception:
        indicators = []
    
    # Cache the result
    _status_indicators_cache = (now, indicators)
    return indicators


def invalidate_status_indicators_cache() -> None:
    """Invalidate the status indicators cache.
    
    Call this when status bar settings change to force a refresh.
    """
    global _status_indicators_cache
    _status_indicators_cache = None


def _get_drive_status_text() -> str:
    """Build the drive status text showing U (USB) and R (Repo) counts.

    Format: "U2|R1" if both have drives, "U2" if only USB, "R1" if only repo.
    Returns empty string if no drives are connected.

    Note: This is kept for backward compatibility. New code should use
    _get_status_indicators() which includes WiFi, web server, and operation status.
    """
    try:
        from rpi_usb_cloner.services.drives import get_drive_counts

        usb_count, repo_count = get_drive_counts()
    except Exception:
        return ""

    parts = []
    if usb_count > 0:
        parts.append(f"U{usb_count}")
    if repo_count > 0:
        parts.append(f"R{repo_count}")

    return "|".join(parts)


def _get_line_height(font, min_height=8) -> int:
    """Get line height for font (with caching).
    
    Deprecated: Use _get_cached_line_height directly for new code.
    Kept for backward compatibility.
    """
    return _get_cached_line_height(font, min_height)


def _measure_text_width(font, text: str) -> int:
    try:
        return int(font.getlength(text))
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
    scroll_start_time: float | None,
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


def _render_menu(
    *,
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    title: str,
    items: Iterable[str],
    selected_index: int,
    scroll_offset: int,
    status_line: str | None,
    visible_rows: int,
    title_font=None,
    title_icon: str | None = None,
    title_icon_font=None,
    items_font=None,
    status_font=None,
    footer: Iterable[str] | None = None,
    footer_positions: Iterable[int] | None = None,
    footer_selected_index: int | None = None,
    footer_font=None,
    content_top: int | None = None,
    enable_horizontal_scroll: bool = False,
    scroll_start_time: float | None = None,
    scroll_start_delay: float = 0.0,
    target_cycle_seconds: float = 6.0,
    scroll_gap: int = 20,
    now: float | None = None,
    last_activity_time: float | None = None,
    screen_id: str | None = None,
    clear: bool = True,
    app_context=None,
    selected_item_icon: str | None = None,
) -> None:
    context = display.get_display_context()
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
            draw=draw,
            image=image,
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
    item_widths: list[int] = []
    item_toggles: list[bool | None] = []  # Track toggle states for each item

    # Reserve space for toggle icon if present (toggle width + 2px spacing)
    toggle_space = TOGGLE_WIDTH + 2

    for item_index, item in enumerate(items_seq):
        # Parse toggle marker from item label
        clean_label, toggle_state = parse_toggle_label(item)
        item_toggles.append(toggle_state)

        # Calculate width based on clean label (without toggle marker)
        item_width = _measure_text_width(list_font, clean_label)
        item_widths.append(item_width)

        # Adjust max width for items with toggles to leave room for the icon
        effective_max_width = max_item_width
        if toggle_state is not None:
            effective_max_width = max(0, max_item_width - toggle_space)

        if (
            enable_horizontal_scroll
            and item_index == selected_index
            and screen_id == "images"
        ):
            items_list.append(clean_label)
        else:
            items_list.append(_truncate_text(clean_label, list_font, effective_max_width))
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
                now=now if now is not None else time.monotonic(),
                scroll_start_time=scroll_start_time,
                text_width=item_widths[item_index],
                max_width=max_item_width,
                scroll_gap=scroll_gap,
                target_cycle_seconds=target_cycle_seconds,
                scroll_start_delay=scroll_start_delay,
            )
        # Draw text with offset for alignment
        text_x = left_margin + selector_width + x_offset
        draw.text(
            (text_x, text_y),
            items_list[item_index],
            font=list_font,
            fill=text_color,
        )

        # Draw toggle icon if item has a toggle state
        toggle_state = item_toggles[item_index]
        if toggle_state is not None:
            # Get the displayed text width (may be truncated)
            displayed_text_width = _measure_text_width(
                list_font, items_list[item_index]
            )
            # Position toggle after text with 2px spacing
            toggle_x = text_x + displayed_text_width + 2
            # Center toggle vertically within the row
            toggle_y = row_top + max(0, (row_height - TOGGLE_HEIGHT) // 2)
            # Get and paste the toggle image
            toggle_img = get_toggle(toggle_state)
            image.paste(toggle_img, (toggle_x, toggle_y))

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

    # Draw selected item icon preview in the right side if enabled
    if selected_item_icon and not selected_item_icon.endswith(".png"):
        from rpi_usb_cloner.config.settings import get_bool

        if get_bool("menu_icon_preview_enabled", default=False):
            icon_preview_size = 24
            icon_font = display.get_lucide_font_sized(icon_preview_size)

            # Calculate icon dimensions
            icon_bbox = icon_font.getbbox(selected_item_icon)
            icon_width = icon_bbox[2] - icon_bbox[0]
            icon_height = icon_bbox[3] - icon_bbox[1]

            # Position: right side, vertically centered in content area
            # Leave space for scrollbar (4px from right edge)
            icon_x = context.width - icon_width - 4
            if needs_scrollbar:
                icon_x -= scrollbar_width + scrollbar_padding

            # Center vertically between content_top and content_bottom
            content_height = content_bottom - content_top
            icon_y = content_top + (content_height - icon_height) // 2

            # Adjust for font baseline offset
            icon_y -= icon_bbox[1]

            draw.text(
                (icon_x, icon_y),
                selected_item_icon,
                font=icon_font,
                fill=255,
            )

    if status_line:
        # Draw white background bar for footer (full screen width)
        draw.rectangle(
            (0, footer_y - footer_padding + 1, context.width, context.height),
            outline=255,
            fill=255,
        )

        # Get all status indicators (WiFi, Web, Bluetooth, Drive counts)
        status_indicators = _get_status_indicators(app_context)
        total_status_width = 0
        status_right_margin = 1
        status_spacing = 4  # Space between status_line text and status indicators
        indicator_spacing = 1  # 1px space between icons/boxes
        box_padding_x = 1  # Horizontal padding inside each text box

        if status_indicators:
            # Use silkscreen font (fontdisks) for text indicators
            status_indicator_font = context.fonts.get("items", context.fontdisks)
            status_font_height = _get_line_height(status_indicator_font)

            # Load icons and calculate widths for all indicators
            indicator_data = []  # List of (width, icon_image or None)
            for indicator in status_indicators:
                if indicator.is_icon:
                    # Load icon image from icon_path
                    try:
                        icon_img = Image.open(indicator.icon_path).convert("1")
                        indicator_data.append((icon_img.width, icon_img))
                        total_status_width += icon_img.width
                    except Exception:
                        # Fallback to label if icon fails to load
                        label_width = _measure_text_width(
                            status_indicator_font, indicator.label or "?"
                        )
                        indicator_data.append((label_width + (box_padding_x * 2), None))
                        total_status_width += label_width + (box_padding_x * 2)
                else:
                    # Text label with box
                    label_width = _measure_text_width(
                        status_indicator_font, indicator.label
                    )
                    indicator_data.append((label_width + (box_padding_x * 2), None))
                    total_status_width += label_width + (box_padding_x * 2)

            # Add 1px spacing between indicators
            if len(status_indicators) > 1:
                total_status_width += indicator_spacing * (len(status_indicators) - 1)

            # Draw indicators from right to left (lowest priority first = rightmost)
            current_x = context.width - status_right_margin
            # Calculate vertical position - leave 1px white border at top and bottom
            footer_top = footer_y - footer_padding + 1
            footer_bottom = context.height - 1
            box_top = footer_top + 1  # 1px margin from top of footer
            box_bottom = footer_bottom - 1  # 1px margin from bottom of footer
            footer_height = box_bottom - box_top + 1

            for i, indicator in enumerate(status_indicators):
                item_width, icon_img = indicator_data[i]

                if icon_img is not None:
                    # Draw icon (no box, just the icon centered vertically)
                    icon_left = current_x - icon_img.width
                    # Center 7px icon vertically in footer
                    icon_top = box_top + (footer_height - icon_img.height) // 2

                    # Icons are black on white - paste directly onto white footer
                    # The icons should be black pixels that show on white background
                    image.paste(icon_img, (icon_left, icon_top))

                    current_x = icon_left - indicator_spacing
                else:
                    # Draw text with box
                    box_left = current_x - item_width
                    box_right = current_x - 1

                    if indicator.inverted:
                        # Inverted style: black box, white text
                        draw.rectangle(
                            (box_left, box_top, box_right, box_bottom),
                            outline=0,
                            fill=0,
                        )
                        text_fill = 255
                    else:
                        # Normal style: white box with black outline, black text
                        draw.rectangle(
                            (box_left, box_top, box_right, box_bottom),
                            outline=0,
                            fill=255,
                        )
                        text_fill = 0

                    # Draw text inside box, centered vertically
                    text_x = box_left + box_padding_x
                    box_inner_height = box_bottom - box_top + 1
                    text_y = box_top + (box_inner_height - status_font_height) // 2
                    draw.text(
                        (text_x, text_y),
                        indicator.label,
                        font=status_indicator_font,
                        fill=text_fill,
                    )

                    current_x = box_left - indicator_spacing

        # Calculate available width for status line text
        max_status_width = context.width - left_margin - 1
        if status_indicators:
            max_status_width -= total_status_width + status_spacing + status_right_margin
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


def calculate_footer_bounds(
    *,
    status_line: str | None = None,
    status_font=None,
    footer: Iterable[str] | None = None,
    footer_font=None,
    items_font=None,
    footer_padding: int = 1,
) -> tuple[int, int]:
    context = display.get_display_context()
    list_font = items_font or context.fonts.get("items", context.fontdisks)
    footer_height = 0
    footer_y = context.height
    if status_line:
        footer_font = status_font or list_font
        footer_height = _get_line_height(footer_font)
        footer_y = context.height - footer_height - footer_padding
    elif footer:
        footer_font = footer_font or context.fonts.get("footer", context.fontdisks)
        footer_height = _get_line_height(footer_font)
        footer_y = context.height - footer_height - footer_padding
    if footer_height <= 0:
        return (context.height, context.height)
    footer_start = footer_y - footer_padding + 1
    footer_start = max(0, min(footer_start, context.height))
    return (footer_start, context.height)


def render_menu_screen(
    title: str,
    items: Iterable[str],
    selected_index: int,
    scroll_offset: int,
    status_line: str | None = None,
    visible_rows: int = DEFAULT_VISIBLE_ROWS,
    title_font=None,
    title_icon: str | None = None,
    title_icon_font=None,
    items_font=None,
    status_font=None,
    footer: Iterable[str] | None = None,
    footer_positions: Iterable[int] | None = None,
    footer_selected_index: int | None = None,
    footer_font=None,
    content_top: int | None = None,
    enable_horizontal_scroll: bool = False,
    scroll_start_time: float | None = None,
    scroll_start_delay: float = 0.0,
    target_cycle_seconds: float = 6.0,
    scroll_gap: int = 20,
    now: float | None = None,
    last_activity_time: float | None = None,
    screen_id: str | None = None,
    clear: bool = True,
    app_context=None,
    selected_item_icon: str | None = None,
) -> None:
    context = display.get_display_context()
    draw = context.draw
    # Acquire lock to ensure atomic rendering (prevent partial frame captures)
    with display._display_lock:
        _render_menu(
            draw=draw,
            image=context.image,
            title=title,
            items=items,
            selected_index=selected_index,
            scroll_offset=scroll_offset,
            status_line=status_line,
            visible_rows=visible_rows,
            title_font=title_font,
            title_icon=title_icon,
            title_icon_font=title_icon_font,
            items_font=items_font,
            status_font=status_font,
            footer=footer,
            footer_positions=footer_positions,
            footer_selected_index=footer_selected_index,
            footer_font=footer_font,
            content_top=content_top,
            enable_horizontal_scroll=enable_horizontal_scroll,
            scroll_start_time=scroll_start_time,
            scroll_start_delay=scroll_start_delay,
            target_cycle_seconds=target_cycle_seconds,
            scroll_gap=scroll_gap,
            now=now,
            last_activity_time=last_activity_time,
            screen_id=screen_id,
            clear=clear,
            app_context=app_context,
            selected_item_icon=selected_item_icon,
        )

        context.disp.display(context.image)
        display.mark_display_dirty()


def render_menu_image(
    title: str,
    items: Iterable[str],
    selected_index: int,
    scroll_offset: int,
    status_line: str | None = None,
    visible_rows: int = DEFAULT_VISIBLE_ROWS,
    title_font=None,
    title_icon: str | None = None,
    title_icon_font=None,
    items_font=None,
    status_font=None,
    footer: Iterable[str] | None = None,
    footer_positions: Iterable[int] | None = None,
    footer_selected_index: int | None = None,
    footer_font=None,
    content_top: int | None = None,
    enable_horizontal_scroll: bool = False,
    scroll_start_time: float | None = None,
    scroll_start_delay: float = 0.0,
    target_cycle_seconds: float = 6.0,
    scroll_gap: int = 20,
    now: float | None = None,
    last_activity_time: float | None = None,
    screen_id: str | None = None,
    clear: bool = True,
    app_context=None,
    selected_item_icon: str | None = None,
) -> Image.Image:
    context = display.get_display_context()
    image = Image.new("1", (context.width, context.height), 0)
    draw = ImageDraw.Draw(image)
    _render_menu(
        draw=draw,
        image=image,
        title=title,
        items=items,
        selected_index=selected_index,
        scroll_offset=scroll_offset,
        status_line=status_line,
        visible_rows=visible_rows,
        title_font=title_font,
        title_icon=title_icon,
        title_icon_font=title_icon_font,
        items_font=items_font,
        status_font=status_font,
        footer=footer,
        footer_positions=footer_positions,
        footer_selected_index=footer_selected_index,
        footer_font=footer_font,
        content_top=content_top,
        enable_horizontal_scroll=enable_horizontal_scroll,
        scroll_start_time=scroll_start_time,
        scroll_start_delay=scroll_start_delay,
        target_cycle_seconds=target_cycle_seconds,
        scroll_gap=scroll_gap,
        now=now,
        last_activity_time=last_activity_time,
        screen_id=screen_id,
        clear=clear,
        app_context=app_context,
        selected_item_icon=selected_item_icon,
    )
    return image


def calculate_visible_rows(
    title: str,
    title_icon: str | None = None,
    status_line: str | None = None,
    title_font=None,
    items_font=None,
    status_font=None,
    title_icon_font=None,
    padding: int = 1,
    footer: Iterable[str] | None = None,
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
