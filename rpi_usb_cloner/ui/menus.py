import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from PIL import ImageFont

from rpi_usb_cloner.config import settings
from rpi_usb_cloner.hardware.gpio import (
    PIN_A,
    PIN_B,
    PIN_C,
    PIN_D,
    PIN_L,
    PIN_R,
    PIN_U,
    is_pressed,
    read_button,
)
from rpi_usb_cloner.menu.model import get_screen_icon
from rpi_usb_cloner.storage.clone import normalize_clone_mode
from rpi_usb_cloner.storage.devices import format_device_label
from rpi_usb_cloner.ui import display

INITIAL_REPEAT_DELAY = 0.3
REPEAT_INTERVAL = 0.08
BUTTON_POLL_DELAY = 0.01
DEFAULT_SCROLL_CYCLE_SECONDS = 6.0
DEFAULT_SCROLL_REFRESH_INTERVAL = 0.04


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
    title_font: Optional[ImageFont.ImageFont] = None
    footer: Optional[List[str]] = None
    footer_selected_index: Optional[int] = None
    footer_positions: Optional[List[int]] = None
    content_top: Optional[int] = None
    items_font: Optional[ImageFont.ImageFont] = None
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
    title_font: Optional[ImageFont.ImageFont] = None,
    title_icon: Optional[str] = None,
    title_icon_font: Optional[ImageFont.ImageFont] = None,
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
    max_width = menu.max_width if menu.max_width is not None else (context.width - left_margin - 1)
    now = time.monotonic()
    for item_index, item in enumerate(menu.items):
        lines = item.lines
        row_height = max(len(lines), 1) * row_height_per_line
        row_top = current_y
        is_selected = item_index == menu.selected_index
        if is_selected:
            draw.rectangle((0, row_top, width, row_top + row_height - 1), outline=0, fill=1)
        for line_index, line in enumerate(lines):
            text_color = 0 if is_selected else 255
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
                line_width = line_widths[line_index] if line_index < len(line_widths) else None
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
            draw.text(
                (left_margin + x_offset, row_top + 1 + line_index * row_height_per_line),
                display_line,
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
            if menu.footer_selected_index is not None and footer_index == menu.footer_selected_index:
                draw.rectangle(
                    (text_bbox[0] - 3, text_bbox[1] - 2, text_bbox[2] + 3, text_bbox[3] + 2),
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
    title_icon: Optional[str] = None,
    title_font: Optional[ImageFont.ImageFont] = None,
    footer: Optional[List[str]] = None,
    footer_positions: Optional[List[int]] = None,
    items_font: Optional[ImageFont.ImageFont] = None,
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
) -> Optional[int]:
    context = display.get_display_context()
    if not items:
        return None
    items_font = items_font or context.fontdisks
    title_font = title_font or context.fonts.get("title", context.fontdisks)
    content_top = (
        content_top
        if content_top is not None
        else get_standard_content_top(title, title_font=title_font, title_icon=title_icon)
    )
    footer_height = 15 if footer else 0
    line_height = _get_line_height(items_font)
    row_height = line_height + 2
    available_height = context.height - content_top - footer_height
    items_per_page = max(1, available_height // row_height)
    selected_index = max(0, min(selected_index, len(items) - 1))
    enable_scroll = enable_horizontal_scroll or (scroll_mode == "horizontal")
    left_margin = context.x - 11
    max_width = context.width - left_margin - 1

    def render(selected: int, *, scroll_start_time: Optional[float] = None) -> None:
        offset = (selected // items_per_page) * items_per_page
        page_items = items[offset : offset + items_per_page]
        menu_items = []
        for line in page_items:
            line_width = display._measure_text_width(context.draw, line, items_font)
            menu_items.append(MenuItem([line], [int(line_width)]))
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
        menu = Menu(
            items=menu_items,
            selected_index=selected - offset,
            title=None if header_lines else title,
            title_icon=title_icon,
            screen_id=screen_id,
            title_font=title_font,
            content_top=content_top,
            footer=footer,
            footer_positions=footer_positions,
            items_font=items_font,
            enable_horizontal_scroll=enable_scroll,
            scroll_speed=scroll_speed,
            target_cycle_seconds=target_cycle_seconds,
            scroll_gap=scroll_gap,
            scroll_start_time=scroll_start_time,
            scroll_start_delay=scroll_start_delay,
            max_width=max_width,
        )
        render_menu(
            menu,
            context.draw,
            context.width,
            context.height,
            context.fonts,
            clear=not header_lines,
        )
        context.disp.display(context.image)

    if scroll_refresh_interval is None:
        scroll_refresh_interval = settings.get_setting(
            "scroll_refresh_interval",
            DEFAULT_SCROLL_REFRESH_INTERVAL,
        )
    scroll_refresh_interval = max(0.02, float(scroll_refresh_interval))

    scroll_start_time = time.monotonic() if enable_scroll else None
    render(selected_index, scroll_start_time=scroll_start_time)
    last_rendered_index = selected_index
    last_refresh_time = time.monotonic()
    last_scroll_render = time.monotonic()
    wait_for_buttons_release([PIN_U, PIN_D, PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
    prev_states = {
        "U": read_button(PIN_U),
        "D": read_button(PIN_D),
        "L": read_button(PIN_L),
        "R": read_button(PIN_R),
        "A": read_button(PIN_A),
        "B": read_button(PIN_B),
        "C": read_button(PIN_C),
    }
    last_press_time = {key: 0.0 for key in prev_states}
    last_repeat_time = {key: 0.0 for key in prev_states}
    while True:
        now = time.monotonic()
        action_taken = False
        refresh_needed = False
        if enable_scroll and screen_id == "images":
            if now - last_scroll_render >= scroll_refresh_interval:
                refresh_needed = True
                last_scroll_render = now
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
                render(selected_index, scroll_start_time=scroll_start_time)
                last_rendered_index = selected_index
        current_u = read_button(PIN_U)
        if prev_states["U"] and not current_u:
            action_taken = True
            next_index = max(0, selected_index - 1)
            if next_index != selected_index:
                selected_index = next_index
                scroll_start_time = time.monotonic() if enable_scroll else None
            last_press_time["U"] = now
            last_repeat_time["U"] = now
        elif not current_u and now - last_press_time["U"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["U"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = max(0, selected_index - 1)
                if next_index != selected_index:
                    selected_index = next_index
                    scroll_start_time = time.monotonic() if enable_scroll else None
                last_repeat_time["U"] = now
        current_d = read_button(PIN_D)
        if prev_states["D"] and not current_d:
            action_taken = True
            next_index = min(len(items) - 1, selected_index + 1)
            if next_index != selected_index:
                selected_index = next_index
                scroll_start_time = time.monotonic() if enable_scroll else None
            last_press_time["D"] = now
            last_repeat_time["D"] = now
        elif not current_d and now - last_press_time["D"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["D"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = min(len(items) - 1, selected_index + 1)
                if next_index != selected_index:
                    selected_index = next_index
                    scroll_start_time = time.monotonic() if enable_scroll else None
                last_repeat_time["D"] = now
        current_l = read_button(PIN_L)
        if prev_states["L"] and not current_l:
            action_taken = True
            next_index = max(0, selected_index - items_per_page)
            if next_index != selected_index:
                selected_index = next_index
                scroll_start_time = time.monotonic() if enable_scroll else None
            last_press_time["L"] = now
            last_repeat_time["L"] = now
        elif not current_l and now - last_press_time["L"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["L"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = max(0, selected_index - items_per_page)
                if next_index != selected_index:
                    selected_index = next_index
                    scroll_start_time = time.monotonic() if enable_scroll else None
                last_repeat_time["L"] = now
        current_r = read_button(PIN_R)
        if prev_states["R"] and not current_r:
            action_taken = True
            next_index = min(len(items) - 1, selected_index + items_per_page)
            if next_index != selected_index:
                selected_index = next_index
                scroll_start_time = time.monotonic() if enable_scroll else None
            last_press_time["R"] = now
            last_repeat_time["R"] = now
        elif not current_r and now - last_press_time["R"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["R"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = min(len(items) - 1, selected_index + items_per_page)
                if next_index != selected_index:
                    selected_index = next_index
                    scroll_start_time = time.monotonic() if enable_scroll else None
                last_repeat_time["R"] = now
        current_a = read_button(PIN_A)
        if prev_states["A"] and not current_a:
            return None
        current_b = read_button(PIN_B)
        if prev_states["B"] and not current_b:
            return selected_index
        current_c = read_button(PIN_C)
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        prev_states["C"] = current_c
        if (selected_index != last_rendered_index and action_taken) or refresh_needed:
            render(selected_index, scroll_start_time=scroll_start_time)
            last_rendered_index = selected_index
        time.sleep(BUTTON_POLL_DELAY)


def render_menu_list(
    title: str,
    items: List[str],
    *,
    screen_id: Optional[str] = None,
    title_icon: Optional[str] = None,
    title_font: Optional[ImageFont.ImageFont] = None,
    footer: Optional[List[str]] = None,
    footer_positions: Optional[List[int]] = None,
    items_font: Optional[ImageFont.ImageFont] = None,
    content_top: Optional[int] = None,
    selected_index: int = 0,
    header_lines: Optional[List[str]] = None,
    refresh_callback: Optional[Callable[[], Optional[List[str]]]] = None,
    refresh_interval: float = 0.25,
) -> Optional[int]:
    context = display.get_display_context()
    title_font = title_font or context.fonts.get("title", context.fontdisks)
    if title_icon is None and screen_id:
        title_icon = get_screen_icon(screen_id)
    if content_top is None:
        content_top = get_standard_content_top(title, title_font=title_font, title_icon=title_icon)
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
    )


def select_usb_drive(
    title: str,
    devices_list: List[dict],
    *,
    title_icon: Optional[str] = None,
    footer: Optional[List[str]] = None,
    selected_name: Optional[str] = None,
    header_lines: Optional[List[str]] = None,
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
    )


def select_clone_mode(current_mode=None):
    modes = ["smart", "exact", "verify"]
    selected_mode = normalize_clone_mode(current_mode or "smart")
    if selected_mode not in modes:
        selected_mode = "smart"
    selected_index = render_menu_list(
        "CLONE MODE",
        [mode.upper() for mode in modes],
        selected_index=modes.index(selected_mode),
    )
    if selected_index is None:
        return None
    return modes[selected_index]


def select_erase_mode():
    modes = ["quick", "zero", "discard", "secure"]
    selected_index = render_menu_list(
        "ERASE MODE",
        [mode.upper() for mode in modes],
        title_font=display.get_display_context().fontcopy,
        title_icon=chr(57741),
    )
    if selected_index is None:
        return None
    return modes[selected_index]
