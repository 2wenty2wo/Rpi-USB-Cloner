"""Logs screen rendering function."""

import time

from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.menu.model import get_screen_icon
from rpi_usb_cloner.ui import menus

from .info import render_info_screen


def show_logs(app_context, *, title: str = "LOGS", max_lines: int = 40) -> None:
    page_index = 0
    title_icon = get_screen_icon("logs")

    def render(page: int) -> tuple[int, int]:
        lines = list(app_context.log_buffer)[-max_lines:]
        if not lines:
            lines = ["No logs yet."]
        return render_info_screen(title, lines, page_index=page, title_icon=title_icon)

    total_pages, page_index = render(page_index)
    menus.wait_for_buttons_release([gpio.PIN_A, gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D])
    prev_states = {
        "A": gpio.read_button(gpio.PIN_A),
        "L": gpio.read_button(gpio.PIN_L),
        "R": gpio.read_button(gpio.PIN_R),
        "U": gpio.read_button(gpio.PIN_U),
        "D": gpio.read_button(gpio.PIN_D),
    }
    while True:
        current_a = gpio.read_button(gpio.PIN_A)
        if prev_states["A"] and not current_a:
            return
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
        prev_states["A"] = current_a
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        time.sleep(0.05)
