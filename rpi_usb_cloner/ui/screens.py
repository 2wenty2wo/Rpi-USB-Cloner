import time

from typing import Iterable, Optional

from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.ui import display, menus


def render_status_screen(
    title: str,
    status: str = "Running...",
    *,
    progress_line: Optional[str] = None,
    extra_lines: Optional[Iterable[str]] = None,
    title_font=None,
    body_font=None,
) -> None:
    lines = [status]
    if progress_line:
        lines.append(progress_line)
    if extra_lines:
        lines.extend(line for line in extra_lines if line)
    display.render_paginated_lines(
        title,
        lines,
        page_index=0,
        title_font=title_font,
        items_font=body_font,
    )


def show_coming_soon(title="COMING SOON", delay=1) -> None:
    display.display_lines([title, "Not implemented", "yet"])
    if delay:
        time.sleep(delay)


def render_status_screen(
    title: str,
    status: str = "Running...",
    *,
    progress_line: Optional[str] = None,
    extra_lines: Optional[Iterable[str]] = None,
    title_font=None,
    body_font=None,
) -> None:
    lines = [status]
    if progress_line:
        lines.append(progress_line)
    if extra_lines:
        lines.extend(line for line in extra_lines if line)
    display.render_paginated_lines(
        title,
        lines,
        page_index=0,
        title_font=title_font,
        items_font=body_font,
    )


def show_logs(app_context, *, title: str = "LOGS", max_lines: int = 40) -> None:
    page_index = 0

    def render(page: int) -> tuple[int, int]:
        lines = list(app_context.log_buffer)[-max_lines:]
        if not lines:
            lines = ["No logs yet."]
        return display.render_paginated_lines(title, lines, page_index=page)

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


def show_wifi_settings(*, title: str = "WIFI") -> None:
    page_index = 0
    lines = [
        "Configure Wi-Fi",
        "using system tools",
        "then return here.",
        "Press BACK to exit.",
    ]

    def render(page: int) -> tuple[int, int]:
        return display.render_paginated_lines(title, lines, page_index=page)

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
            return
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
