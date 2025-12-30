import time
from dataclasses import dataclass
from typing import Optional

from mount import get_device_name, get_model, get_size, get_vendor, list_media_devices

from rpi_usb_cloner import config
from rpi_usb_cloner.services.cloning import normalize_clone_mode
from rpi_usb_cloner.ui.menu import Menu, MenuItem, render_menu

MENU_COPY = 0
MENU_VIEW = 1
MENU_ERASE = 2
MENU_NONE = -1


@dataclass
class ScreenContext:
    disp: object
    draw: object
    image: object
    fonts: dict
    width: int
    height: int
    x: int
    top: int
    fontcopy: object
    fontinsert: object
    fontdisks: object
    read_button: object
    is_pressed: object
    pin_u: int
    pin_d: int
    pin_l: int
    pin_r: int
    pin_a: int
    pin_b: int
    pin_c: int


def display_lines(context: ScreenContext, lines, font=None) -> None:
    draw = context.draw
    width = context.width
    height = context.height
    x = context.x
    top = context.top
    if font is None:
        font = context.fontdisks
    draw.rectangle((0, 0, width, height), outline=0, fill=0)
    y = top
    for line in lines[:6]:
        draw.text((x - 11, y), line, font=font, fill=255)
        y += 10
    context.disp.display(context.image)


def _draw_centered_text(context: ScreenContext, text: str, font) -> None:
    draw = context.draw
    width = context.width
    height = context.height
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    text_x = (width - text_width) // 2
    text_y = (height - text_height) // 2
    draw.text((text_x, text_y), text, font=font, fill=255)


def wait_for_buttons_release(context: ScreenContext, buttons, poll_delay: float = 0.05) -> None:
    while any(context.is_pressed(pin) for pin in buttons):
        time.sleep(poll_delay)


def basemenu(context: ScreenContext, state) -> bool:
    devices = list_media_devices()
    devices_present = bool(devices)
    draw = context.draw
    width = context.width
    height = context.height
    x = context.x
    top = context.top
    if not devices:
        draw.rectangle((0, 0, width, height), outline=0, fill=0)
        _draw_centered_text(context, "INSERT USB", context.fontinsert)
        state.usb_list_index = 0
    else:
        if state.usb_list_index >= len(devices):
            state.usb_list_index = max(len(devices) - 1, 0)
        menu_items = []
        for device in devices:
            menu_items.append(
                MenuItem(
                    [
                        f"{get_device_name(device)} {get_size(device) / 1024 ** 3:.2f}GB",
                        f"{get_vendor(device)} {get_model(device)}",
                    ]
                )
            )
        start_index = max(0, state.usb_list_index - 1)
        max_start = max(len(menu_items) - config.VISIBLE_ROWS, 0)
        if start_index > max_start:
            start_index = max_start
        visible_items = menu_items[start_index : start_index + VISIBLE_ROWS]
        visible_selected_index = state.usb_list_index - start_index
        if state.index not in (MENU_COPY, MENU_VIEW, MENU_ERASE):
            state.index = MENU_COPY
        footer_selected = None
        if state.index in (MENU_COPY, MENU_VIEW, MENU_ERASE):
            footer_selected = state.index
        menu = Menu(
            items=visible_items,
            selected_index=visible_selected_index,
            footer=["COPY", "VIEW", "ERASE"],
            footer_selected_index=footer_selected,
            footer_positions=[x - 11, x + 32, x + 71],
        )
        render_menu(menu, draw, width, height, context.fonts, x=x, top=top)
    context.disp.display(context.image)
    if not devices_present:
        state.index = MENU_NONE
    config.log_debug("Base menu drawn")
    return devices_present


def select_clone_mode(context: ScreenContext) -> Optional[str]:
    modes = ["smart", "exact", "verify"]
    selected_mode = normalize_clone_mode(config.CLONE_MODE)
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
    render_menu(menu, context.draw, context.width, context.height, context.fonts, x=context.x, top=context.top)
    context.disp.display(context.image)
    wait_for_buttons_release(
        context,
        [
            context.pin_u,
            context.pin_d,
            context.pin_l,
            context.pin_r,
            context.pin_a,
            context.pin_b,
            context.pin_c,
        ],
    )
    prev_states = {
        "U": context.read_button(context.pin_u),
        "D": context.read_button(context.pin_d),
        "L": context.read_button(context.pin_l),
        "R": context.read_button(context.pin_r),
        "A": context.read_button(context.pin_a),
        "B": context.read_button(context.pin_b),
        "C": context.read_button(context.pin_c),
    }
    while True:
        current_U = context.read_button(context.pin_u)
        if prev_states["U"] and not current_U:
            selected_index = max(0, selected_index - 1)
            config.log_debug(f"Clone mode selection changed: {modes[selected_index]}")
        current_D = context.read_button(context.pin_d)
        if prev_states["D"] and not current_D:
            selected_index = min(len(modes) - 1, selected_index + 1)
            config.log_debug(f"Clone mode selection changed: {modes[selected_index]}")
        current_L = context.read_button(context.pin_l)
        if prev_states["L"] and not current_L:
            selected_index = max(0, selected_index - 1)
        current_R = context.read_button(context.pin_r)
        if prev_states["R"] and not current_R:
            selected_index = min(len(modes) - 1, selected_index + 1)
        current_A = context.read_button(context.pin_a)
        if prev_states["A"] and not current_A:
            return None
        current_B = context.read_button(context.pin_b)
        if prev_states["B"] and not current_B:
            return modes[selected_index]
        current_C = context.read_button(context.pin_c)
        prev_states["U"] = current_U
        prev_states["D"] = current_D
        prev_states["L"] = current_L
        prev_states["R"] = current_R
        prev_states["A"] = current_A
        prev_states["B"] = current_B
        prev_states["C"] = current_C
        menu.selected_index = selected_index
        render_menu(menu, context.draw, context.width, context.height, context.fonts, x=context.x, top=context.top)
        context.disp.display(context.image)
        time.sleep(0.05)


def select_erase_mode(context: ScreenContext) -> Optional[str]:
    modes = ["quick", "zero", "discard", "secure"]
    selected_index = 0
    menu_items = [MenuItem([mode.upper()]) for mode in modes]
    menu = Menu(
        items=menu_items,
        selected_index=selected_index,
        title="ERASE MODE",
        title_font=context.fontcopy,
    )
    render_menu(menu, context.draw, context.width, context.height, context.fonts, x=context.x, top=context.top)
    context.disp.display(context.image)
    wait_for_buttons_release(
        context,
        [
            context.pin_u,
            context.pin_d,
            context.pin_l,
            context.pin_r,
            context.pin_a,
            context.pin_b,
            context.pin_c,
        ],
    )
    prev_states = {
        "U": context.read_button(context.pin_u),
        "D": context.read_button(context.pin_d),
        "L": context.read_button(context.pin_l),
        "R": context.read_button(context.pin_r),
        "A": context.read_button(context.pin_a),
        "B": context.read_button(context.pin_b),
        "C": context.read_button(context.pin_c),
    }
    while True:
        current_U = context.read_button(context.pin_u)
        if prev_states["U"] and not current_U:
            selected_index = max(0, selected_index - 1)
            config.log_debug(f"Erase mode selection changed: {modes[selected_index]}")
        current_D = context.read_button(context.pin_d)
        if prev_states["D"] and not current_D:
            selected_index = min(len(modes) - 1, selected_index + 1)
            config.log_debug(f"Erase mode selection changed: {modes[selected_index]}")
        current_L = context.read_button(context.pin_l)
        if prev_states["L"] and not current_L:
            selected_index = max(0, selected_index - 1)
        current_R = context.read_button(context.pin_r)
        if prev_states["R"] and not current_R:
            selected_index = min(len(modes) - 1, selected_index + 1)
        current_A = context.read_button(context.pin_a)
        if prev_states["A"] and not current_A:
            return None
        current_B = context.read_button(context.pin_b)
        if prev_states["B"] and not current_B:
            return modes[selected_index]
        current_C = context.read_button(context.pin_c)
        prev_states["U"] = current_U
        prev_states["D"] = current_D
        prev_states["L"] = current_L
        prev_states["R"] = current_R
        prev_states["A"] = current_A
        prev_states["B"] = current_B
        prev_states["C"] = current_C
        menu.selected_index = selected_index
        render_menu(menu, context.draw, context.width, context.height, context.fonts, x=context.x, top=context.top)
        context.disp.display(context.image)
        time.sleep(0.05)
