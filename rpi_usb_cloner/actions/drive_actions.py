from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Callable, Iterable, Optional

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.storage import devices
from rpi_usb_cloner.storage.clone import clone_device, erase_device
from rpi_usb_cloner.storage.devices import (
    format_device_label,
    get_children,
    human_size,
    list_usb_disks,
)
from rpi_usb_cloner.ui import display, menus, screens


def copy_drive(
    *,
    state: app_state.AppState,
    clone_mode: str,
    log_debug: Optional[Callable[[str], None]],
    get_selected_usb_name: Callable[[], Optional[str]],
) -> None:
    source, target = _pick_source_target(get_selected_usb_name)
    if not source or not target:
        display.display_lines(["COPY", "Need 2 USBs"])
        time.sleep(1)
        return
    source_name = source.get("name")
    target_name = target.get("name")
    title = "COPY"
    prompt = f"Clone {source_name} to {target_name}?"
    confirm_selection = app_state.CONFIRM_NO
    screens.render_confirmation_screen(
        title,
        prompt,
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
                else:
                    context.disp.display(context.image)
                    time.sleep(0.01)
            current_L = gpio.read_button(gpio.PIN_L)
            if prev_states["L"] and not current_L:
                if confirm_selection == app_state.CONFIRM_YES:
                    confirm_selection = app_state.CONFIRM_NO
                    _log_debug(log_debug, "Copy menu selection changed: NO")
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                else:
                    context.disp.display(context.image)
                    time.sleep(0.01)
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
                prompt,
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
    target_devices = list_usb_disks()
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
    mode = menus.select_erase_mode()
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
    screens.render_status_template("ERASE", "Running...", progress_line="Starting...")
    if erase_device(target, mode):
        screens.render_status_template("ERASE", "Done", progress_line="Complete.")
    else:
        _log_debug(log_debug, "Erase failed")
        screens.render_status_template("ERASE", "Failed", progress_line="Check logs.")
    time.sleep(1)


def _pick_source_target(
    get_selected_usb_name: Callable[[], Optional[str]],
) -> tuple[Optional[dict], Optional[dict]]:
    devices_list = [device for device in list_usb_disks() if not devices.is_root_device(device)]
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
    title = "⚠ DATA LOST"
    prompt = " ".join(prompt_lines)
    confirm_selection = app_state.CONFIRM_NO
    screens.render_confirmation_screen(
        title,
        prompt,
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
    while True:
        current_R = gpio.read_button(gpio.PIN_R)
        if prev_states["R"] and not current_R:
            if confirm_selection == app_state.CONFIRM_NO:
                confirm_selection = app_state.CONFIRM_YES
                _log_debug(log_debug, "Destructive menu selection changed: YES")
                state.run_once = 0
                state.lcdstart = datetime.now()
        current_L = gpio.read_button(gpio.PIN_L)
        if prev_states["L"] and not current_L:
            if confirm_selection == app_state.CONFIRM_YES:
                confirm_selection = app_state.CONFIRM_NO
                _log_debug(log_debug, "Destructive menu selection changed: NO")
                state.run_once = 0
                state.lcdstart = datetime.now()
        current_A = gpio.read_button(gpio.PIN_A)
        if prev_states["A"] and not current_A:
            return False
        current_B = gpio.read_button(gpio.PIN_B)
        if prev_states["B"] and not current_B:
            return confirm_selection == app_state.CONFIRM_YES
        current_C = gpio.read_button(gpio.PIN_C)
        if prev_states["C"] and not current_C:
            _log_debug(log_debug, "Destructive menu: Button C pressed (ignored)")
        prev_states["R"] = current_R
        prev_states["L"] = current_L
        prev_states["A"] = current_A
        prev_states["B"] = current_B
        prev_states["C"] = current_C
        screens.render_confirmation_screen(
            title,
            prompt,
            selected_index=confirm_selection,
        )


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

        usage_label = "?"
        try:
            usage = os.statvfs(mountpoint)
            total = usage.f_blocks * usage.f_frsize
            free = usage.f_bavail * usage.f_frsize
            used = total - free
            usage_label = f"{human_size(used)}/{human_size(total)}"
        except (FileNotFoundError, PermissionError, OSError) as error:
            _log_debug(log_debug, f"Usage check failed for {mountpoint}: {error}")
            usage_label = "usage?"

        if not append_line(f"use:{usage_label}"):
            break

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
    lines = _build_device_info_lines(device, log_debug=log_debug)
    return screens.render_info_screen(
        "DRIVE INFO",
        lines,
        page_index=page_index,
        title_font=display.get_display_context().fontcopy,
    )


def _log_debug(log_debug: Optional[Callable[[str], None]], message: str) -> None:
    if log_debug:
        log_debug(message)
