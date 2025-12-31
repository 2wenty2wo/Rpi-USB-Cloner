import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from PIL import ImageFont

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
from rpi_usb_cloner.storage.clone import normalize_clone_mode
from rpi_usb_cloner.ui import display

INITIAL_REPEAT_DELAY = 0.3
REPEAT_INTERVAL = 0.08
BUTTON_POLL_DELAY = 0.01


@dataclass
class MenuItem:
    lines: List[str]


@dataclass
class Menu:
    items: List[MenuItem]
    selected_index: int = 0
    title: Optional[str] = None
    title_font: Optional[ImageFont.ImageFont] = None
    footer: Optional[List[str]] = None
    footer_selected_index: Optional[int] = None
    footer_positions: Optional[List[int]] = None
    content_top: Optional[int] = None
    items_font: Optional[ImageFont.ImageFont] = None


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
    extra_gap: int = 2,
) -> int:
    # Use this helper for new pages to avoid title overlap.
    context = display.get_display_context()
    if not title:
        return context.top
    header_font = title_font or context.fonts.get("title", context.fontdisks)
    title_height = _get_text_height(context.draw, title, header_font)
    return context.top + title_height + display.TITLE_PADDING + extra_gap


def render_menu(menu, draw, width, height, fonts, *, clear: bool = True):
    context = display.get_display_context()
    if clear:
        draw.rectangle((0, 0, width, height), outline=0, fill=0)
    current_y = context.top
    if menu.title:
        title_font = menu.title_font or fonts["title"]
        draw.text((context.x - 11, current_y), menu.title, font=title_font, fill=255)
        current_y = get_standard_content_top(menu.title, title_font=title_font)
    if menu.content_top is not None:
        current_y = max(current_y, menu.content_top)

    items_font = menu.items_font or fonts["items"]
    line_height = _get_line_height(items_font)
    row_height_per_line = line_height + 2

    for item_index, item in enumerate(menu.items):
        lines = item.lines
        row_height = max(len(lines), 1) * row_height_per_line
        row_top = current_y
        is_selected = item_index == menu.selected_index
        if is_selected:
            draw.rectangle((0, row_top, width, row_top + row_height - 1), outline=0, fill=1)
        for line_index, line in enumerate(lines):
            text_color = 0 if is_selected else 255
            draw.text(
                (context.x - 11, row_top + 1 + line_index * row_height_per_line),
                line,
                font=items_font,
                fill=text_color,
            )
        current_y += row_height

    if menu.footer:
        footer_font = fonts["footer"]
        footer_y = height - 15
        positions = menu.footer_positions
        if positions is None:
            spacing = width // (len(menu.footer) + 1)
            positions = [(spacing * (index + 1)) - 10 for index in range(len(menu.footer))]
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
    footer: Optional[List[str]] = None,
    footer_positions: Optional[List[int]] = None,
    items_font: Optional[ImageFont.ImageFont] = None,
    content_top: Optional[int] = None,
    header_lines: Optional[List[str]] = None,
    refresh_callback: Optional[Callable[[], Optional[List[str]]]] = None,
    refresh_interval: float = 0.25,
) -> Optional[int]:
    context = display.get_display_context()
    if not items:
        return None
    items_font = items_font or context.fontdisks
    title_font = context.fonts.get("title", context.fontdisks)
    content_top = (
        content_top
        if content_top is not None
        else get_standard_content_top(title, title_font=title_font)
    )
    footer_height = 15 if footer else 0
    line_height = _get_line_height(items_font)
    row_height = line_height + 2
    available_height = context.height - content_top - footer_height
    items_per_page = max(1, available_height // row_height)
    selected_index = 0

    def render(selected: int) -> None:
        offset = (selected // items_per_page) * items_per_page
        page_items = items[offset : offset + items_per_page]
        menu_items = [MenuItem([line]) for line in page_items]
        if header_lines:
            header_content_top = get_standard_content_top(title, title_font=title_font)
            display.render_paginated_lines(
                title,
                header_lines,
                page_index=0,
                content_top=header_content_top,
                title_font=title_font,
                items_font=items_font,
            )
        menu = Menu(
            items=menu_items,
            selected_index=selected - offset,
            title=None if header_lines else title,
            title_font=title_font,
            content_top=content_top,
            footer=footer,
            footer_positions=footer_positions,
            items_font=items_font,
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

    render(selected_index)
    last_rendered_index = selected_index
    last_refresh_time = time.monotonic()
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
        if refresh_callback and now - last_refresh_time >= refresh_interval:
            new_items = refresh_callback()
            last_refresh_time = now
            if new_items is not None:
                items = new_items
                if not items:
                    return None
                if selected_index >= len(items):
                    selected_index = len(items) - 1
                render(selected_index)
                last_rendered_index = selected_index
        current_u = read_button(PIN_U)
        if prev_states["U"] and not current_u:
            action_taken = True
            next_index = max(0, selected_index - 1)
            if next_index != selected_index:
                selected_index = next_index
            last_press_time["U"] = now
            last_repeat_time["U"] = now
        elif not current_u and now - last_press_time["U"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["U"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = max(0, selected_index - 1)
                if next_index != selected_index:
                    selected_index = next_index
                last_repeat_time["U"] = now
        current_d = read_button(PIN_D)
        if prev_states["D"] and not current_d:
            action_taken = True
            next_index = min(len(items) - 1, selected_index + 1)
            if next_index != selected_index:
                selected_index = next_index
            last_press_time["D"] = now
            last_repeat_time["D"] = now
        elif not current_d and now - last_press_time["D"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["D"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = min(len(items) - 1, selected_index + 1)
                if next_index != selected_index:
                    selected_index = next_index
                last_repeat_time["D"] = now
        current_l = read_button(PIN_L)
        if prev_states["L"] and not current_l:
            action_taken = True
            next_index = max(0, selected_index - items_per_page)
            if next_index != selected_index:
                selected_index = next_index
            last_press_time["L"] = now
            last_repeat_time["L"] = now
        elif not current_l and now - last_press_time["L"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["L"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = max(0, selected_index - items_per_page)
                if next_index != selected_index:
                    selected_index = next_index
                last_repeat_time["L"] = now
        current_r = read_button(PIN_R)
        if prev_states["R"] and not current_r:
            action_taken = True
            next_index = min(len(items) - 1, selected_index + items_per_page)
            if next_index != selected_index:
                selected_index = next_index
            last_press_time["R"] = now
            last_repeat_time["R"] = now
        elif not current_r and now - last_press_time["R"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["R"] >= REPEAT_INTERVAL:
                action_taken = True
                next_index = min(len(items) - 1, selected_index + items_per_page)
                if next_index != selected_index:
                    selected_index = next_index
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
            render(selected_index)
            last_rendered_index = selected_index
        time.sleep(BUTTON_POLL_DELAY)


def select_clone_mode(current_mode=None):
    context = display.get_display_context()
    modes = ["smart", "exact", "verify"]
    selected_mode = normalize_clone_mode(current_mode or "smart")
    if selected_mode not in modes:
        selected_mode = "smart"
    selected_index = modes.index(selected_mode)
    menu_items = [MenuItem([mode.upper()]) for mode in modes]
    menu = Menu(
        items=menu_items,
        selected_index=selected_index,
        title="CLONE MODE",
        footer=["BACK", "OK"],
        footer_positions=[context.x + 12, context.x + 63],
    )
    render_menu(menu, context.draw, context.width, context.height, context.fonts)
    context.disp.display(context.image)
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
        current_U = read_button(PIN_U)
        if prev_states["U"] and not current_U:
            selected_index = max(0, selected_index - 1)
            last_press_time["U"] = now
            last_repeat_time["U"] = now
        elif not current_U and now - last_press_time["U"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["U"] >= REPEAT_INTERVAL:
                selected_index = max(0, selected_index - 1)
                last_repeat_time["U"] = now
        current_D = read_button(PIN_D)
        if prev_states["D"] and not current_D:
            selected_index = min(len(modes) - 1, selected_index + 1)
            last_press_time["D"] = now
            last_repeat_time["D"] = now
        elif not current_D and now - last_press_time["D"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["D"] >= REPEAT_INTERVAL:
                selected_index = min(len(modes) - 1, selected_index + 1)
                last_repeat_time["D"] = now
        current_L = read_button(PIN_L)
        if prev_states["L"] and not current_L:
            selected_index = max(0, selected_index - 1)
            last_press_time["L"] = now
            last_repeat_time["L"] = now
        elif not current_L and now - last_press_time["L"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["L"] >= REPEAT_INTERVAL:
                selected_index = max(0, selected_index - 1)
                last_repeat_time["L"] = now
        current_R = read_button(PIN_R)
        if prev_states["R"] and not current_R:
            selected_index = min(len(modes) - 1, selected_index + 1)
            last_press_time["R"] = now
            last_repeat_time["R"] = now
        elif not current_R and now - last_press_time["R"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["R"] >= REPEAT_INTERVAL:
                selected_index = min(len(modes) - 1, selected_index + 1)
                last_repeat_time["R"] = now
        current_A = read_button(PIN_A)
        if prev_states["A"] and not current_A:
            return None
        current_B = read_button(PIN_B)
        if prev_states["B"] and not current_B:
            return modes[selected_index]
        current_C = read_button(PIN_C)
        prev_states["U"] = current_U
        prev_states["D"] = current_D
        prev_states["L"] = current_L
        prev_states["R"] = current_R
        prev_states["A"] = current_A
        prev_states["B"] = current_B
        prev_states["C"] = current_C
        menu.selected_index = selected_index
        render_menu(menu, context.draw, context.width, context.height, context.fonts)
        context.disp.display(context.image)
        time.sleep(BUTTON_POLL_DELAY)


def select_erase_mode():
    context = display.get_display_context()
    modes = ["quick", "zero", "discard", "secure"]
    selected_index = 0
    menu_items = [MenuItem([mode.upper()]) for mode in modes]
    title_height = _get_text_height(context.draw, "ERASE MODE", context.fontcopy)
    menu = Menu(
        items=menu_items,
        selected_index=selected_index,
        title="ERASE MODE",
        title_font=context.fontcopy,
        content_top=context.top + title_height + display.TITLE_PADDING,
    )
    render_menu(menu, context.draw, context.width, context.height, context.fonts)
    context.disp.display(context.image)
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
        current_U = read_button(PIN_U)
        if prev_states["U"] and not current_U:
            selected_index = max(0, selected_index - 1)
            last_press_time["U"] = now
            last_repeat_time["U"] = now
        elif not current_U and now - last_press_time["U"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["U"] >= REPEAT_INTERVAL:
                selected_index = max(0, selected_index - 1)
                last_repeat_time["U"] = now
        current_D = read_button(PIN_D)
        if prev_states["D"] and not current_D:
            selected_index = min(len(modes) - 1, selected_index + 1)
            last_press_time["D"] = now
            last_repeat_time["D"] = now
        elif not current_D and now - last_press_time["D"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["D"] >= REPEAT_INTERVAL:
                selected_index = min(len(modes) - 1, selected_index + 1)
                last_repeat_time["D"] = now
        current_L = read_button(PIN_L)
        if prev_states["L"] and not current_L:
            selected_index = max(0, selected_index - 1)
            last_press_time["L"] = now
            last_repeat_time["L"] = now
        elif not current_L and now - last_press_time["L"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["L"] >= REPEAT_INTERVAL:
                selected_index = max(0, selected_index - 1)
                last_repeat_time["L"] = now
        current_R = read_button(PIN_R)
        if prev_states["R"] and not current_R:
            selected_index = min(len(modes) - 1, selected_index + 1)
            last_press_time["R"] = now
            last_repeat_time["R"] = now
        elif not current_R and now - last_press_time["R"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["R"] >= REPEAT_INTERVAL:
                selected_index = min(len(modes) - 1, selected_index + 1)
                last_repeat_time["R"] = now
        current_A = read_button(PIN_A)
        if prev_states["A"] and not current_A:
            return None
        current_B = read_button(PIN_B)
        if prev_states["B"] and not current_B:
            return modes[selected_index]
        current_C = read_button(PIN_C)
        prev_states["U"] = current_U
        prev_states["D"] = current_D
        prev_states["L"] = current_L
        prev_states["R"] = current_R
        prev_states["A"] = current_A
        prev_states["B"] = current_B
        prev_states["C"] = current_C
        menu.selected_index = selected_index
        render_menu(menu, context.draw, context.width, context.height, context.fonts)
        context.disp.display(context.image)
        time.sleep(BUTTON_POLL_DELAY)
