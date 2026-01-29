"""Erase drive actions.

Handles secure erasure of USB drives.
"""

from __future__ import annotations

import threading
import time
from typing import Callable
from uuid import uuid4

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.logging import LoggerFactory, get_logger
from rpi_usb_cloner.services import drives
from rpi_usb_cloner.storage.clone import erase_device
from rpi_usb_cloner.storage.devices import (
    get_human_device_label,
    list_usb_disks,
)
from rpi_usb_cloner.ui import display, menus, screens
from rpi_usb_cloner.ui.icons import ALERT_ICON

from ._utils import (
    build_status_line,
    confirm_destructive_action,
    ensure_root,
    select_target_device,
)


log_operation = LoggerFactory.for_clone()


def erase_drive(
    *,
    state: app_state.AppState,
    get_selected_usb_name: Callable[[], str | None],
) -> None:
    """Erase a USB drive with selected mode (quick/full)."""
    repo_devices = drives._get_repo_device_names()
    target_devices = [
        device for device in list_usb_disks() if device.get("name") not in repo_devices
    ]

    if not target_devices:
        display.display_lines(["ERASE", "No USB found"])
        time.sleep(1)
        return

    selected_name = get_selected_usb_name()
    target_devices, target = select_target_device(target_devices, selected_name)

    if target is None:
        display.display_lines(["ERASE", "No USB found"])
        time.sleep(1)
        return

    target_name = target.get("name")
    status_line = build_status_line(target_devices, target, selected_name)

    mode = menus.select_erase_mode(status_line=status_line)
    if not mode:
        return

    target_label = get_human_device_label(target)
    prompt_lines = [f"ERASE {target_label}", f"MODE {mode.upper()}"]

    if not confirm_destructive_action(state=state, prompt_lines=prompt_lines):
        return

    if not ensure_root():
        return

    # Threading pattern for progress screen
    job_id = f"erase-{uuid4().hex}"
    op_log = get_logger(job_id=job_id, tags=["erase"], source="erase")
    op_log.info(f"Starting erase: {target_name} (mode {mode})")

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
        log_operation.error(
            "Erase failed with exception",
            device=target_name,
            mode=mode,
            error=str(error),
        )
        screens.render_status_template("ERASE", "Failed", progress_line="Check logs.")
    elif not result_holder.get("result", False):
        log_operation.error("Erase failed", device=target_name, mode=mode)
        screens.render_status_template("ERASE", "Failed", progress_line="Check logs.")
    else:
        log_operation.info(
            "Erase completed successfully", device=target_name, mode=mode
        )
        screens.render_status_template("ERASE", "Done", progress_line="Complete.")

    time.sleep(1)
