import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from PIL import Image, ImageDraw

from rpi_usb_cloner.config import settings
from rpi_usb_cloner.config.settings import (
    DEFAULT_SCROLL_REFRESH_INTERVAL,
    DEFAULT_TRANSITION_FRAME_COUNT,
    DEFAULT_TRANSITION_FRAME_DELAY,
)
from rpi_usb_cloner.hardware.gpio import (
    PIN_A,
    PIN_B,
    PIN_C,
    PIN_D,
    PIN_L,
    PIN_R,
    PIN_U,
    is_pressed,
)
from rpi_usb_cloner.menu.model import get_screen_icon
from rpi_usb_cloner.ui.animated_icons import (
    AnimatedIconRef,
    is_animated_icon_path,
)
from rpi_usb_cloner.storage.clone import normalize_clone_mode
from rpi_usb_cloner.storage.devices import format_device_label
from rpi_usb_cloner.ui import display, renderer, transitions
from rpi_usb_cloner.ui.constants import (
    BUTTON_POLL_DELAY,
    DEFAULT_SCROLL_CYCLE_SECONDS,
    INITIAL_REPEAT_DELAY,
    REPEAT_INTERVAL,
)


@dataclass
class MenuItem:
    lines: List[str]
    line_widths: Optional[List[int]] = None


@dataclass
class Menu:
    items: List[MenuItem]
    selected_index: int = 0
    title: Optional[str] = None
    title_icon: Optional[str] = None
    screen_id: Optional[str] = None
    title_font: Optional[display.Font] = None
    footer: Optional[List[str]] = None
    footer_selected_index: Optional[int] = None
    footer_positions: Optional[List[int]] = None
    content_top: Optional[int] = None
    items_font: Optional[display.Font] = None
    enable_horizontal_scroll: bool = False
    scroll_speed: float = 30.0
    target_cycle_seconds: float = DEFAULT_SCROLL_CYCLE_SECONDS
    scroll_gap: int = 20
    scroll_start_time: Optional[float] = None
    scroll_start_delay: float = 0.0
    max_width: Optional[int] = None


def _get_text_height(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


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


def get_standard_content_top(
    title: str,
    *,
    title_font: Optional[display.Font] = None,
    title_icon: Optional[str | AnimatedIconRef] = None,
    title_icon_font: Optional[display.Font] = None,
    extra_gap: int = 2,
) -> int:
    # Use this helper for new pages to avoid title overlap.
    context = display.get_display_context()
    if not title:
        return context.top
    header_font = title_font or context.fonts.get("title", context.fontdisks)
    title_height = _get_text_height(context.draw, title, header_font)
    icon_height = 0
    if title_icon:
        icon_font = title_icon_font or display._get_lucide_font()
        icon_height = _get_line_height(icon_font)
    line_height = max(title_height, icon_height)
    return context.top + line_height + display.TITLE_PADDING + extra_gap


def _get_default_footer_positions(width: int, footer: List[str]) -> List[int]:
    spacing = width // (len(footer) + 1)
    return [(spacing * (index + 1)) - 10 for index in range(len(footer))]


def _render_header_lines_image(
    image: Image.Image,
    *,
    title: str,
    header_lines: List[str],
    title_font: Optional[display.Font] = None,
    title_icon: Optional[str | AnimatedIconRef] = None,
    items_font: Optional[display.Font] = None,
    content_top: Optional[int] = None,
) -> None:
    context = display.get_display_context()
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    current_y = context.top
    header_font = title_font or context.fonts.get("title", context.fontdisks)
    if title:
        layout = display.draw_title_with_icon(
            title,
            title_font=header_font,
            icon=title_icon,
            extra_gap=2,
            left_margin=context.x - 11,
            draw=draw,
            image=image,
        )
        current_y = layout.content_top
    if content_top is not None:
        current_y = max(current_y, content_top)
    items_font = items_font or context.fontdisks
    left_margin = context.x - 11
    available_width = max(0, context.width - left_margin)
    wrapped_lines = display._wrap_lines_to_width(
        header_lines,
        items_font,
        available_width,
    )
    line_height = _get_line_height(items_font)
    line_step = line_height + 2
    available_height = context.height - current_y - 2
    lines_per_page = max(1, available_height // line_step)
    total_pages = max(1, (len(wrapped_lines) + lines_per_page - 1) // lines_per_page)
    page_lines = wrapped_lines[:lines_per_page]
    for line in page_lines:
        draw.text((context.x - 11, current_y), line, font=items_font, fill=255)
        current_y += line_step
    if total_pages > 1:
        indicator = f"1/{total_pages}>"
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


def _render_menu_list_image(
    *,
    title: str,
    items: List[str],
    selected_index: int,
    scroll_offset: int,
    visible_rows: int,
    title_font: Optional[display.Font] = None,
    title_icon: Optional[str | AnimatedIconRef] = None,
    items_font: Optional[display.Font] = None,
    footer: Optional[List[str]] = None,
    footer_positions: Optional[List[int]] = None,
    content_top: Optional[int] = None,
    enable_horizontal_scroll: bool = False,
    scroll_start_time: Optional[float] = None,
    scroll_start_delay: float = 0.0,
    target_cycle_seconds: float = DEFAULT_SCROLL_CYCLE_SECONDS,
    scroll_gap: int = 20,
    screen_id: Optional[str] = None,
    header_lines: Optional[List[str]] = None,
) -> Image.Image:
    context = display.get_display_context()
    image = Image.new("1", (context.width, context.height), 0)
    if header_lines:
        _render_header_lines_image(
            image,
            title=title,
            header_lines=header_lines,
            title_font=title_font,
            title_icon=title_icon,
            items_font=items_font,
            content_top=content_top,
        )
    draw = ImageDraw.Draw(image)
    renderer._render_menu(
        draw=draw,
        image=image,
        title="" if header_lines else title,
        items=items,
        selected_index=selected_index,
        scroll_offset=scroll_offset,
        status_line=None,
        visible_rows=visible_rows,
        title_font=title_font,
        title_icon=title_icon,
        title_icon_font=None,
        items_font=items_font,
        status_font=None,
        footer=footer,
        footer_positions=footer_positions,
        footer_selected_index=None,
        footer_font=None,
        content_top=content_top,
        enable_horizontal_scroll=enable_horizontal_scroll,
        scroll_start_time=scroll_start_time,
        scroll_start_delay=scroll_start_delay,
        target_cycle_seconds=target_cycle_seconds,
        scroll_gap=scroll_gap,
        screen_id=screen_id,
        clear=not header_lines,
    )
    return image


def _get_transition_frame_count() -> int:
    context = display.get_display_context()
    default_frames = max(8, min(24, context.width // 4))
    setting_value = settings.get_setting(
        "transition_frame_count", DEFAULT_TRANSITION_FRAME_COUNT
    )
    try:
        frames = int(setting_value)
    except (TypeError, ValueError):
        return default_frames
    return max(1, min(24, frames))


def _get_transition_frame_delay() -> float:
    setting_value = settings.get_setting(
        "transition_frame_delay", DEFAULT_TRANSITION_FRAME_DELAY
    )
    try:
        delay = float(setting_value)
    except (TypeError, ValueError):
        return DEFAULT_TRANSITION_FRAME_DELAY
    return max(0.0, delay)


def render_menu(menu, draw, width, height, fonts, *, clear: bool = True):
    context = display.get_display_context()
    if clear:
        draw.rectangle((0, 0, width, height), outline=0, fill=0)
    current_y = context.top
    if menu.title:
        title_font = menu.title_font or fonts["title"]
        title_icon = menu.title_icon or get_screen_icon(menu.screen_id)
        layout = display.draw_title_with_icon(
            menu.title,
            title_font=title_font,
            icon=title_icon,
            extra_gap=1,
            left_margin=context.x - 11,
            draw=draw,
        )
        current_y = layout.content_top
    if menu.content_top is not None:
        current_y = max(current_y, menu.content_top)

    items_font = menu.items_font or fonts["items"]
    line_height = _get_line_height(items_font)
    row_height_per_line = line_height + 2

    left_margin = context.x - 11
    # Calculate selector width for consistent alignment
    selector = "> "
    selector_width = display._measure_text_width(draw, selector, items_font)
    if menu.max_width is not None:
        max_width = max(0, menu.max_width - selector_width)
    else:
        max_width = context.width - left_margin - selector_width - 1
    now = time.monotonic()
    for item_index, item in enumerate(menu.items):
        lines = item.lines
        row_height = max(len(lines), 1) * row_height_per_line
        row_top = current_y
        is_selected = item_index == menu.selected_index
        for line_index, line in enumerate(lines):
            text_color = 255
            x_offset = 0
            display_line = line
            if menu.screen_id == "images" and not is_selected:
                display_line = display._truncate_text(draw, line, items_font, max_width)
            if (
                is_selected
                and menu.enable_horizontal_scroll
                and menu.screen_id == "images"
                and menu.scroll_start_time is not None
            ):
                line_widths = item.line_widths or []
                line_width = (
                    line_widths[line_index] if line_index < len(line_widths) else None
                )
                if line_width is None:
                    line_width = display._measure_text_width(draw, line, items_font)
                if line_width > max_width:
                    elapsed = max(0.0, now - menu.scroll_start_time)
                    pause_duration = max(0.0, menu.scroll_start_delay)
                    cycle_width = line_width + menu.scroll_gap
                    target_cycle_seconds = max(0.0, menu.target_cycle_seconds)
                    travel_duration = max(0.0, target_cycle_seconds - pause_duration)
                    cycle_duration = pause_duration + travel_duration
                    if cycle_width > 0 and travel_duration > 0 and cycle_duration > 0:
                        scroll_speed = cycle_width / travel_duration
                        phase = elapsed % cycle_duration
                        if phase >= pause_duration:
                            travel_phase = phase - pause_duration
                            x_offset = -int((travel_phase * scroll_speed) % cycle_width)
            # Draw text with offset for alignment
            draw.text(
                (
                    left_margin + selector_width + x_offset,
                    row_top + 1 + line_index * row_height_per_line,
                ),
                display_line,
                font=items_font,
                fill=text_color,
            )
            # Draw selector for selected item (only on first line)
            if is_selected and line_index == 0:
                if menu.screen_id == "images":
                    # Mask entire selector column from left edge to prevent scrolling text from showing through
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
                draw.text(
                    (left_margin, row_top + 1),
                    selector,
                    font=items_font,
                    fill=text_color,
                )
        current_y += row_height

    if menu.footer:
        footer_font = fonts["footer"]
        footer_y = height - 15
        positions = menu.footer_positions
        if positions is None:
            positions = _get_default_footer_positions(width, menu.footer)
        for footer_index, label in enumerate(menu.footer):
            x_pos = positions[footer_index]
            text_bbox = draw.textbbox((x_pos, footer_y), label, font=footer_font)
            if (
                menu.footer_selected_index is not None
                and footer_index == menu.footer_selected_index
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


def wait_for_buttons_release(buttons, poll_delay=BUTTON_POLL_DELAY):
    while any(is_pressed(pin) for pin in buttons):
        time.sleep(poll_delay)


def select_list(
    title: str,
    items: List[str],
    *,
    screen_id: Optional[str] = None,
    title_icon: Optional[str | AnimatedIconRef] = None,
    title_font: Optional[display.Font] = None,
    footer: Optional[List[str]] = None,
    footer_positions: Optional[List[int]] = None,
    items_font: Optional[display.Font] = None,
    content_top: Optional[int] = None,
    selected_index: int = 0,
    header_lines: Optional[List[str]] = None,
    refresh_callback: Optional[Callable[[], Optional[List[str]]]] = None,
    refresh_interval: float = 0.25,
    scroll_mode: Optional[str] = None,
    enable_horizontal_scroll: bool = False,
    scroll_speed: float = 30.0,
    target_cycle_seconds: float = DEFAULT_SCROLL_CYCLE_SECONDS,
    scroll_gap: int = 20,
    scroll_refresh_interval: Optional[float] = None,
    scroll_start_delay: float = 0.0,
    transition_direction: Optional[str] = None,
) -> Optional[int]:
    context = display.get_display_context()
    if not items:
        return None
    items_font = items_font or context.fontdisks
    title_font = title_font or context.fonts.get("title", context.fontdisks)
    if title_icon is None and screen_id:
        title_icon = get_screen_icon(screen_id)
    content_top = (
        content_top
        if content_top is not None
        else get_standard_content_top(
            title, title_font=title_font, title_icon=title_icon
        )
    )
    visible_rows = renderer.calculate_visible_rows(
        title=title,
        title_icon=title_icon,
        title_font=title_font,
        items_font=items_font,
        footer=footer,
    )
    selected_index = max(0, min(selected_index, len(items) - 1))
    enable_scroll = enable_horizontal_scroll or (scroll_mode == "horizontal")
    scroll_offset = 0
    
    # Check if icon is animated and determine refresh interval
    has_animated_icon = isinstance(title_icon, AnimatedIconRef) or (
        isinstance(title_icon, str) and is_animated_icon_path(title_icon)
    )
    animation_refresh_interval = 0.05  # 20fps default for animations
    
    def clamp_scroll_offset(selected: int, offset: int) -> int:
        if selected < offset:
            offset = selected
        elif selected >= offset + visible_rows:
            offset = selected - visible_rows + 1
        max_scroll = max(len(items) - visible_rows, 0)
        return max(0, min(offset, max_scroll))

    def render(
        selected: int, offset: int, *, scroll_start_time: Optional[float] = None
    ) -> int:
        offset = clamp_scroll_offset(selected, offset)
        if header_lines:
            header_content_top = get_standard_content_top(
                title,
                title_font=title_font,
                title_icon=title_icon,
            )
            display.render_paginated_lines(
                title,
                header_lines,
                page_index=0,
                content_top=header_content_top,
                title_font=title_font,
                items_font=items_font,
                title_icon=title_icon,
            )
        renderer.render_menu_screen(
            title="" if header_lines else title,
            items=items,
            selected_index=selected,
            scroll_offset=offset,
            visible_rows=visible_rows,
            title_font=title_font,
            title_icon=title_icon,
            items_font=items_font,
            footer=footer,
            footer_positions=footer_positions,
            content_top=content_top,
            enable_horizontal_scroll=enable_scroll,
            scroll_start_time=scroll_start_time,
            scroll_start_delay=scroll_start_delay,
            target_cycle_seconds=target_cycle_seconds,
            scroll_gap=scroll_gap,
            screen_id=screen_id,
            clear=not header_lines,
        )
        return offset

    if scroll_refresh_interval is None:
        scroll_refresh_interval = settings.get_setting(
            "scroll_refresh_interval",
            DEFAULT_SCROLL_REFRESH_INTERVAL,
        )
    scroll_refresh_interval = max(0.02, float(scroll_refresh_interval))

    scroll_start_time = time.monotonic() if enable_scroll else None
    # Store original image for back transition when entering with forward transition
    original_image: Optional[Image.Image] = None
    if transition_direction:
        scroll_offset = clamp_scroll_offset(selected_index, scroll_offset)
        from_image = context.image.copy()
        # Store original for back transition on exit
        if transition_direction == "forward":
            original_image = from_image.copy()
        to_image = _render_menu_list_image(
            title=title,
            items=items,
            selected_index=selected_index,
            scroll_offset=scroll_offset,
            visible_rows=visible_rows,
            title_font=title_font,
            title_icon=title_icon,
            items_font=items_font,
            footer=footer,
            footer_positions=footer_positions,
            content_top=content_top,
            enable_horizontal_scroll=enable_scroll,
            scroll_start_time=scroll_start_time,
            scroll_start_delay=scroll_start_delay,
            target_cycle_seconds=target_cycle_seconds,
            scroll_gap=scroll_gap,
            screen_id=screen_id,
            header_lines=header_lines,
        )
        transitions.render_slide_transition(
            from_image=from_image,
            to_image=to_image,
            direction=transition_direction,
            frame_count=_get_transition_frame_count(),
            frame_delay=_get_transition_frame_delay(),
        )
        with display._display_lock:
            context = display.get_display_context()
            context.image.paste(to_image)
            context.disp.display(context.image)
            display.mark_display_dirty()
    else:
        scroll_offset = render(
            selected_index, scroll_offset, scroll_start_time=scroll_start_time
        )
    last_rendered_index = selected_index
    last_refresh_time = time.monotonic()
    last_scroll_render = time.monotonic()
    last_animation_render = time.monotonic()
    wait_for_buttons_release([PIN_U, PIN_D, PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
    prev_states = {
        "U": is_pressed(PIN_U),
        "D": is_pressed(PIN_D),
        "L": is_pressed(PIN_L),
        "R": is_pressed(PIN_R),
        "A": is_pressed(PIN_A),
        "B": is_pressed(PIN_B),
        "C": is_pressed(PIN_C),
    }
    last_press_time = dict.fromkeys(prev_states, 0.0)
    last_repeat_time = dict.fromkeys(prev_states, 0.0)
    while True:
        now = time.monotonic()
        action_taken = False
        refresh_needed = False
        if (
            enable_scroll
            and screen_id == "images"
            and now - last_scroll_render >= scroll_refresh_interval
        ):
            refresh_needed = True
            last_scroll_render = now
        # Animation refresh for animated icons
        if (
            has_animated_icon
            and now - last_animation_render >= animation_refresh_interval
        ):
            refresh_needed = True
            last_animation_render = now
        if refresh_callback and now - last_refresh_time >= refresh_interval:
            new_items = refresh_callback()
            last_refresh_time = now
            if new_items is not None:
                items = new_items
                if not items:
                    return None
                if selected_index >= len(items):
                    selected_index = len(items) - 1
                scroll_start_time = time.monotonic() if enable_scroll else None
                scroll_offset = render(
                    selected_index,
                    scroll_offset,
                    scroll_start_time=scroll_start_time,
                )
                last_rendered_index = selected_index
        current_u = is_pressed(PIN_U)
        if not prev_states["U"] and current_u:
            action_taken = True
            next_index = max(0, selected_index - 1)
            if next_index != selected_index:
                selected_index = next_index
                scroll_start_time = time.monotonic() if enable_scroll else None
            last_press_time["U"] = now
            last_repeat_time["U"] = now
        elif current_u and now - last_press_time["U"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["U"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = max(0, selected_index - 1)
                if next_index != selected_index:
                    selected_index = next_index
                    scroll_start_time = time.monotonic() if enable_scroll else None
                last_repeat_time["U"] = now
        current_d = is_pressed(PIN_D)
        if not prev_states["D"] and current_d:
            action_taken = True
            next_index = min(len(items) - 1, selected_index + 1)
            if next_index != selected_index:
                selected_index = next_index
                scroll_start_time = time.monotonic() if enable_scroll else None
            last_press_time["D"] = now
            last_repeat_time["D"] = now
        elif current_d and now - last_press_time["D"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["D"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = min(len(items) - 1, selected_index + 1)
                if next_index != selected_index:
                    selected_index = next_index
                    scroll_start_time = time.monotonic() if enable_scroll else None
                last_repeat_time["D"] = now
        current_l = is_pressed(PIN_L)
        if not prev_states["L"] and current_l:
            action_taken = True
            next_index = max(0, selected_index - visible_rows)
            if next_index != selected_index:
                selected_index = next_index
                scroll_start_time = time.monotonic() if enable_scroll else None
            last_press_time["L"] = now
            last_repeat_time["L"] = now
        elif current_l and now - last_press_time["L"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["L"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = max(0, selected_index - visible_rows)
                if next_index != selected_index:
                    selected_index = next_index
                    scroll_start_time = time.monotonic() if enable_scroll else None
                last_repeat_time["L"] = now
        current_r = is_pressed(PIN_R)
        if not prev_states["R"] and current_r:
            action_taken = True
            next_index = min(len(items) - 1, selected_index + visible_rows)
            if next_index != selected_index:
                selected_index = next_index
                scroll_start_time = time.monotonic() if enable_scroll else None
            last_press_time["R"] = now
            last_repeat_time["R"] = now
        elif current_r and now - last_press_time["R"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["R"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = min(len(items) - 1, selected_index + visible_rows)
                if next_index != selected_index:
                    selected_index = next_index
                    scroll_start_time = time.monotonic() if enable_scroll else None
                last_repeat_time["R"] = now
        current_a = is_pressed(PIN_A)
        if not prev_states["A"] and current_a:
            # Play back transition if we entered with forward transition
            if original_image is not None:
                current_image = context.image.copy()
                transitions.render_slide_transition(
                    from_image=current_image,
                    to_image=original_image,
                    direction="back",
                    frame_count=_get_transition_frame_count(),
                    frame_delay=_get_transition_frame_delay(),
                )
                with display._display_lock:
                    context = display.get_display_context()
                    context.image.paste(original_image)
                    context.disp.display(context.image)
                    display.mark_display_dirty()
            return None
        current_b = is_pressed(PIN_B)
        if not prev_states["B"] and current_b:
            return selected_index
        current_c = is_pressed(PIN_C)
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        prev_states["C"] = current_c
        if (selected_index != last_rendered_index and action_taken) or refresh_needed:
            scroll_offset = render(
                selected_index,
                scroll_offset,
                scroll_start_time=scroll_start_time,
            )
            last_rendered_index = selected_index
        time.sleep(BUTTON_POLL_DELAY)


def render_menu_list(
    title: str,
    items: List[str],
    *,
    screen_id: Optional[str] = None,
    title_icon: Optional[str | AnimatedIconRef] = None,
    title_font: Optional[display.Font] = None,
    footer: Optional[List[str]] = None,
    footer_positions: Optional[List[int]] = None,
    items_font: Optional[display.Font] = None,
    content_top: Optional[int] = None,
    selected_index: int = 0,
    header_lines: Optional[List[str]] = None,
    refresh_callback: Optional[Callable[[], Optional[List[str]]]] = None,
    refresh_interval: float = 0.25,
    transition_direction: Optional[str] = None,
) -> Optional[int]:
    context = display.get_display_context()
    title_font = title_font or context.fonts.get("title", context.fontdisks)
    if title_icon is None and screen_id:
        title_icon = get_screen_icon(screen_id)
    if content_top is None:
        content_top = get_standard_content_top(
            title, title_font=title_font, title_icon=title_icon
        )
    if footer and footer_positions is None:
        footer_positions = _get_default_footer_positions(context.width, footer)
    return select_list(
        title,
        items,
        screen_id=screen_id,
        title_icon=title_icon,
        title_font=title_font,
        footer=footer,
        footer_positions=footer_positions,
        items_font=items_font,
        content_top=content_top,
        selected_index=selected_index,
        header_lines=header_lines,
        refresh_callback=refresh_callback,
        refresh_interval=refresh_interval,
        transition_direction=transition_direction,
    )


def select_menu_screen_list(
    title: str,
    items: List[str],
    *,
    screen_id: Optional[str] = None,
    status_line: Optional[str] = None,
    title_icon: Optional[str | AnimatedIconRef] = None,
    title_font: Optional[display.Font] = None,
    items_font: Optional[display.Font] = None,
    selected_index: int = 0,
) -> Optional[int]:
    context = display.get_display_context()
    if not items:
        return None
    if title_icon is None and screen_id:
        title_icon = get_screen_icon(screen_id)
    items_font = items_font or context.fontdisks
    title_font = title_font or context.fonts.get("title", context.fontdisks)
    visible_rows = renderer.calculate_visible_rows(
        title=title,
        title_icon=title_icon,
        status_line=status_line,
        title_font=title_font,
        items_font=items_font,
    )
    selected_index = max(0, min(selected_index, len(items) - 1))
    scroll_offset = 0

    def clamp_scroll_offset(selected: int, offset: int) -> int:
        if selected < offset:
            offset = selected
        elif selected >= offset + visible_rows:
            offset = selected - visible_rows + 1
        max_scroll = max(len(items) - visible_rows, 0)
        return max(0, min(offset, max_scroll))

    def render(selected: int, offset: int) -> int:
        offset = clamp_scroll_offset(selected, offset)
        renderer.render_menu_screen(
            title=title,
            items=items,
            selected_index=selected,
            scroll_offset=offset,
            status_line=status_line,
            visible_rows=visible_rows,
            title_font=title_font,
            title_icon=title_icon,
            items_font=items_font,
        )
        return offset

    scroll_offset = render(selected_index, scroll_offset)
    last_rendered_index = selected_index
    wait_for_buttons_release([PIN_U, PIN_D, PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
    prev_states = {
        "U": is_pressed(PIN_U),
        "D": is_pressed(PIN_D),
        "L": is_pressed(PIN_L),
        "R": is_pressed(PIN_R),
        "A": is_pressed(PIN_A),
        "B": is_pressed(PIN_B),
        "C": is_pressed(PIN_C),
    }
    last_press_time = dict.fromkeys(prev_states, 0.0)
    last_repeat_time = dict.fromkeys(prev_states, 0.0)
    while True:
        now = time.monotonic()
        action_taken = False
        current_u = is_pressed(PIN_U)
        if not prev_states["U"] and current_u:
            last_press_time["U"] = now
            last_repeat_time["U"] = now
        if prev_states["U"] and not current_u:
            action_taken = True
            next_index = max(0, selected_index - 1)
            if next_index != selected_index:
                selected_index = next_index
            last_press_time["U"] = now
            last_repeat_time["U"] = now
        elif current_u and now - last_press_time["U"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["U"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = max(0, selected_index - 1)
                if next_index != selected_index:
                    selected_index = next_index
                last_repeat_time["U"] = now
        current_d = is_pressed(PIN_D)
        if not prev_states["D"] and current_d:
            last_press_time["D"] = now
            last_repeat_time["D"] = now
        if prev_states["D"] and not current_d:
            action_taken = True
            next_index = min(len(items) - 1, selected_index + 1)
            if next_index != selected_index:
                selected_index = next_index
            last_press_time["D"] = now
            last_repeat_time["D"] = now
        elif current_d and now - last_press_time["D"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["D"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = min(len(items) - 1, selected_index + 1)
                if next_index != selected_index:
                    selected_index = next_index
                last_repeat_time["D"] = now
        current_l = is_pressed(PIN_L)
        if not prev_states["L"] and current_l:
            last_press_time["L"] = now
            last_repeat_time["L"] = now
        if prev_states["L"] and not current_l:
            action_taken = True
            next_index = max(0, selected_index - visible_rows)
            if next_index != selected_index:
                selected_index = next_index
            last_press_time["L"] = now
            last_repeat_time["L"] = now
        elif current_l and now - last_press_time["L"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["L"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = max(0, selected_index - visible_rows)
                if next_index != selected_index:
                    selected_index = next_index
                last_repeat_time["L"] = now
        current_r = is_pressed(PIN_R)
        if not prev_states["R"] and current_r:
            last_press_time["R"] = now
            last_repeat_time["R"] = now
        if prev_states["R"] and not current_r:
            action_taken = True
            next_index = min(len(items) - 1, selected_index + visible_rows)
            if next_index != selected_index:
                selected_index = next_index
            last_press_time["R"] = now
            last_repeat_time["R"] = now
        elif current_r and now - last_press_time["R"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["R"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = min(len(items) - 1, selected_index + visible_rows)
                if next_index != selected_index:
                    selected_index = next_index
                last_repeat_time["R"] = now
        current_a = is_pressed(PIN_A)
        if prev_states["A"] and not current_a:
            return None
        current_b = is_pressed(PIN_B)
        if prev_states["B"] and not current_b:
            return selected_index
        current_c = is_pressed(PIN_C)
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        prev_states["C"] = current_c
        if selected_index != last_rendered_index and action_taken:
            scroll_offset = render(selected_index, scroll_offset)
            last_rendered_index = selected_index
        time.sleep(BUTTON_POLL_DELAY)


def select_usb_drive(
    title: str,
    devices_list: List[dict],
    *,
    title_icon: Optional[str | AnimatedIconRef] = None,
    footer: Optional[List[str]] = None,
    selected_name: Optional[str] = None,
    header_lines: Optional[List[str]] = None,
    transition_direction: Optional[str] = None,
) -> Optional[int]:
    if not devices_list:
        return None
    items = [format_device_label(device) for device in devices_list]
    selected_index = 0
    if selected_name:
        for index, device in enumerate(devices_list):
            if device.get("name") == selected_name:
                selected_index = index
                break
    return select_list(
        title,
        items,
        title_icon=title_icon,
        footer=footer,
        selected_index=selected_index,
        header_lines=header_lines,
        transition_direction=transition_direction,
    )


def select_clone_mode(current_mode=None, *, transition_direction: Optional[str] = None):
    modes = ["smart", "exact", "verify"]
    selected_mode = normalize_clone_mode(current_mode or "smart")
    if selected_mode not in modes:
        selected_mode = "smart"
    selected_index = render_menu_list(
        "CLONE MODE",
        [mode.upper() for mode in modes],
        selected_index=modes.index(selected_mode),
        screen_id="clone",
        transition_direction=transition_direction,
    )
    if selected_index is None:
        return None
    return modes[selected_index]


def select_erase_mode(*, status_line: Optional[str] = None):
    modes = ["quick", "zero", "discard", "secure"]
    selected_index = select_menu_screen_list(
        "ERASE MODE",
        [mode.upper() for mode in modes],
        screen_id="drives",
        status_line=status_line,
    )
    if selected_index is None:
        return None
    return modes[selected_index]


def select_filesystem_type(device_size: int, *, status_line: Optional[str] = None):
    """Select filesystem type with size-based default.

    Args:
        device_size: Device size in bytes

    Returns:
        Selected filesystem type or None if cancelled
    """
    filesystems = ["ext4", "vfat", "exfat", "ntfs"]

    # Determine default based on size
    # FAT32 for ≤32 GB, exFAT for ≥64 GB
    gb_32 = 32 * 1024 * 1024 * 1024
    gb_64 = 64 * 1024 * 1024 * 1024

    if device_size <= gb_32:
        default_fs = "vfat"
    elif device_size >= gb_64:
        default_fs = "exfat"
    else:
        # Between 32-64GB, default to exFAT
        default_fs = "exfat"

    default_index = filesystems.index(default_fs) if default_fs in filesystems else 0

    selected_index = select_menu_screen_list(
        "FORMAT DRIVE",
        [fs.upper() for fs in filesystems],
        screen_id="drives",
        selected_index=default_index,
        status_line=status_line,
    )
    if selected_index is None:
        return None
    return filesystems[selected_index]


def select_format_type(*, status_line: Optional[str] = None):
    """Select format type (quick or full).

    Returns:
        Selected format type or None if cancelled
    """
    types = ["quick", "full"]
    selected_index = select_menu_screen_list(
        "FORMAT TYPE",
        [t.upper() for t in types],
        screen_id="drives",
        status_line=status_line,
    )
    if selected_index is None:
        return None
    return types[selected_index]
