"""Shared utilities for drive actions.

Common functions used across multiple drive action modules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Iterable

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.config import settings
from rpi_usb_cloner.hardware import gpio
from loguru import logger

from rpi_usb_cloner.services import drives
from rpi_usb_cloner.storage.devices import format_device_label, get_children
from rpi_usb_cloner.ui import display, menus, screens
from rpi_usb_cloner.ui.icons import ALERT_ICON




def apply_confirmation_selection(selection: int, direction: str) -> int:
    """Update confirmation selection based on direction."""
    if direction == "right" and selection == app_state.CONFIRM_NO:
        return app_state.CONFIRM_YES
    if direction == "left" and selection == app_state.CONFIRM_YES:
        return app_state.CONFIRM_NO
    return selection


def handle_screenshot() -> bool:
    """Capture screenshot if enabled. Returns True if captured."""
    if not settings.get_bool("screenshots_enabled", default=False):
        return False
    screenshot_path = display.capture_screenshot()
    if screenshot_path:
        screens.render_status_template("SCREENSHOT", f"Saved to {screenshot_path.name}")
        import time

        time.sleep(1.5)
        return True
    return False


def confirm_destructive_action(
    *,
    state: app_state.AppState,
    prompt_lines: Iterable[str],
    poll_button_events: Callable[..., bool | None] | None = None,
    wait_for_buttons_release: Callable[..., None] | None = None,
    render_confirmation_screen: Callable[..., None] | None = None,
    handle_screenshot_func: Callable[[], bool] | None = None,
    poll_interval: float | None = None,
) -> bool:
    """Show destructive action confirmation dialog.

    Returns True if user confirms, False otherwise.
    """
    title = "DATA LOSS"
    prompt = " ".join(prompt_lines)
    selection = [app_state.CONFIRM_NO]

    if poll_button_events is None:
        poll_button_events = gpio.poll_button_events
    if wait_for_buttons_release is None:
        wait_for_buttons_release = menus.wait_for_buttons_release
    if render_confirmation_screen is None:
        render_confirmation_screen = screens.render_confirmation_screen
    if poll_interval is None:
        poll_interval = menus.BUTTON_POLL_DELAY
    if handle_screenshot_func is None:
        handle_screenshot_func = handle_screenshot

    def render():
        render_confirmation_screen(
            title,
            [prompt],
            selected_index=selection[0],
            title_icon=ALERT_ICON,
        )

    render()
    wait_for_buttons_release(
        [gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B, gpio.PIN_C]
    )

    def on_right():
        updated = apply_confirmation_selection(selection[0], "right")
        if updated != selection[0]:
            selection[0] = updated
            logger.debug("Destructive action confirmation changed: YES")
            state.run_once = 0
            state.lcdstart = datetime.now()

    def on_left():
        updated = apply_confirmation_selection(selection[0], "left")
        if updated != selection[0]:
            selection[0] = updated
            logger.debug("Destructive action confirmation changed: NO")
            state.run_once = 0
            state.lcdstart = datetime.now()

    result = poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel
            gpio.PIN_B: lambda: selection[0] == app_state.CONFIRM_YES,  # Confirm
            gpio.PIN_C: lambda: (handle_screenshot_func(), None)[1],
        },
        poll_interval=poll_interval,
        loop_callback=render,
    )

    return result if result is not None else False


def select_target_device(
    target_devices: Iterable[dict],
    selected_name: str | None,
) -> tuple[list[dict], dict | None]:
    """Select target device from available devices.

    Returns (sorted_devices, selected_device).
    """
    sorted_devices = sorted(target_devices, key=lambda d: d.get("name", ""))
    if not sorted_devices:
        return sorted_devices, None

    target = None
    if selected_name:
        for device in sorted_devices:
            if device.get("name") == selected_name:
                target = device
                break

    if not target:
        target = sorted_devices[-1]

    return sorted_devices, target


def build_status_line(
    target_devices: Iterable[dict],
    target: dict,
    selected_name: str | None,
) -> str:
    """Build status line for device selection screens."""
    target_names = {device.get("name") for device in target_devices}
    return (
        drives.get_active_drive_label(selected_name)
        if selected_name in target_names
        else None
    ) or format_device_label(target)


def collect_mountpoints(device: dict) -> set[str]:
    """Collect all mountpoints for a device and its partitions."""
    mountpoints: set[str] = set()
    stack = [device]
    while stack:
        current = stack.pop()
        mountpoint = current.get("mountpoint")
        if mountpoint:
            mountpoints.add(mountpoint)
        stack.extend(get_children(current))
    return mountpoints


def ensure_root() -> bool:
    """Check if running as root. Shows error if not."""
    import os
    import time

    if os.geteuid() != 0:
        display.display_lines(["Run as root"])
        time.sleep(1)
        return False
    return True
