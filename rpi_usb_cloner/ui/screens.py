import threading
import time

from typing import Iterable, Optional

from PIL import ImageFont

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


def _show_icon_font_demo(title: str, font_path, *, icons: Optional[Iterable[str]] = None) -> None:
    context = display.get_display_context()
    title_font = context.fonts.get("title", context.fontdisks)
    content_top = menus.get_standard_content_top(title, title_font=title_font)
    if icons is None:
        icons = ["\uf55a", "\uf060", "\uf30a", "\uf00c"]
    icons = list(icons)
    sizes = [8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 26, 28, 30]
    label_font = context.fontdisks
    icon_font = ImageFont.truetype(font_path, max(sizes))
    max_icon_height = 0
    for glyph in icons:
        bbox = context.draw.textbbox((0, 0), glyph, font=icon_font)
        max_icon_height = max(max_icon_height, bbox[3] - bbox[1])
    label_line_height = display._get_line_height(label_font)
    line_step = max(max_icon_height, label_line_height) + 2
    rows_per_page = max(1, (context.height - content_top - 2) // line_step)
    max_offset = max(0, len(sizes) - rows_per_page)
    scroll_offset = 0

    def render(offset: int) -> int:
        offset = max(0, min(offset, max_offset))
        page_sizes = sizes[offset : offset + rows_per_page]

        draw = context.draw
        draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        draw.text((context.x - 11, context.top), title, font=title_font, fill=255)

        current_y = content_top
        left_x = context.x - 11
        for size in page_sizes:
            icon_font = ImageFont.truetype(font_path, size)
            icon_height = display._get_line_height(icon_font)
            icon_y = current_y + max(0, (line_step - icon_height) // 2)
            label_y = current_y + max(0, (line_step - label_line_height) // 2)
            label_text = f"{size}px"
            draw.text((left_x, label_y), label_text, font=label_font, fill=255)
            label_width = display._measure_text_width(draw, label_text, label_font)
            current_x = left_x + label_width + 6
            for glyph in icons:
                glyph_width = display._measure_text_width(draw, glyph, icon_font)
                if current_x + glyph_width > context.width - 2:
                    break
                draw.text((current_x, icon_y), glyph, font=icon_font, fill=255)
                current_x += glyph_width + 6
            current_y += line_step

        if len(sizes) > rows_per_page:
            footer_text = "▲▼ to scroll"
            footer_height = display._get_line_height(label_font)
            footer_y = context.height - footer_height - 1
            footer_x = left_x
            draw.text((footer_x, footer_y), footer_text, font=label_font, fill=255)

        context.disp.display(context.image)
        return offset

    scroll_offset = render(scroll_offset)
    menus.wait_for_buttons_release([gpio.PIN_A, gpio.PIN_B, gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D])
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
        if prev_states["A"] and not current_a:
            return
        current_b = gpio.read_button(gpio.PIN_B)
        if prev_states["B"] and not current_b:
            return
        current_l = gpio.read_button(gpio.PIN_L)
        if prev_states["L"] and not current_l:
            return
        current_r = gpio.read_button(gpio.PIN_R)
        current_u = gpio.read_button(gpio.PIN_U)
        if prev_states["U"] and not current_u:
            scroll_offset = max(0, scroll_offset - 1)
            scroll_offset = render(scroll_offset)
        current_d = gpio.read_button(gpio.PIN_D)
        if prev_states["D"] and not current_d:
            scroll_offset = min(max_offset, scroll_offset + 1)
            scroll_offset = render(scroll_offset)
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        time.sleep(0.05)


def show_font_awesome_demo(title: str = "FONT AWESOME") -> None:
    font_path = display.ASSETS_DIR / "fonts" / "Font-Awesome-7-Free-Solid-900.otf"
    _show_icon_font_demo(title, font_path)


def show_lucide_demo(title: str = "LUCIDE") -> None:
    font_path = display.ASSETS_DIR / "fonts" / "lucide.ttf"
    lucide_icons = [chr(57518), chr(57778), chr(57452)]
    _show_icon_font_demo(title, font_path, icons=lucide_icons)


def show_heroicons_demo(title: str = "HEROICONS") -> None:
    font_path = display.ASSETS_DIR / "fonts" / "his.ttf"
    heroicons_icons = [chr(0xE934), chr(0xE963), chr(0xE964), chr(0xEA27)]
    _show_icon_font_demo(title, font_path, icons=heroicons_icons)


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


def render_info_screen(
    title: str,
    lines: Iterable[str],
    *,
    page_index: int = 0,
    title_font=None,
    body_font=None,
    content_top: Optional[int] = None,
) -> tuple[int, int]:
    if content_top is None:
        content_top = menus.get_standard_content_top(title, title_font=title_font)
    return display.render_paginated_lines(
        title,
        list(lines),
        page_index=page_index,
        title_font=title_font,
        items_font=body_font,
        content_top=content_top,
    )


def render_confirmation_screen(
    title: str,
    prompt: str,
    *,
    selected_index: int = 0,
) -> None:
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    title_font = context.fonts.get("title", context.fontdisks)
    draw.text((context.x - 11, context.top), title, font=title_font, fill=255)
    prompt_font = context.fontdisks
    button_font = context.fontcopy
    content_top = menus.get_standard_content_top(title, title_font=title_font)
    prompt_lines = display._wrap_lines_to_width(
        [prompt],
        prompt_font,
        context.width - 8,
    )
    prompt_line_height = display._get_line_height(prompt_font)
    prompt_line_step = prompt_line_height + 2
    prompt_height = max(prompt_line_height, len(prompt_lines) * prompt_line_step - 2)
    button_height = max(16, display._get_line_height(button_font) + 6)
    button_label = "YES"
    button_width = max(
        36,
        display._measure_text_width(draw, button_label, button_font) + 16,
    )
    button_y = int(content_top + (context.height - content_top) * 0.55)
    prompt_area_height = max(0, button_y - content_top - 6)
    prompt_start_y = content_top + max(0, (prompt_area_height - prompt_height) // 2)
    prompt_bottom = prompt_start_y + prompt_height
    min_button_y = int(prompt_bottom + 4)
    max_button_y = context.height - button_height - 4
    button_y = max(min_button_y, min(button_y, max_button_y))
    left_x = int(context.width * 0.25 - button_width / 2)
    right_x = int(context.width * 0.75 - button_width / 2)

    current_y = prompt_start_y
    for line in prompt_lines:
        text_width = display._measure_text_width(draw, line, prompt_font)
        line_x = int((context.width - text_width) / 2)
        draw.text((line_x, current_y), line, font=prompt_font, fill=255)
        current_y += prompt_line_step

    buttons = [("NO", left_x), ("YES", right_x)]
    for index, (label, x_pos) in enumerate(buttons):
        is_selected = index == selected_index
        rect = (x_pos, button_y, x_pos + button_width, button_y + button_height)
        if is_selected:
            draw.rectangle(rect, outline=255, fill=255)
        else:
            draw.rectangle(rect, outline=255, fill=0)
        text_width = display._measure_text_width(draw, label, button_font)
        text_height = display._get_line_height(button_font)
        text_x = int(x_pos + (button_width - text_width) / 2)
        text_y = int(button_y + (button_height - text_height) / 2)
        draw.text((text_x, text_y), label, font=button_font, fill=0 if is_selected else 255)
    context.disp.display(context.image)


def render_progress_screen(
    title: str,
    lines: Iterable[str],
    *,
    progress_ratio: Optional[float] = None,
    animate: bool = False,
) -> None:
    context = display.get_display_context()
    title_font = context.fonts.get("title", context.fontdisks)
    body_font = context.fontdisks
    content_top = menus.get_standard_content_top(title, title_font=title_font)
    wrapped_lines = display._wrap_lines_to_width(
        list(lines),
        body_font,
        context.width - 8,
    )
    line_height = display._get_line_height(body_font)
    line_step = line_height + 2
    text_height = max(line_height, len(wrapped_lines) * line_step - 2)
    bar_height = max(10, line_height + 4)
    bar_width = context.width - 16
    bar_y = int(content_top + (context.height - content_top) * 0.65)
    text_area_height = max(0, bar_y - content_top - 6)
    text_start_y = content_top + max(0, (text_area_height - text_height) // 2)
    text_bottom = text_start_y + text_height
    min_bar_y = int(text_bottom + 6)
    max_bar_y = context.height - bar_height - 4
    bar_y = max(min_bar_y, min(bar_y, max_bar_y))
    bar_x = int((context.width - bar_width) / 2)

    def render_frame(current_ratio: Optional[float], phase: float = 0.0) -> None:
        draw = context.draw
        draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        draw.text((context.x - 11, context.top), title, font=title_font, fill=255)

        current_y = text_start_y
        for line in wrapped_lines:
            text_width = display._measure_text_width(draw, line, body_font)
            line_x = int((context.width - text_width) / 2)
            draw.text((line_x, current_y), line, font=body_font, fill=255)
            current_y += line_step

        bar_rect = (bar_x, bar_y, bar_x + bar_width, bar_y + bar_height)
        draw.rectangle(bar_rect, outline=255, fill=0)

        inner_left = bar_x + 1
        inner_right = bar_x + bar_width - 1
        inner_width = max(0, inner_right - inner_left)
        inner_top = bar_y + 1
        inner_bottom = bar_y + bar_height - 1
        if inner_width <= 0 or inner_bottom <= inner_top:
            context.disp.display(context.image)
            return

        if current_ratio is None:
            window_width = max(6, int(inner_width * 0.25))
            travel = max(1, inner_width - window_width)
            offset = int(travel * phase)
            fill_left = inner_left + offset
            fill_right = fill_left + window_width
        else:
            clamped = max(0.0, min(1.0, float(current_ratio)))
            fill_right = inner_left + int(inner_width * clamped)
            fill_left = inner_left

        if fill_right > fill_left:
            draw.rectangle(
                (fill_left, inner_top, fill_right, inner_bottom),
                outline=255,
                fill=255,
            )
        context.disp.display(context.image)

    if not animate:
        render_frame(progress_ratio)
        return

    if callable(progress_ratio):
        phase = 0.0
        while True:
            current_ratio = progress_ratio()
            render_frame(current_ratio, phase=phase)
            if current_ratio is not None and current_ratio >= 1:
                return
            phase = (phase + 0.08) % 1.0
            time.sleep(0.08)
    elif progress_ratio is None:
        phase = 0.0
        while True:
            render_frame(None, phase=phase)
            phase = (phase + 0.08) % 1.0
            time.sleep(0.08)
    else:
        render_frame(progress_ratio)


def show_logs(app_context, *, title: str = "LOGS", max_lines: int = 40) -> None:
    page_index = 0

    def render(page: int) -> tuple[int, int]:
        lines = list(app_context.log_buffer)[-max_lines:]
        if not lines:
            lines = ["No logs yet."]
        return render_info_screen(title, lines, page_index=page)

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
