import subprocess
import threading
import time
from pathlib import Path

from typing import Iterable, Optional

from rpi_usb_cloner.hardware import gpio
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


def render_status_template(
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
    render_status_template(
        title,
        status,
        progress_line=progress_line,
        extra_lines=extra_lines,
        title_font=title_font,
        body_font=body_font,
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
    content_top = menus.get_standard_content_top(title)
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

    def build_menu_state() -> tuple[list[str], list[str], list[wifi.WifiNetwork], Optional[int]]:
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
                status_lines.append("No networks" if not networks else "No visible networks")

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
            )
            if password is None:
                continue
        connected = wifi.connect(selected_network.ssid, password=password)
        if connected:
            display.display_lines([title, f"Connected to", selected_network.ssid])
        else:
            display.display_lines([title, "Connection failed", selected_network.ssid])
        time.sleep(1.5)
        refresh_status_async()


def _get_git_version(repo_root: Path) -> Optional[str]:
    describe = subprocess.run(
        ["git", "-C", str(repo_root), "describe", "--tags", "--always", "--dirty"],
        capture_output=True,
        text=True,
        check=False,
    )
    if describe.returncode == 0:
        value = describe.stdout.strip()
        if value:
            return value
    rev_parse = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if rev_parse.returncode == 0:
        value = rev_parse.stdout.strip()
        if value:
            return value
    return None


def _get_app_version() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    version = _get_git_version(repo_root)
    if version:
        return version
    version_file = repo_root / "VERSION"
    if version_file.exists():
        value = version_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    return "unknown"


def show_update_version(*, title: str = "UPDATE") -> None:
    version = _get_app_version()
    version_lines = [f"Version: {version}"]
    content_top = menus.get_standard_content_top(title)
    display.render_paginated_lines(
        title,
        version_lines,
        page_index=0,
        content_top=content_top,
    )
    while True:
        selection = menus.render_menu_list(title, ["UPDATE", "BACK"], content_top=content_top)
        if selection is None or selection == 1:
            return
        if selection == 0:
            display.render_paginated_lines(
                title,
                ["Update not implemented yet."],
                page_index=0,
                content_top=content_top,
            )
            time.sleep(1.5)
            display.render_paginated_lines(
                title,
                version_lines,
                page_index=0,
                content_top=content_top,
            )
