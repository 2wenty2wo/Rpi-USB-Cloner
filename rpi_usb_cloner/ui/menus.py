import time
from dataclasses import dataclass
from typing import List, Optional

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


def render_menu(menu, draw, width, height, fonts):
    context = display.get_display_context()
    draw.rectangle((0, 0, width, height), outline=0, fill=0)
    current_y = context.top
    if menu.title:
        title_font = menu.title_font or fonts["title"]
        title_bbox = draw.textbbox((context.x - 11, current_y), menu.title, font=title_font)
        draw.text((context.x - 11, current_y), menu.title, font=title_font, fill=255)
        title_height = title_bbox[3] - title_bbox[1]
        current_y += title_height + 2
    if menu.content_top is not None:
        current_y = menu.content_top

    items_font = menu.items_font or fonts["items"]
    line_height = 8
    try:
        bbox = items_font.getbbox("Ag")
        line_height = max(bbox[3] - bbox[1], line_height)
    except AttributeError:
        if hasattr(items_font, "getmetrics"):
            ascent, descent = items_font.getmetrics()
            line_height = max(ascent + descent, line_height)

    for item_index, item in enumerate(menu.items):
        lines = item.lines
        row_height = max(len(lines), 1) * line_height + 4
        row_top = current_y
        text_y_offset = (row_height - len(lines) * line_height) // 2
        is_selected = item_index == menu.selected_index
        if is_selected:
            draw.rectangle((0, row_top - 1, width, row_top + row_height - 1), outline=0, fill=1)
        for line_index, line in enumerate(lines):
            text_color = 0 if is_selected else 255
            draw.text(
                (context.x - 11, row_top + text_y_offset + line_index * line_height),
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


def wait_for_buttons_release(buttons, poll_delay=0.05):
    while any(is_pressed(pin) for pin in buttons):
        time.sleep(poll_delay)


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
    while True:
        current_U = read_button(PIN_U)
        if prev_states["U"] and not current_U:
            selected_index = max(0, selected_index - 1)
        current_D = read_button(PIN_D)
        if prev_states["D"] and not current_D:
            selected_index = min(len(modes) - 1, selected_index + 1)
        current_L = read_button(PIN_L)
        if prev_states["L"] and not current_L:
            selected_index = max(0, selected_index - 1)
        current_R = read_button(PIN_R)
        if prev_states["R"] and not current_R:
            selected_index = min(len(modes) - 1, selected_index + 1)
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
        time.sleep(0.05)


def select_erase_mode():
    context = display.get_display_context()
    modes = ["quick", "zero", "discard", "secure"]
    selected_index = 0
    menu_items = [MenuItem([mode.upper()]) for mode in modes]
    menu = Menu(
        items=menu_items,
        selected_index=selected_index,
        title="ERASE MODE",
        title_font=context.fontcopy,
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
    while True:
        current_U = read_button(PIN_U)
        if prev_states["U"] and not current_U:
            selected_index = max(0, selected_index - 1)
        current_D = read_button(PIN_D)
        if prev_states["D"] and not current_D:
            selected_index = min(len(modes) - 1, selected_index + 1)
        current_L = read_button(PIN_L)
        if prev_states["L"] and not current_L:
            selected_index = max(0, selected_index - 1)
        current_R = read_button(PIN_R)
        if prev_states["R"] and not current_R:
            selected_index = min(len(modes) - 1, selected_index + 1)
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
        time.sleep(0.05)
