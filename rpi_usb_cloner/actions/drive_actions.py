from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Callable, Iterable, Optional, Set

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.services import drives
from rpi_usb_cloner.storage import devices
from rpi_usb_cloner.storage.clone import clone_device, erase_device
from rpi_usb_cloner.storage.devices import (
    format_device_label,
    get_children,
    human_size,
    list_usb_disks,
)
from rpi_usb_cloner.storage.image_repo import find_image_repos
from rpi_usb_cloner.ui import display, menus, screens
from rpi_usb_cloner.ui.icons import ALERT_ICON, DRIVES_ICON, EJECT_ICON, SPARKLES_ICON
from PIL import ImageDraw


def copy_drive(
    *,
    state: app_state.AppState,
    clone_mode: str,
    log_debug: Optional[Callable[[str], None]],
    get_selected_usb_name: Callable[[], Optional[str]],
) -> None:
    source, target = _pick_source_target(get_selected_usb_name)
    if not source or not target:
        screens.render_error_screen(
            title="COPY DRIVES",
            message="NEED 2 USBS",
            title_icon=DRIVES_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1)
        return
    source_name = source.get("name")
    target_name = target.get("name")
    title = "COPY"
    prompt = f"Clone {source_name} to {target_name}?"
    confirm_selection = app_state.CONFIRM_NO
    screens.render_confirmation_screen(
        title,
        [prompt],
        selected_index=confirm_selection,
    )
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B, gpio.PIN_C])
    prev_states = {
        "L": gpio.read_button(gpio.PIN_L),
        "R": gpio.read_button(gpio.PIN_R),
        "A": gpio.read_button(gpio.PIN_A),
        "B": gpio.read_button(gpio.PIN_B),
        "C": gpio.read_button(gpio.PIN_C),
    }
    try:
        while True:
            current_R = gpio.read_button(gpio.PIN_R)
            if prev_states["R"] and not current_R:
                if confirm_selection == app_state.CONFIRM_NO:
                    confirm_selection = app_state.CONFIRM_YES
                    _log_debug(log_debug, "Copy menu selection changed: YES")
                    state.run_once = 0
                elif confirm_selection == app_state.CONFIRM_YES:
                    confirm_selection = app_state.CONFIRM_YES
                    _log_debug(log_debug, "Copy menu selection changed: YES")
                    state.lcdstart = datetime.now()
                    state.run_once = 0
            current_L = gpio.read_button(gpio.PIN_L)
            if prev_states["L"] and not current_L:
                if confirm_selection == app_state.CONFIRM_YES:
                    confirm_selection = app_state.CONFIRM_NO
                    _log_debug(log_debug, "Copy menu selection changed: NO")
                    state.lcdstart = datetime.now()
                    state.run_once = 0
            current_A = gpio.read_button(gpio.PIN_A)
            if prev_states["A"] and not current_A:
                _log_debug(log_debug, "Copy menu: Button A pressed")
                return
            current_B = gpio.read_button(gpio.PIN_B)
            if prev_states["B"] and not current_B:
                _log_debug(log_debug, "Copy menu: Button B pressed")
                if confirm_selection == app_state.CONFIRM_YES:
                    screens.render_status_template("COPY", "Running...", progress_line="Starting...")
                    mode = menus.select_clone_mode(clone_mode)
                    if not mode:
                        return
                    screens.render_status_template("COPY", "Running...", progress_line=f"Mode {mode.upper()}")
                    if clone_device(source, target, mode=mode):
                        screens.render_status_template("COPY", "Done", progress_line="Complete.")
                    else:
                        _log_debug(log_debug, "Copy failed")
                        screens.render_status_template("COPY", "Failed", progress_line="Check logs.")
                    time.sleep(1)
                    return
                if confirm_selection == app_state.CONFIRM_NO:
                    return
            current_C = gpio.read_button(gpio.PIN_C)
            if prev_states["C"] and not current_C:
                _log_debug(log_debug, "Copy menu: Button C pressed (ignored)")
            prev_states["R"] = current_R
            prev_states["L"] = current_L
            prev_states["B"] = current_B
            prev_states["A"] = current_A
            prev_states["C"] = current_C
            screens.render_confirmation_screen(
                title,
                [prompt],
                selected_index=confirm_selection,
            )
    except KeyboardInterrupt:
        raise


def drive_info(
    *,
    state: app_state.AppState,
    log_debug: Optional[Callable[[str], None]],
    get_selected_usb_name: Callable[[], Optional[str]],
) -> None:
    page_index = 0
    total_pages, page_index = _view_devices(
        log_debug=log_debug,
        get_selected_usb_name=get_selected_usb_name,
        page_index=page_index,
    )
    menus.wait_for_buttons_release([gpio.PIN_A, gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D])
    last_selected_name = get_selected_usb_name()
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
            total_pages, page_index = _view_devices(
                log_debug=log_debug,
                get_selected_usb_name=get_selected_usb_name,
                page_index=page_index,
            )
        current_r = gpio.read_button(gpio.PIN_R)
        if prev_states["R"] and not current_r:
            page_index = min(total_pages - 1, page_index + 1)
            total_pages, page_index = _view_devices(
                log_debug=log_debug,
                get_selected_usb_name=get_selected_usb_name,
                page_index=page_index,
            )
        current_u = gpio.read_button(gpio.PIN_U)
        if prev_states["U"] and not current_u:
            page_index = max(0, page_index - 1)
            total_pages, page_index = _view_devices(
                log_debug=log_debug,
                get_selected_usb_name=get_selected_usb_name,
                page_index=page_index,
            )
        current_d = gpio.read_button(gpio.PIN_D)
        if prev_states["D"] and not current_d:
            page_index = min(total_pages - 1, page_index + 1)
            total_pages, page_index = _view_devices(
                log_debug=log_debug,
                get_selected_usb_name=get_selected_usb_name,
                page_index=page_index,
            )
        current_selected_name = get_selected_usb_name()
        if current_selected_name != last_selected_name:
            page_index = 0
            total_pages, page_index = _view_devices(
                log_debug=log_debug,
                get_selected_usb_name=get_selected_usb_name,
                page_index=page_index,
            )
            last_selected_name = current_selected_name
        prev_states["A"] = current_a
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        time.sleep(0.05)


def erase_drive(
    *,
    state: app_state.AppState,
    log_debug: Optional[Callable[[str], None]],
    get_selected_usb_name: Callable[[], Optional[str]],
) -> None:
    repo_devices = _get_repo_device_names()
    target_devices = [
        device for device in list_usb_disks() if device.get("name") not in repo_devices
    ]
    if not target_devices:
        display.display_lines(["ERASE", "No USB found"])
        time.sleep(1)
        return
    target_devices = sorted(target_devices, key=lambda d: d.get("name", ""))
    selected_name = get_selected_usb_name()
    target = None
    if selected_name:
        for device in target_devices:
            if device.get("name") == selected_name:
                target = device
                break
    if not target:
        target = target_devices[-1]
    target_name = target.get("name")
    target_names = {device.get("name") for device in target_devices}
    status_line = (
        drives.get_active_drive_label(selected_name)
        if selected_name in target_names
        else None
    ) or format_device_label(target)
    mode = menus.select_erase_mode(status_line=status_line)
    if not mode:
        return
    prompt_lines = [f"ERASE {target_name}", f"MODE {mode.upper()}"]
    if not _confirm_destructive_action(
        state=state,
        log_debug=log_debug,
        prompt_lines=prompt_lines,
    ):
        return
    if not _ensure_root_for_erase():
        return

    # Threading pattern for progress screen (similar to write_image)
    done = threading.Event()
    result_holder: dict[str, bool] = {}
    error_holder: dict[str, Exception] = {}
    progress_lock = threading.Lock()
    progress_lines = ["Preparing..."]
    progress_ratio: Optional[float] = 0.0

    def update_progress(lines: list[str], ratio: Optional[float]) -> None:
        nonlocal progress_lines, progress_ratio
        clamped = None
        if ratio is not None:
            clamped = max(0.0, min(1.0, float(ratio)))
        with progress_lock:
            progress_lines = lines
            if clamped is not None:
                progress_ratio = clamped

    def current_progress() -> tuple[list[str], Optional[float]]:
        with progress_lock:
            return list(progress_lines), progress_ratio

    def worker() -> None:
        try:
            success = erase_device(target, mode, progress_callback=update_progress)
            result_holder["result"] = success
        except Exception as exc:
            error_holder["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    while not done.is_set():
        lines, ratio = current_progress()
        screens.render_progress_screen(
            "ERASE",
            lines,
            progress_ratio=ratio,
            animate=False,
            title_icon=ALERT_ICON,
        )
        time.sleep(0.1)
    thread.join()

    # Display final result
    lines, ratio = current_progress()
    screens.render_progress_screen(
        "ERASE",
        lines,
        progress_ratio=ratio,
        animate=False,
        title_icon=ALERT_ICON,
    )

    if "error" in error_holder:
        error = error_holder["error"]
        _log_debug(log_debug, f"Erase failed with exception: {error}")
        screens.render_status_template("ERASE", "Failed", progress_line="Check logs.")
    elif not result_holder.get("result", False):
        _log_debug(log_debug, "Erase failed")
        screens.render_status_template("ERASE", "Failed", progress_line="Check logs.")
    else:
        screens.render_status_template("ERASE", "Done", progress_line="Complete.")
    time.sleep(1)


def _collect_mountpoints(device: dict) -> Set[str]:
    """Collect all mountpoints for a device and its partitions."""
    mountpoints: Set[str] = set()
    stack = [device]
    while stack:
        current = stack.pop()
        mountpoint = current.get("mountpoint")
        if mountpoint:
            mountpoints.add(mountpoint)
        stack.extend(get_children(current))
    return mountpoints


def _get_repo_device_names() -> Set[str]:
    """Get the set of device names that are repo drives."""
    repos = find_image_repos()
    if not repos:
        return set()

    repo_devices: Set[str] = set()
    usb_devices = list_usb_disks()

    for device in usb_devices:
        mountpoints = _collect_mountpoints(device)
        if any(str(repo).startswith(mount) for mount in mountpoints for repo in repos):
            device_name = device.get("name")
            if device_name:
                repo_devices.add(device_name)

    return repo_devices


def _pick_source_target(
    get_selected_usb_name: Callable[[], Optional[str]],
) -> tuple[Optional[dict], Optional[dict]]:
    repo_devices = _get_repo_device_names()
    devices_list = [
        device
        for device in list_usb_disks()
        if not devices.is_root_device(device) and device.get("name") not in repo_devices
    ]
    if len(devices_list) < 2:
        return None, None
    devices_list = sorted(devices_list, key=lambda d: d.get("name", ""))
    selected_name = get_selected_usb_name()
    selected = None
    if selected_name:
        for device in devices_list:
            if device.get("name") == selected_name:
                selected = device
                break
    if selected:
        remaining = [device for device in devices_list if device.get("name") != selected_name]
        if not remaining:
            return None, None
        source = selected
        target = remaining[0]
    else:
        source = devices_list[0]
        target = devices_list[1]
    return source, target


def _ensure_root_for_erase() -> bool:
    if os.geteuid() != 0:
        display.display_lines(["Run as root"])
        time.sleep(1)
        return False
    return True


def _confirm_destructive_action(
    *,
    state: app_state.AppState,
    log_debug: Optional[Callable[[str], None]],
    prompt_lines: Iterable[str],
) -> bool:
    title = "DATA LOSS"
    prompt = " ".join(prompt_lines)
    selection = [app_state.CONFIRM_NO]  # Use list for mutability in closures

    def render():
        screens.render_confirmation_screen(
            title,
            [prompt],
            selected_index=selection[0],
            title_icon=ALERT_ICON,
        )

    render()
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B, gpio.PIN_C])

    def on_right():
        if selection[0] == app_state.CONFIRM_NO:
            selection[0] = app_state.CONFIRM_YES
            _log_debug(log_debug, "Destructive menu selection changed: YES")
            state.run_once = 0
            state.lcdstart = datetime.now()

    def on_left():
        if selection[0] == app_state.CONFIRM_YES:
            selection[0] = app_state.CONFIRM_NO
            _log_debug(log_debug, "Destructive menu selection changed: NO")
            state.run_once = 0
            state.lcdstart = datetime.now()

    result = gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel
            gpio.PIN_B: lambda: selection[0] == app_state.CONFIRM_YES,  # Confirm
            gpio.PIN_C: lambda: None,  # Ignored
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render,
    )

    return result if result is not None else False


def _render_disk_usage_page(
    device: dict,
    *,
    log_debug: Optional[Callable[[str], None]],
    page_index: int,
    total_pages: int,
) -> None:
    """Render a dedicated disk usage page with pie chart - focuses on space usage only."""
    context = display.get_display_context()
    draw = context.draw

    # Clear display
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    # Draw title with icon
    title = "DISK USAGE"
    title_font = context.fontcopy
    title_icon = DRIVES_ICON
    layout = display.draw_title_with_icon(
        title,
        title_font=title_font,
        icon=title_icon,
        extra_gap=2,
        left_margin=context.x - 11,
    )

    current_y = layout.content_top + 2
    items_font = context.fontdisks
    left_margin = context.x - 11

    # Pie chart configuration (drawn on right side, higher up to avoid page number)
    pie_size = 36  # diameter
    pie_x = context.width - pie_size - 6
    pie_y = layout.content_top  # Align with top of content area

    # Collect disk usage from all mounted partitions
    total_bytes = 0
    used_bytes = 0
    partition_count = 0

    for child in get_children(device):
        mountpoint = child.get("mountpoint")
        if not mountpoint:
            continue

        try:
            usage = os.statvfs(mountpoint)
            total = usage.f_blocks * usage.f_frsize
            free = usage.f_bavail * usage.f_frsize
            used = total - free

            total_bytes += total
            used_bytes += used
            partition_count += 1
        except (FileNotFoundError, PermissionError, OSError) as error:
            _log_debug(log_debug, f"Usage check failed for {mountpoint}: {error}")

    if partition_count == 0 or total_bytes == 0:
        # No mounted partitions or no usage data
        lines = ["No mounted", "partitions"]
        for line in lines:
            draw.text((left_margin, current_y), line, font=items_font, fill=255)
            current_y += display._get_line_height(items_font) + 2
    else:
        # Calculate percentages
        free_bytes = total_bytes - used_bytes
        used_percent = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0

        # Draw disk usage text (below device info, on left side)
        text_lines = [
            f"Used: {human_size(used_bytes)}",
            f"Free: {human_size(free_bytes)}",
            f"Total: {human_size(total_bytes)}",
            f"({used_percent:.1f}% used)",
        ]

        for line in text_lines:
            draw.text((left_margin, current_y), line, font=items_font, fill=255)
            current_y += display._get_line_height(items_font) + 2

        # Draw pie chart (on right side, top aligned with content)
        # Draw outer circle (border)
        draw.ellipse(
            [(pie_x, pie_y), (pie_x + pie_size, pie_y + pie_size)],
            outline=255,
            fill=0,
        )

        # Draw used portion as a filled pie slice
        if used_percent > 0:
            # PIL's pieslice uses angles: 0 degrees is 3 o'clock, 90 is 12 o'clock
            # We want to start at 12 o'clock (90 degrees) and go clockwise
            start_angle = 90
            end_angle = start_angle - (used_percent / 100 * 360)

            draw.pieslice(
                [(pie_x + 1, pie_y + 1), (pie_x + pie_size - 1, pie_y + pie_size - 1)],
                start=start_angle,
                end=end_angle,
                fill=255,
                outline=255,
            )

    # Draw page indicator (always show if multiple pages)
    if total_pages > 1:
        left_indicator = "<" if page_index > 0 else ""
        right_indicator = ">" if page_index < total_pages - 1 else ""
        indicator = f"{left_indicator}{page_index + 1}/{total_pages}{right_indicator}"
        indicator_bbox = draw.textbbox((0, 0), indicator, font=items_font)
        indicator_width = indicator_bbox[2] - indicator_bbox[0]
        indicator_height = indicator_bbox[3] - indicator_bbox[1]
        draw.text(
            (context.width - indicator_width - 2, context.height - indicator_height - 2),
            indicator,
            font=items_font,
            fill=255,
        )

    context.disp.display(context.image)


def _render_device_identity_page(
    device: dict,
    *,
    page_index: int,
    total_pages: int,
) -> None:
    """Render page 2: DEVICE INFO - name, model, serial."""
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    title_font = context.fontcopy
    items_font = context.fontdisks
    title_icon = DRIVES_ICON
    layout = display.draw_title_with_icon(
        "DEVICE INFO",
        title_font=title_font,
        icon=title_icon,
        extra_gap=2,
        left_margin=context.x - 11,
    )

    current_y = layout.content_top + 2
    left_margin = context.x - 11

    # Device name + size
    device_name = device.get("name") or ""
    size_bytes = device.get("size") or 0
    size_gb = size_bytes / (1024**3)
    draw.text((left_margin, current_y), f"{device_name.upper()} {size_gb:.1f}GB", font=items_font, fill=255)
    current_y += display._get_line_height(items_font) + 2

    # Vendor/model
    vendor = (device.get("vendor") or "").strip()
    model = (device.get("model") or "").strip()
    vendor_model = " ".join(part for part in [vendor, model] if part)
    if vendor_model:
        available_width = context.width - left_margin
        wrapped = display._wrap_lines_to_width([vendor_model], items_font, available_width)
        for line in wrapped:
            draw.text((left_margin, current_y), line, font=items_font, fill=255)
            current_y += display._get_line_height(items_font) + 2

    # Serial
    serial = (device.get("serial") or "").strip()
    if serial:
        available_width = context.width - left_margin
        wrapped = display._wrap_lines_to_width([f"SERIAL:{serial}"], items_font, available_width)
        for line in wrapped:
            draw.text((left_margin, current_y), line.upper(), font=items_font, fill=255)
            current_y += display._get_line_height(items_font) + 2

    # Page indicator
    _draw_page_indicator(context, page_index, total_pages, items_font)
    context.disp.display(context.image)


def _render_drive_metadata_page(
    device: dict,
    *,
    page_index: int,
    total_pages: int,
) -> None:
    """Render page 3: DRIVE INFO - type, table, uuid."""
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    title_font = context.fontcopy
    items_font = context.fontdisks
    title_icon = DRIVES_ICON
    layout = display.draw_title_with_icon(
        "DRIVE INFO",
        title_font=title_font,
        icon=title_icon,
        extra_gap=2,
        left_margin=context.x - 11,
    )

    current_y = layout.content_top + 2
    left_margin = context.x - 11

    # Type
    rota = device.get("rota")
    if rota is not None:
        device_type = "HDD" if rota == "1" or rota == 1 else "SSD"
        draw.text((left_margin, current_y), f"TYPE: {device_type}", font=items_font, fill=255)
        current_y += display._get_line_height(items_font) + 2

    # Table type
    pttype = (device.get("pttype") or "").strip()
    if pttype:
        draw.text((left_margin, current_y), f"TABLE: {pttype.upper()}", font=items_font, fill=255)
        current_y += display._get_line_height(items_font) + 2

    # UUID
    ptuuid = (device.get("ptuuid") or "").strip()
    if ptuuid:
        draw.text((left_margin, current_y), f"UUID: {ptuuid.upper()}", font=items_font, fill=255)
        current_y += display._get_line_height(items_font) + 2

    # Page indicator
    _draw_page_indicator(context, page_index, total_pages, items_font)
    context.disp.display(context.image)


def _render_partition_info_page(
    device: dict,
    *,
    log_debug: Optional[Callable[[str], None]],
    partition_page_index: int,
    page_index: int,
    total_pages: int,
) -> None:
    """Render pages 4+: PARTITION INFO - partition details (paginated)."""
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    title_font = context.fontcopy
    items_font = context.fontdisks
    title_icon = DRIVES_ICON
    layout = display.draw_title_with_icon(
        "PARTITION INFO",
        title_font=title_font,
        icon=title_icon,
        extra_gap=2,
        left_margin=context.x - 11,
    )

    current_y = layout.content_top + 2
    left_margin = context.x - 11
    available_height = context.height - current_y - 12  # Leave room for page indicator
    line_height = display._get_line_height(items_font)
    line_step = line_height + 2

    # Build partition lines
    partition_lines = []
    children = get_children(device)
    for child in children:
        name = child.get("name") or ""
        fstype = child.get("fstype") or "RAW"
        label = (child.get("label") or "").strip()
        mountpoint = child.get("mountpoint")

        label_suffix = f" ({label})" if label else ""
        partition_lines.append(f"{name.upper()} - {fstype.upper()}{label_suffix}")

        if mountpoint:
            partition_lines.append(f"MOUNT: {mountpoint.upper()}")
        else:
            partition_lines.append("MOUNT: NOT MOUNTED")

        partition_lines.append("")  # Spacing

    # Paginate partition lines
    lines_per_page = max(1, available_height // line_step)
    start = partition_page_index * lines_per_page
    end = start + lines_per_page
    page_lines = partition_lines[start:end]

    # Draw lines
    for line in page_lines:
        if line:  # Skip empty lines at the end
            draw.text((left_margin, current_y), line, font=items_font, fill=255)
        current_y += line_step

    # Page indicator
    _draw_page_indicator(context, page_index, total_pages, items_font)
    context.disp.display(context.image)


def _draw_page_indicator(context, page_index: int, total_pages: int, font) -> None:
    """Helper to draw page indicator in bottom right."""
    if total_pages > 1:
        left_indicator = "<" if page_index > 0 else ""
        right_indicator = ">" if page_index < total_pages - 1 else ""
        indicator = f"{left_indicator}{page_index + 1}/{total_pages}{right_indicator}"
        indicator_bbox = context.draw.textbbox((0, 0), indicator, font=font)
        indicator_width = indicator_bbox[2] - indicator_bbox[0]
        indicator_height = indicator_bbox[3] - indicator_bbox[1]
        context.draw.text(
            (context.width - indicator_width - 2, context.height - indicator_height - 2),
            indicator,
            font=font,
            fill=255,
        )


def _view_devices(
    *,
    log_debug: Optional[Callable[[str], None]],
    get_selected_usb_name: Callable[[], Optional[str]],
    page_index: int,
) -> tuple[int, int]:
    selected_name = get_selected_usb_name()
    if not selected_name:
        display.display_lines(["NO SELECTED USB"])
        return 1, 0
    devices_list = [device for device in list_usb_disks() if device.get("name") == selected_name]
    if not devices_list:
        display.display_lines(["NO SELECTED USB"])
        return 1, 0
    device = devices_list[0]

    # Calculate total pages:
    # Page 0: Disk usage
    # Page 1: Device info (identity)
    # Page 2: Drive info (metadata)
    # Pages 3+: Partition info (may be multiple pages)

    # Calculate partition info pages
    context = display.get_display_context()
    items_font = context.fontdisks
    title_font = context.fontcopy
    title_icon = DRIVES_ICON

    # Simulate partition info layout to calculate pages
    layout = display.draw_title_with_icon(
        "PARTITION INFO",
        title_font=title_font,
        icon=title_icon,
        extra_gap=2,
        left_margin=context.x - 11,
    )
    available_height = context.height - layout.content_top - 2 - 12
    line_step = display._get_line_height(items_font) + 2
    lines_per_page = max(1, available_height // line_step)

    # Count partition lines (3 lines per partition: name+fs, mount, blank)
    children = get_children(device)
    partition_line_count = len(children) * 3 if children else 0
    partition_pages = max(1, (partition_line_count + lines_per_page - 1) // lines_per_page) if children else 1

    total_pages = 3 + partition_pages  # disk usage + device info + drive info + partition pages

    # Route to appropriate renderer based on page index
    if page_index == 0:
        # Page 1: DISK USAGE
        _render_disk_usage_page(
            device, log_debug=log_debug, page_index=page_index, total_pages=total_pages
        )
    elif page_index == 1:
        # Page 2: DEVICE INFO
        _render_device_identity_page(
            device, page_index=page_index, total_pages=total_pages
        )
    elif page_index == 2:
        # Page 3: DRIVE INFO
        _render_drive_metadata_page(
            device, page_index=page_index, total_pages=total_pages
        )
    else:
        # Pages 4+: PARTITION INFO
        partition_page_index = page_index - 3
        _render_partition_info_page(
            device,
            log_debug=log_debug,
            partition_page_index=partition_page_index,
            page_index=page_index,
            total_pages=total_pages,
        )

    return total_pages, page_index


def format_drive(
    *,
    state: app_state.AppState,
    log_debug: Optional[Callable[[str], None]],
    get_selected_usb_name: Callable[[], Optional[str]],
) -> None:
    """Format a USB drive with user-selected filesystem."""
    from rpi_usb_cloner.storage.format import format_device
    from rpi_usb_cloner.ui import keyboard

    # Get target device
    repo_devices = _get_repo_device_names()
    target_devices = [
        device for device in list_usb_disks() if device.get("name") not in repo_devices
    ]
    if not target_devices:
        display.display_lines(["FORMAT", "No USB found"])
        time.sleep(1)
        return

    target_devices = sorted(target_devices, key=lambda d: d.get("name", ""))
    selected_name = get_selected_usb_name()
    target = None
    if selected_name:
        for device in target_devices:
            if device.get("name") == selected_name:
                target = device
                break
    if not target:
        target = target_devices[-1]

    target_name = target.get("name")
    target_size = target.get("size", 0)

    target_names = {device.get("name") for device in target_devices}
    status_line = (
        drives.get_active_drive_label(selected_name)
        if selected_name in target_names
        else None
    ) or format_device_label(target)

    # Select filesystem type (size-based default)
    filesystem = menus.select_filesystem_type(target_size, status_line=status_line)
    if not filesystem:
        return

    # Select format type (quick or full)
    format_type = menus.select_format_type(status_line=status_line)
    if not format_type:
        return

    # Warn about full format being slow
    if format_type == "full":
        prompt_lines = ["Full format is SLOW!", "Continue?"]
        if not _confirm_destructive_action(
            state=state,
            log_debug=log_debug,
            prompt_lines=prompt_lines,
        ):
            return

    # Optional: Get partition label
    # Show confirmation screen to decide whether to add label
    title = "ADD LABEL?"
    prompt = "Add partition label?"
    selection = [app_state.CONFIRM_NO]

    def render():
        screens.render_confirmation_screen(
            title,
            [prompt],
            selected_index=selection[0],
            title_icon=SPARKLES_ICON,
        )

    render()
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B])

    def on_right():
        if selection[0] == app_state.CONFIRM_NO:
            selection[0] = app_state.CONFIRM_YES
            _log_debug(log_debug, "Label selection changed: YES")

    def on_left():
        if selection[0] == app_state.CONFIRM_YES:
            selection[0] = app_state.CONFIRM_NO
            _log_debug(log_debug, "Label selection changed: NO")

    add_label = gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel - no label
            gpio.PIN_B: lambda: selection[0] == app_state.CONFIRM_YES,
            gpio.PIN_C: lambda: None,
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render,
    )

    # Get label if user chose to add one
    label = None
    if add_label:
        label = keyboard.prompt_text(
            title="LABEL",
            initial="",
            title_icon=SPARKLES_ICON,
        )
        if label == "":
            label = None

    # Final confirmation with details
    prompt_lines = [
        f"FORMAT {target_name}",
        f"TYPE {filesystem.upper()}",
        f"MODE {format_type.upper()}",
    ]
    if not _confirm_destructive_action(
        state=state,
        log_debug=log_debug,
        prompt_lines=prompt_lines,
    ):
        return

    # Check root permissions
    if not _ensure_root_for_erase():
        return

    # Threading pattern for progress screen
    done = threading.Event()
    result_holder: dict[str, bool] = {}
    error_holder: dict[str, Exception] = {}
    progress_lock = threading.Lock()
    progress_lines = ["Preparing..."]
    progress_ratio: Optional[float] = 0.0

    def update_progress(lines: list[str], ratio: Optional[float]) -> None:
        nonlocal progress_lines, progress_ratio
        clamped = None
        if ratio is not None:
            clamped = max(0.0, min(1.0, float(ratio)))
        with progress_lock:
            progress_lines = lines
            if clamped is not None:
                progress_ratio = clamped

    def current_progress() -> tuple[list[str], Optional[float]]:
        with progress_lock:
            return list(progress_lines), progress_ratio

    def worker() -> None:
        try:
            success = format_device(
                target, filesystem, format_type, label=label, progress_callback=update_progress
            )
            result_holder["result"] = success
        except Exception as exc:
            error_holder["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while not done.is_set():
        lines, ratio = current_progress()
        screens.render_progress_screen(
            "FORMAT",
            lines,
            progress_ratio=ratio,
            animate=False,
            title_icon=SPARKLES_ICON,
        )
        time.sleep(0.1)

    thread.join()

    # Display final result
    lines, ratio = current_progress()
    screens.render_progress_screen(
        "FORMAT",
        lines,
        progress_ratio=ratio,
        animate=False,
        title_icon=chr(58367),
    )

    if "error" in error_holder:
        error = error_holder["error"]
        _log_debug(log_debug, f"Format failed with exception: {error}")
        screens.render_status_template("FORMAT", "Failed", progress_line="Check logs.")
    elif not result_holder.get("result", False):
        _log_debug(log_debug, "Format failed")
        screens.render_status_template("FORMAT", "Failed", progress_line="Check logs.")
    else:
        screens.render_status_template("FORMAT", "Done", progress_line="Complete.")
    time.sleep(1)


def unmount_drive(
    *,
    state: app_state.AppState,
    log_debug: Optional[Callable[[str], None]],
    get_selected_usb_name: Callable[[], Optional[str]],
) -> None:
    """Unmount a USB drive and optionally power it off."""
    from rpi_usb_cloner.storage.devices import unmount_device_with_retry, power_off_device

    # Get target device
    selected_name = get_selected_usb_name()
    if not selected_name:
        display.display_lines(["NO DRIVE", "SELECTED"])
        time.sleep(1)
        return

    devices_list = [device for device in list_usb_disks() if device.get("name") == selected_name]
    if not devices_list:
        display.display_lines(["DRIVE", "NOT FOUND"])
        time.sleep(1)
        return

    device = devices_list[0]
    device_name = device.get("name")

    # Check for mounted partitions
    mountpoints = _collect_mountpoints(device)

    # Show mounted partitions info
    info_lines = [f"{device_name}"]
    if mountpoints:
        info_lines.append(f"{len(mountpoints)} mounted")
        for mp in list(mountpoints)[:3]:  # Show first 3
            info_lines.append(f"  {mp}")
    else:
        info_lines.append("Not mounted")

    # Display info screen
    screens.render_info_screen(
        "UNMOUNT",
        info_lines,
        page_index=0,
        title_font=display.get_display_context().fontcopy,
        title_icon=EJECT_ICON,
    )
    time.sleep(1)

    # Confirmation
    title = "UNMOUNT"
    prompt = f"Unmount {device_name}?"
    selection = [app_state.CONFIRM_YES]  # Default to YES

    def render():
        screens.render_confirmation_screen(
            title,
            [prompt],
            selected_index=selection[0],
            title_icon=EJECT_ICON,
        )

    render()
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B])

    def on_right():
        if selection[0] == app_state.CONFIRM_NO:
            selection[0] = app_state.CONFIRM_YES
            _log_debug(log_debug, "Unmount selection changed: YES")

    def on_left():
        if selection[0] == app_state.CONFIRM_YES:
            selection[0] = app_state.CONFIRM_NO
            _log_debug(log_debug, "Unmount selection changed: NO")

    confirmed = gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel
            gpio.PIN_B: lambda: selection[0] == app_state.CONFIRM_YES,
            gpio.PIN_C: lambda: None,
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render,
    )

    if not confirmed:
        return

    # Attempt to unmount
    display.display_lines(["UNMOUNTING..."])
    success, used_lazy = unmount_device_with_retry(device, log_debug=log_debug)

    if not success:
        display.display_lines(["UNMOUNT", "FAILED"])
        time.sleep(1)
        return

    # Show success message
    if used_lazy:
        display.display_lines(["UNMOUNTED", "(lazy)"])
    else:
        display.display_lines(["UNMOUNTED"])
    time.sleep(0.5)

    # Offer to power off drive
    title = "POWER OFF?"
    prompt = f"Power off {device_name}?"
    selection = [app_state.CONFIRM_YES]  # Default to YES

    def render_poweroff():
        screens.render_confirmation_screen(
            title,
            [prompt],
            selected_index=selection[0],
            title_icon=EJECT_ICON,
        )

    render_poweroff()
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B])

    power_off_confirmed = gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel
            gpio.PIN_B: lambda: selection[0] == app_state.CONFIRM_YES,
            gpio.PIN_C: lambda: None,
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render_poweroff,
    )

    if power_off_confirmed:
        display.display_lines(["POWERING OFF..."])
        if power_off_device(device, log_debug=log_debug):
            display.display_lines(["POWERED OFF"])
        else:
            display.display_lines(["POWER OFF", "FAILED"])
        time.sleep(1)


def _log_debug(log_debug: Optional[Callable[[str], None]], message: str) -> None:
    if log_debug:
        log_debug(message)
