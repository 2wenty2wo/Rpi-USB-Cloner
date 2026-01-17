"""Info and paginated screen rendering functions."""

import time
from typing import Iterable, Optional

from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.ui import display, menus
from rpi_usb_cloner.ui.constants import BUTTON_POLL_DELAY


def render_info_screen(
    title: str,
    lines: Iterable[str],
    *,
    page_index: int = 0,
    title_icon: Optional[str] = None,
    title_font=None,
    body_font=None,
    content_top: Optional[int] = None,
) -> tuple[int, int]:
    if content_top is None:
        content_top = menus.get_standard_content_top(
            title,
            title_font=title_font,
            title_icon=title_icon,
        )
    return display.render_paginated_lines(
        title,
        list(lines),
        page_index=page_index,
        title_font=title_font,
        items_font=body_font,
        content_top=content_top,
        title_icon=title_icon,
    )


def wait_for_paginated_input(
    title: str,
    lines: Iterable[str],
    *,
    page_index: int = 0,
    title_icon: Optional[str] = None,
    title_font=None,
    body_font=None,
    buttons: Optional[Iterable[int]] = None,
    poll_delay: float = BUTTON_POLL_DELAY,
) -> None:
    if buttons is None:
        buttons = (gpio.PIN_A, gpio.PIN_B)
    buttons = tuple(buttons)
    line_list = list(lines)

    def render(page: int) -> tuple[int, int]:
        return display.render_paginated_lines(
            title,
            line_list,
            page_index=page,
            title_font=title_font,
            items_font=body_font,
            title_icon=title_icon,
        )

    total_pages, page_index = render(page_index)
    nav_buttons = (gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D)
    menus.wait_for_buttons_release(buttons + nav_buttons, poll_delay=poll_delay)
    prev_states = {
        "A": gpio.read_button(gpio.PIN_A),
        "B": gpio.read_button(gpio.PIN_B),
        "L": gpio.read_button(gpio.PIN_L),
        "R": gpio.read_button(gpio.PIN_R),
        "U": gpio.read_button(gpio.PIN_U),
        "D": gpio.read_button(gpio.PIN_D),
    }
    while True:
        current_a = gpio.read_button(gpio.PIN_A)
        if gpio.PIN_A in buttons and prev_states["A"] and not current_a:
            return
        current_b = gpio.read_button(gpio.PIN_B)
        if gpio.PIN_B in buttons and prev_states["B"] and not current_b:
            return
        if total_pages > 1:
            current_l = gpio.read_button(gpio.PIN_L)
            if prev_states["L"] and not current_l:
                page_index = max(0, page_index - 1)
                total_pages, page_index = render(page_index)
            current_r = gpio.read_button(gpio.PIN_R)
            if prev_states["R"] and not current_r:
                page_index = min(total_pages - 1, page_index + 1)
                total_pages, page_index = render(page_index)
            current_u = gpio.read_button(gpio.PIN_U)
            if prev_states["U"] and not current_u:
                page_index = max(0, page_index - 1)
                total_pages, page_index = render(page_index)
            current_d = gpio.read_button(gpio.PIN_D)
            if prev_states["D"] and not current_d:
                page_index = min(total_pages - 1, page_index + 1)
                total_pages, page_index = render(page_index)
        else:
            current_l = gpio.read_button(gpio.PIN_L)
            current_r = gpio.read_button(gpio.PIN_R)
            current_u = gpio.read_button(gpio.PIN_U)
            current_d = gpio.read_button(gpio.PIN_D)
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        time.sleep(poll_delay)
