import time

from typing import Iterable, Optional

from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.services import wifi
from rpi_usb_cloner.ui import display, keyboard, menus


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
    while True:
        networks = wifi.list_networks()
        if not networks:
            display.display_lines([title, "No networks", "Press BACK"])
            menus.wait_for_buttons_release([gpio.PIN_A, gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D])
            while True:
                current_a = gpio.read_button(gpio.PIN_A)
                current_l = gpio.read_button(gpio.PIN_L)
                if not current_a or not current_l:
                    return
                time.sleep(0.05)

        menu_lines = []
        for network in networks:
            ssid = network.ssid or "<hidden>"
            lock = "*" if network.secured else ""
            signal = f"{network.signal}%" if network.signal is not None else "?"
            in_use = "✔" if network.in_use else ""
            menu_lines.append(f"{ssid} {signal}{lock}{in_use}".strip())
        menu_lines.append("Refresh")

        selection = menus.select_list(title, menu_lines, footer=["BACK", "OK"])
        if selection is None:
            return
        if selection == len(menu_lines) - 1:
            continue
        selected_network = networks[selection]
        password = None
        if selected_network.secured:
            password = keyboard.prompt_text(
                "PASSWORD",
                masked=True,
            )
            if password is None:
                continue
        connected = wifi.connect(selected_network.ssid, password=password)
        if connected:
            display.display_lines([title, f"Connected to", selected_network.ssid])
        else:
            display.display_lines([title, "Connection failed", selected_network.ssid])
        time.sleep(1.5)
