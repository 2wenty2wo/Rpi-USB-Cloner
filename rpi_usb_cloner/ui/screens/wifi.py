"""WiFi settings screen."""

import threading
import time
from typing import Optional

from rpi_usb_cloner.menu.model import get_screen_icon
from rpi_usb_cloner.services import wifi
from rpi_usb_cloner.ui import display, keyboard, menus


_WIFI_STATUS_CACHE = {"connected": False, "ssid": None, "ip": None}
_WIFI_STATUS_LOCK = threading.Lock()


def _update_wifi_status_cache() -> None:
    status = wifi.get_status_cached()
    with _WIFI_STATUS_LOCK:
        _WIFI_STATUS_CACHE.update(
            {
                "connected": status.get("connected", False),
                "ssid": status.get("ssid"),
                "ip": status.get("ip"),
            }
        )


def _get_wifi_status_cache() -> dict:
    with _WIFI_STATUS_LOCK:
        return dict(_WIFI_STATUS_CACHE)


def show_wifi_settings(*, title: str = "WIFI") -> None:
    title_icon = get_screen_icon("wifi")
    content_top = menus.get_standard_content_top(title, title_icon=title_icon)
    status_updated = threading.Event()
    status_thread = None
    status_thread_lock = threading.Lock()
    screen_active = True

    def refresh_status_async() -> None:
        nonlocal status_thread
        with status_thread_lock:
            if status_thread and status_thread.is_alive():
                return
            status_updated.clear()

            def run() -> None:
                _update_wifi_status_cache()
                status_updated.set()

            status_thread = threading.Thread(target=run, daemon=True)
            status_thread.start()

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
        display.render_paginated_lines(
            title,
            [spinner_frames[0]],
            page_index=0,
            content_top=content_top,
            title_icon=title_icon,
        )

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
            display.render_paginated_lines(
                title,
                [frame],
                page_index=0,
                content_top=content_top,
                title_icon=title_icon,
            )
            frame_index += 1
            time.sleep(refresh_interval_s)
        if scan_thread.is_alive():
            return [], True
        return result["networks"], False

    networks: list[wifi.WifiNetwork] = []
    timed_out = False
    needs_scan = False
    refresh_status_async()

    def build_menu_state() -> (
        tuple[list[str], list[str], list[wifi.WifiNetwork], Optional[int]]
    ):
        visible_networks = [network for network in networks if network.ssid]
        cached_status = _get_wifi_status_cache()
        is_connected = cached_status["connected"]
        active_ssid = cached_status["ssid"]
        ip_address = cached_status["ip"] if is_connected else None
        status_lines = [
            f"Wi-Fi: {'Connected' if is_connected else 'Not connected'}",
            f"SSID: {active_ssid or '--'}",
            f"IP: {ip_address or '--'}",
        ]
        if not visible_networks:
            if timed_out:
                status_lines.append("Scan timed out")
            else:
                status_lines.append(
                    "No networks" if not networks else "No visible networks"
                )

        menu_lines = list(status_lines)
        disconnect_index = None
        if is_connected:
            disconnect_index = len(menu_lines)
            menu_lines.append("Disconnect")
        menu_lines.append("Search")
        for network in visible_networks:
            ssid = network.ssid
            lock = "*" if network.secured else ""
            signal = f"{network.signal}%" if network.signal is not None else "?"
            in_use = "✔" if network.in_use else ""
            menu_lines.append(f"{ssid} {signal}{lock}{in_use}".strip())
        menu_lines.append("Refresh")
        return menu_lines, status_lines, visible_networks, disconnect_index

    menu_state = build_menu_state()

    def refresh_menu_if_status_ready() -> Optional[list[str]]:
        nonlocal menu_state
        if not screen_active or not status_updated.is_set():
            return None
        status_updated.clear()
        menu_state = build_menu_state()
        return menu_state[0]

    while True:
        if needs_scan:
            networks, timed_out = scan_networks_with_spinner()
            needs_scan = False
        menu_state = build_menu_state()
        menu_lines, status_lines, visible_networks, disconnect_index = menu_state

        selection = menus.render_menu_list(
            title,
            menu_lines,
            content_top=content_top,
            refresh_callback=refresh_menu_if_status_ready,
            title_icon=title_icon,
            transition_direction="forward",
        )
        menu_lines, status_lines, visible_networks, disconnect_index = menu_state
        search_index = len(status_lines) + (1 if disconnect_index is not None else 0)
        network_start_index = search_index + 1
        refresh_index = len(menu_lines) - 1
        if selection is None:
            screen_active = False
            return
        if selection < len(status_lines):
            continue
        if disconnect_index is not None and selection == disconnect_index:
            disconnected = wifi.disconnect()
            if disconnected:
                display.display_lines([title, "Disconnected"])
            else:
                display.display_lines([title, "Disconnect failed"])
            time.sleep(1.5)
            refresh_status_async()
            continue
        if selection in {search_index, refresh_index}:
            needs_scan = True
            continue
        selected_network = visible_networks[selection - network_start_index]
        password = None
        if selected_network.secured:
            password = keyboard.prompt_text(
                "PASSWORD",
                masked=True,
                title_icon=keyboard.PASSWORD_ICON_GLYPH,
            )
            if password is None:
                continue
        connected = wifi.connect(selected_network.ssid, password=password)
        if connected:
            display.display_lines([title, "Connected to", selected_network.ssid])
        else:
            display.display_lines([title, "Connection failed", selected_network.ssid])
        time.sleep(1.5)
        refresh_status_async()
