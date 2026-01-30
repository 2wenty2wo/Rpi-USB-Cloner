"""Format drive actions.

Handles USB drive formatting operations.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from loguru import logger

from rpi_usb_cloner.services import drives
from rpi_usb_cloner.storage.devices import (
    format_device_label,
    get_human_device_label,
    list_usb_disks,
)
from rpi_usb_cloner.ui import display, menus, screens
from rpi_usb_cloner.ui.icons import SPARKLES_ICON

from ._utils import (
    build_status_line,
    confirm_destructive_action,
    ensure_root,
    handle_screenshot,
    select_target_device,
)




def format_drive(
    *,
    state: app_state.AppState,
    get_selected_usb_name: Callable[[], str | None],
) -> None:
    """Format a USB drive with user-selected filesystem."""
    from rpi_usb_cloner.storage.format import format_device

    # Get target device
    repo_devices = drives._get_repo_device_names()
    target_devices = [
        device for device in list_usb_disks() if device.get("name") not in repo_devices
    ]

    if not target_devices:
        display.display_lines(["FORMAT", "No USB found"])
        time.sleep(1)
        return

    selected_name = get_selected_usb_name()
    target_devices, target = select_target_device(target_devices, selected_name)

    if target is None:
        display.display_lines(["FORMAT", "No USB found"])
        time.sleep(1)
        return

    target_name = target.get("name")
    target_size = target.get("size", 0)
    status_line = build_status_line(target_devices, target, selected_name)

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
        if not confirm_destructive_action(state=state, prompt_lines=prompt_lines):
            return

    # Optional: Get partition label
    label = _prompt_for_label(state)

    # Final confirmation with details
    target_label = get_human_device_label(target)
    prompt_lines = [
        f"FORMAT {target_label}",
        f"{filesystem.upper()} {format_type.upper()}",
    ]
    if not confirm_destructive_action(state=state, prompt_lines=prompt_lines):
        return

    if not ensure_root():
        return

    # Threading pattern for progress screen
    done = threading.Event()
    result_holder: dict[str, bool] = {}
    error_holder: dict[str, Exception] = {}
    progress_lock = threading.Lock()
    progress_lines = ["Preparing..."]
    progress_ratio: float | None = 0.0

    def update_progress(lines: list[str], ratio: float | None) -> None:
        nonlocal progress_lines, progress_ratio
        clamped = None
        if ratio is not None:
            clamped = max(0.0, min(1.0, float(ratio)))
        with progress_lock:
            progress_lines = lines
            if clamped is not None:
                progress_ratio = clamped

    def current_progress() -> tuple[list[str], float | None]:
        with progress_lock:
            return list(progress_lines), progress_ratio

    def worker() -> None:
        try:
            success = format_device(
                target,
                filesystem,
                format_type,
                label=label,
                progress_callback=update_progress,
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
        logger.error(
            "Format failed with exception",
            device=target_name,
            filesystem=filesystem,
            mode=format_type,
            label=label,
            error=str(error),
        )
        screens.render_status_template("FORMAT", "Failed", progress_line="Check logs.")
    elif not result_holder.get("result", False):
        logger.error(
            "Format failed",
            device=target_name,
            filesystem=filesystem,
            mode=format_type,
            label=label,
        )
        screens.render_status_template("FORMAT", "Failed", progress_line="Check logs.")
    else:
        formatted_label = format_device_label(target)
        logger.debug(
            "Format completed (action) for {}",
            formatted_label,
            device=target_name,
            filesystem=filesystem,
            mode=format_type,
            label=label,
        )
        screens.render_status_template("FORMAT", "Done", progress_line="Complete.")

    time.sleep(1)


def _prompt_for_label(state: app_state.AppState) -> str | None:
    """Prompt user to optionally add a partition label."""
    from rpi_usb_cloner.ui import keyboard

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
    menus.wait_for_buttons_release(
        [gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B, gpio.PIN_C]
    )

    def on_right():
        if selection[0] == app_state.CONFIRM_NO:
            selection[0] = app_state.CONFIRM_YES
            logger.debug("Format label selection changed: YES")

    def on_left():
        if selection[0] == app_state.CONFIRM_YES:
            selection[0] = app_state.CONFIRM_NO
            logger.debug("Format label selection changed: NO")

    add_label = gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel - no label
            gpio.PIN_B: lambda: selection[0] == app_state.CONFIRM_YES,
            gpio.PIN_C: lambda: handle_screenshot() or None,
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render,
    )

    if not add_label:
        return None

    label = keyboard.prompt_text(
        title="LABEL",
        initial="",
        title_icon=SPARKLES_ICON,
    )

    return label if label else None
