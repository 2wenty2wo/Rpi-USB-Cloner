import threading
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
    def scan_networks_with_spinner(
        *,
        scan_timeout_s: float = 15.0,
        refresh_interval_s: float = 0.25,
    ) -> tuple[list[wifi.WifiNetwork], bool]:
        spinner_frames = [
            "Searching",
            "Searching.",
            "Searching..",
            "Searching...",
        ]
        display.render_paginated_lines(title, [spinner_frames[0]], page_index=0)

        result: dict[str, list[wifi.WifiNetwork]] = {"networks": []}

        def run_scan() -> None:
            result["networks"] = wifi.list_networks()

        scan_thread = threading.Thread(target=run_scan, daemon=True)
        scan_thread.start()
        start_time = time.monotonic()
        frame_index = 0
        while scan_thread.is_alive():
            elapsed = time.monotonic() - start_time
            if elapsed >= scan_timeout_s:
                break
            frame = spinner_frames[frame_index % len(spinner_frames)]
            display.render_paginated_lines(title, [frame], page_index=0)
            frame_index += 1
            time.sleep(refresh_interval_s)
        if scan_thread.is_alive():
            return [], True
        return result["networks"], False

    while True:
        networks, timed_out = scan_networks_with_spinner()
        visible_networks = [network for network in networks if network.ssid]
        if not visible_networks:
            if timed_out:
                message = "Scan timed out"
            else:
                message = "No networks" if not networks else "No visible networks"
            context = display.get_display_context()
            display.render_paginated_lines(
                title,
                [message, "Press BACK"],
                page_index=0,
                title_font=context.fonts.get("title", context.fontdisks),
            )
            menus.wait_for_buttons_release([gpio.PIN_A, gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D])
            while True:
                current_a = gpio.read_button(gpio.PIN_A)
                current_l = gpio.read_button(gpio.PIN_L)
                if not current_a or not current_l:
                    return
                time.sleep(0.05)

        active_ssid = wifi.get_active_ssid()
        is_connected = wifi.is_connected()
        ip_address = wifi.get_ip_address() if is_connected else None
        status_lines = [
            f"Wi-Fi: {'Connected' if is_connected else 'Not connected'}",
            f"SSID: {active_ssid or '--'}",
            f"IP: {ip_address or '--'}",
        ]

        menu_lines = list(status_lines)
        for network in visible_networks:
            ssid = network.ssid
            lock = "*" if network.secured else ""
            signal = f"{network.signal}%" if network.signal is not None else "?"
            in_use = "✔" if network.in_use else ""
            menu_lines.append(f"{ssid} {signal}{lock}{in_use}".strip())
        menu_lines.append("Refresh")

        selection = menus.select_list(title, menu_lines)
        if selection is None:
            return
        if selection < len(status_lines):
            continue
        if selection == len(menu_lines) - 1:
            continue
        selected_network = visible_networks[selection - len(status_lines)]
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
