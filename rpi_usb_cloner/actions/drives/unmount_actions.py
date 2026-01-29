"""Unmount drive actions.

Handles USB drive unmounting and power-off operations.
"""

from __future__ import annotations

import time
from typing import Callable

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.logging import LoggerFactory
from rpi_usb_cloner.storage.devices import list_usb_disks
from rpi_usb_cloner.ui import display, menus, screens
from rpi_usb_cloner.ui.icons import EJECT_ICON

from ._utils import collect_mountpoints, handle_screenshot


log_menu = LoggerFactory.for_menu()
log_system = LoggerFactory.for_system()


def unmount_drive(
    *,
    state: app_state.AppState,
    get_selected_usb_name: Callable[[], str | None],
) -> None:
    """Unmount a USB drive and optionally power it off."""
    from rpi_usb_cloner.storage.devices import (
        power_off_device,
        unmount_device_with_retry,
    )

    selected_name = get_selected_usb_name()
    if not selected_name:
        display.display_lines(["NO DRIVE", "SELECTED"])
        time.sleep(1)
        return

    devices_list = [
        device for device in list_usb_disks() if device.get("name") == selected_name
    ]
    if not devices_list:
        display.display_lines(["DRIVE", "NOT FOUND"])
        time.sleep(1)
        return

    device = devices_list[0]
    device_name = device.get("name")

    # Check for mounted partitions
    mountpoints = collect_mountpoints(device)

    # Show mounted partitions info
    info_lines = [f"{device_name}"]
    if mountpoints:
        info_lines.append(f"{len(mountpoints)} mounted")
        for mp in list(mountpoints)[:3]:  # Show first 3
            info_lines.append(f"  {mp}")
    else:
        info_lines.append("Not mounted")

    screens.render_info_screen(
        "UNMOUNT",
        info_lines,
        page_index=0,
        title_font=display.get_display_context().fontcopy,
        title_icon=EJECT_ICON,
    )
    time.sleep(1)

    # Confirmation
    if not _confirm_unmount(state, device_name):
        return

    # Attempt to unmount
    log_system.info("Attempting to unmount device", device=device_name)
    display.display_lines(["UNMOUNTING..."])
    success, used_lazy = unmount_device_with_retry(device)

    if not success:
        log_system.error("Unmount failed", device=device_name)
        display.display_lines(["UNMOUNT", "FAILED"])
        time.sleep(1)
        return

    # Show success message
    if used_lazy:
        log_system.info("Device unmounted (lazy)", device=device_name)
        display.display_lines(["UNMOUNTED", "(lazy)"])
    else:
        log_system.info("Device unmounted successfully", device=device_name)
        display.display_lines(["UNMOUNTED"])
    time.sleep(0.5)

    # Offer to power off drive
    if _confirm_power_off(state, device_name):
        log_system.info("Attempting to power off device", device=device_name)
        display.display_lines(["POWERING OFF..."])
        if power_off_device(device):
            log_system.info("Device powered off successfully", device=device_name)
            display.display_lines(["POWERED OFF"])
        else:
            log_system.error("Power off failed", device=device_name)
            display.display_lines(["POWER OFF", "FAILED"])
        time.sleep(1)


def _confirm_unmount(state: app_state.AppState, device_name: str) -> bool:
    """Show unmount confirmation dialog."""
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
    menus.wait_for_buttons_release(
        [gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B, gpio.PIN_C]
    )

    def on_right():
        if selection[0] == app_state.CONFIRM_NO:
            selection[0] = app_state.CONFIRM_YES
            log_menu.debug("Unmount selection changed: YES")

    def on_left():
        if selection[0] == app_state.CONFIRM_YES:
            selection[0] = app_state.CONFIRM_NO
            log_menu.debug("Unmount selection changed: NO")

    confirmed = gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel
            gpio.PIN_B: lambda: selection[0] == app_state.CONFIRM_YES,
            gpio.PIN_C: lambda: handle_screenshot() or None,
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render,
    )

    return confirmed if confirmed is not None else False


def _confirm_power_off(state: app_state.AppState, device_name: str) -> bool:
    """Show power-off confirmation dialog."""
    title = "POWER OFF?"
    prompt = f"Power off {device_name}?"
    selection = [app_state.CONFIRM_YES]  # Default to YES

    def render():
        screens.render_confirmation_screen(
            title,
            [prompt],
            selected_index=selection[0],
            title_icon=EJECT_ICON,
        )

    render()
    menus.wait_for_buttons_release(
        [gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B, gpio.PIN_C]
    )

    def on_right():
        if selection[0] == app_state.CONFIRM_NO:
            selection[0] = app_state.CONFIRM_YES
            log_menu.debug("Power off selection changed: YES")

    def on_left():
        if selection[0] == app_state.CONFIRM_YES:
            selection[0] = app_state.CONFIRM_NO
            log_menu.debug("Power off selection changed: NO")

    confirmed = gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel
            gpio.PIN_B: lambda: selection[0] == app_state.CONFIRM_YES,
            gpio.PIN_C: lambda: handle_screenshot() or None,
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render,
    )

    return confirmed if confirmed is not None else False
