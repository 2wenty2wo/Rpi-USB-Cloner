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
            title_icon=chr(57581),  # drives icon
            message_icon=chr(57639),  # octagon-alert icon
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
            title_icon=chr(57639),
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
        title_icon=chr(57639),
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
            title_icon=chr(57639),
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
) -> tuple[int, int]:
    """Render a dedicated disk usage page with pie chart."""
    context = display.get_display_context()
    draw = context.draw

    # Clear display
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    # Draw title with icon
    title = "DISK USAGE"
    title_font = context.fontcopy
    title_icon = chr(57581)  # drives icon
    layout = display.draw_title_with_icon(
        title,
        title_font=title_font,
        icon=title_icon,
        extra_gap=2,
        left_margin=context.x - 11,
    )

    current_y = layout.content_top + 2

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
            draw.text((context.x - 11, current_y), line, font=context.fontdisks, fill=255)
            current_y += 10
        context.disp.display(context.image)
        return 1, 0

    # Calculate percentages
    free_bytes = total_bytes - used_bytes
    used_percent = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0
    free_percent = 100 - used_percent

    # Draw text information
    text_lines = [
        f"Used: {human_size(used_bytes)}",
        f"Free: {human_size(free_bytes)}",
        f"Total: {human_size(total_bytes)}",
        f"({used_percent:.1f}% used)",
    ]

    for line in text_lines:
        draw.text((context.x - 11, current_y), line, font=context.fontdisks, fill=255)
        current_y += 10

    # Draw pie chart
    pie_size = 32  # diameter
    pie_x = context.width - pie_size - 8
    pie_y = layout.content_top + 2

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

    context.disp.display(context.image)
    return 1, 0


def _build_device_info_lines(
    device: dict,
    *,
    log_debug: Optional[Callable[[str], None]],
    max_lines: Optional[int] = None,
) -> list[str]:
    lines = []
    header = format_device_label(device)
    vendor = (device.get("vendor") or "").strip()
    model = (device.get("model") or "").strip()
    vendor_model = " ".join(part for part in [vendor, model] if part)
    if vendor_model:
        header = f"{header} {vendor_model}"
    lines.append(header.strip())

    def append_line(line: str) -> bool:
        if max_lines is not None and len(lines) >= max_lines:
            return False
        lines.append(line)
        return True

    # Add device-level information
    serial = (device.get("serial") or "").strip()
    if serial:
        if not append_line(f"serial: {serial}"):
            return lines

    # Determine device type (SSD/HDD)
    rota = device.get("rota")
    if rota is not None:
        device_type = "HDD" if rota == "1" or rota == 1 else "SSD"
        if not append_line(f"type: {device_type}"):
            return lines

    # Add partition table information
    pttype = (device.get("pttype") or "").strip()
    if pttype:
        if not append_line(f"table: {pttype}"):
            return lines

    ptuuid = (device.get("ptuuid") or "").strip()
    if ptuuid:
        # Truncate UUID if too long
        display_uuid = ptuuid if len(ptuuid) <= 20 else f"{ptuuid[:17]}..."
        if not append_line(f"uuid: {display_uuid}"):
            return lines

    # Add partition information
    for child in get_children(device):
        if max_lines is not None and len(lines) >= max_lines:
            break
        name = child.get("name") or ""
        fstype = child.get("fstype") or "raw"
        label = (child.get("label") or "").strip()
        mountpoint = child.get("mountpoint")
        label_suffix = f" {label}" if label else ""
        if not append_line(f"{name} {fstype}{label_suffix}".strip()):
            break
        if max_lines is not None and len(lines) >= max_lines:
            break
        if not mountpoint:
            append_line("mnt: not mounted")
            continue

        if not append_line(f"mnt:{mountpoint}"):
            break

        # Disk usage is now shown on its own dedicated page

        try:
            entries = sorted(os.listdir(mountpoint))[:3]
            if entries:
                if not append_line(f"files:{','.join(entries)}"):
                    break
        except (FileNotFoundError, PermissionError, OSError) as error:
            _log_debug(log_debug, f"Listdir failed for {mountpoint}: {error}")
            append_line("files?")

    if max_lines is not None and len(lines) > max_lines:
        return lines[:max_lines]
    return lines


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

    # First page is the disk usage page with pie chart
    # Remaining pages are the text-based info pages
    if page_index == 0:
        # Show disk usage page
        _render_disk_usage_page(device, log_debug=log_debug)
        # Get total number of text info pages
        lines = _build_device_info_lines(device, log_debug=log_debug)
        text_total_pages, _ = screens.render_info_screen(
            "DRIVE INFO",
            lines,
            page_index=0,
            title_font=display.get_display_context().fontcopy,
            title_icon=chr(57581),  # drives icon
        )
        # Render the disk usage page again (since render_info_screen overwrote it)
        _render_disk_usage_page(device, log_debug=log_debug)
        total_pages = 1 + text_total_pages  # 1 usage page + N text pages
        return total_pages, 0
    else:
        # Show text info pages (offset by 1 since page 0 is disk usage)
        lines = _build_device_info_lines(device, log_debug=log_debug)
        text_total_pages, text_page_index = screens.render_info_screen(
            "DRIVE INFO",
            lines,
            page_index=page_index - 1,  # Adjust for disk usage page offset
            title_font=display.get_display_context().fontcopy,
            title_icon=chr(57581),  # drives icon
        )
        total_pages = 1 + text_total_pages  # 1 usage page + N text pages
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
            title_icon=chr(58367),  # sparkles icon
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
            title_icon=chr(58367),  # sparkles icon
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
            title_icon=chr(58367),  # sparkles icon
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
        title_icon=chr(57444),  # eject icon
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
            title_icon=chr(57444),  # eject icon
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
            title_icon=chr(57444),  # eject icon
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
