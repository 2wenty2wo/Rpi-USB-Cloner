"""Clone/copy drive actions.

Handles drive-to-drive copying operations.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Callable
from uuid import UUID, uuid4

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.domain import CloneJob, CloneMode, Drive
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.logging import LoggerFactory, get_logger
from rpi_usb_cloner.services import drives
from rpi_usb_cloner.storage import devices
from rpi_usb_cloner.storage.clone import clone_device_v2
from rpi_usb_cloner.storage.devices import (
    get_human_device_label,
    list_usb_disks,
)
from rpi_usb_cloner.ui import menus, screens
from rpi_usb_cloner.ui.icons import ALERT_ICON, COPY_DRIVE_ICON, DRIVES_ICON

from ._utils import apply_confirmation_selection, handle_screenshot


log_menu = LoggerFactory.for_menu()
log_operation = LoggerFactory.for_clone()


def prepare_copy_operation(
    get_selected_usb_name: Callable[[], str | None],
    *,
    list_usb_disks_func: Callable[[], list[dict]] | None = None,
    is_root_device_func: Callable[[dict], bool] | None = None,
    repo_device_names_func: Callable[[], set[str]] | None = None,
) -> tuple[dict | None, dict | None]:
    """Prepare source and target devices for copy operation.

    Returns (source, target) tuple, or (None, None) if insufficient devices.
    """
    if list_usb_disks_func is None:
        list_usb_disks_func = list_usb_disks
    if is_root_device_func is None:
        is_root_device_func = devices.is_root_device
    if repo_device_names_func is None:
        repo_device_names_func = drives._get_repo_device_names

    return _pick_source_target(
        get_selected_usb_name,
        list_usb_disks_func=list_usb_disks_func,
        is_root_device_func=is_root_device_func,
        repo_device_names_func=repo_device_names_func,
    )


def execute_copy_operation(
    source: dict,
    target: dict,
    clone_mode: str,
    *,
    select_clone_mode: Callable[[str], str | None],
    execute_clone_job: Callable[..., tuple[bool, str]],
    job_id_factory: Callable[[], UUID] = uuid4,
) -> tuple[bool, str]:
    """Execute copy operation with mode selection.

    Returns (success, status_line) tuple.
    """
    mode = select_clone_mode(clone_mode)
    if not mode:
        return False, "Cancelled"
    job_id = f"clone-{job_id_factory().hex}"
    return execute_clone_job(source, target, mode, job_id=job_id)


def copy_drive(
    *,
    state: app_state.AppState,
    clone_mode: str,
    get_selected_usb_name: Callable[[], str | None],
    confirm_prompt: Callable[..., bool] | None = None,
    select_clone_mode: Callable[[str], str | None] = None,
    execute_clone_job: Callable[..., tuple[bool, str]] | None = None,
) -> None:
    """Copy one drive to another."""
    if confirm_prompt is None:
        confirm_prompt = _confirm_copy_prompt
    if select_clone_mode is None:
        select_clone_mode = menus.select_clone_mode
    if execute_clone_job is None:
        execute_clone_job = _execute_clone_job

    source, target = prepare_copy_operation(get_selected_usb_name)
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

    source_label = get_human_device_label(source)
    target_label = get_human_device_label(target)
    title = "COPY"
    prompt = f"{source_label} → {target_label}"

    confirmed = confirm_prompt(state=state, title=title, prompt=prompt)
    if not confirmed:
        return

    screens.render_status_template(
        "COPY",
        "Running...",
        progress_line="Starting...",
        title_icon=COPY_DRIVE_ICON,
    )

    success, status_line = execute_copy_operation(
        source,
        target,
        clone_mode,
        select_clone_mode=select_clone_mode,
        execute_clone_job=execute_clone_job,
    )

    if status_line == "Cancelled":
        return

    screens.render_status_template(
        "COPY",
        "Done" if success else "Failed",
        progress_line=status_line,
        title_icon=COPY_DRIVE_ICON,
    )
    time.sleep(1)


def _confirm_copy_prompt(
    *,
    state: app_state.AppState,
    title: str,
    prompt: str,
    poll_button_events: Callable[..., bool | None] | None = None,
    wait_for_buttons_release: Callable[..., None] | None = None,
    render_confirmation_screen: Callable[..., None] | None = None,
    handle_screenshot_func: Callable[[], bool] | None = None,
    poll_interval: float | None = None,
) -> bool:
    """Show copy confirmation prompt."""
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
            title_icon=COPY_DRIVE_ICON,
        )

    render()
    wait_for_buttons_release(
        [gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B, gpio.PIN_C]
    )

    def on_right():
        updated = apply_confirmation_selection(selection[0], "right")
        if updated != selection[0]:
            selection[0] = updated
            log_menu.debug("Copy menu selection changed: YES")
            state.run_once = 0
            state.lcdstart = datetime.now()

    def on_left():
        updated = apply_confirmation_selection(selection[0], "left")
        if updated != selection[0]:
            selection[0] = updated
            log_menu.debug("Copy menu selection changed: NO")
            state.run_once = 0
            state.lcdstart = datetime.now()

    result = poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel
            gpio.PIN_B: lambda: selection[0] == app_state.CONFIRM_YES,
            gpio.PIN_C: lambda: (handle_screenshot_func(), None)[1],
        },
        poll_interval=poll_interval,
        loop_callback=render,
    )

    return result if result is not None else False


def _prepare_clone_job(
    source: dict,
    target: dict,
    mode: str,
    job_id: str,
) -> CloneJob:
    """Build a CloneJob from device metadata."""
    source_drive = Drive.from_lsblk_dict(source)
    target_drive = Drive.from_lsblk_dict(target)
    clone_mode_enum = CloneMode(mode)
    return CloneJob(source_drive, target_drive, clone_mode_enum, job_id)


def _execute_clone_job(
    source: dict,
    target: dict,
    mode: str,
    *,
    job_id: str,
) -> tuple[bool, str]:
    """Run clone operation and return (success, status_line)."""
    source_name = source.get("name")
    target_name = target.get("name")
    op_log = get_logger(job_id=job_id, tags=["clone"], source="clone")
    op_log.info(f"Starting clone: {source_name} -> {target_name} (mode {mode})")

    try:
        job = _prepare_clone_job(source, target, mode, job_id)
    except (KeyError, ValueError) as error:
        log_operation.error(
            "Copy failed",
            source=source_name,
            target=target_name,
            error=str(error),
        )
        return False, "Invalid params"

    # CloneJob.validate() is called inside clone_device_v2
    # This automatically prevents source==destination bug!
    if clone_device_v2(job):
        return True, "Complete."

    log_operation.error(
        "Copy failed",
        source=source_name,
        target=target_name,
        mode=mode,
    )
    return False, "Check logs."


def _pick_source_target(
    get_selected_usb_name: Callable[[], str | None],
    *,
    list_usb_disks_func: Callable[[], list[dict]] | None = None,
    is_root_device_func: Callable[[dict], bool] | None = None,
    repo_device_names_func: Callable[[], set[str]] | None = None,
) -> tuple[dict | None, dict | None]:
    """Pick source and target devices for copy operation."""
    if list_usb_disks_func is None:
        list_usb_disks_func = list_usb_disks
    if is_root_device_func is None:
        is_root_device_func = devices.is_root_device
    if repo_device_names_func is None:
        repo_device_names_func = drives._get_repo_device_names

    repo_devices = repo_device_names_func()
    devices_list = [
        device
        for device in list_usb_disks_func()
        if not is_root_device_func(device) and device.get("name") not in repo_devices
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
        remaining = [
            device for device in devices_list if device.get("name") != selected_name
        ]
        if not remaining:
            return None, None
        source = selected
        target = remaining[0]
    else:
        source = devices_list[0]
        target = devices_list[1]

    return source, target
