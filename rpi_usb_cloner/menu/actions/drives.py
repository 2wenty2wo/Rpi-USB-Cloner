"""Drive-related menu actions."""

from __future__ import annotations

import time

from rpi_usb_cloner.actions import drive_actions
from rpi_usb_cloner.ui import screens
from . import get_action_context


def _ensure_drive_selected(title: str, title_icon: str) -> bool:
    context = get_action_context()
    if context.app_context.active_drive:
        return True
    screens.render_error_screen(
        title,
        message="No drive selected",
        title_icon=title_icon,
        message_icon=chr(57639),
        message_icon_size=24,
    )
    time.sleep(1)
    return False


def _run_operation(action, *, allow_back_interrupt: bool = False) -> None:
    context = get_action_context()
    context.app_context.operation_active = True
    context.app_context.allow_back_interrupt = allow_back_interrupt
    try:
        action()
    finally:
        context.app_context.operation_active = False
        context.app_context.allow_back_interrupt = False


def copy_drive() -> None:
    context = get_action_context()
    if not _ensure_drive_selected("COPY DRIVE", chr(57581)):
        return
    _run_operation(
        lambda: drive_actions.copy_drive(
            state=context.state,
            clone_mode=context.clone_mode,
            log_debug=context.log_debug,
            get_selected_usb_name=context.get_selected_usb_name,
        )
    )


def drive_info() -> None:
    context = get_action_context()
    if not _ensure_drive_selected("DRIVE INFO", chr(57581)):
        return
    context.show_drive_info()


def format_drive() -> None:
    context = get_action_context()
    if not _ensure_drive_selected("FORMAT DRIVE", chr(58367)):
        return
    _run_operation(
        lambda: drive_actions.format_drive(
            state=context.state,
            log_debug=context.log_debug,
            get_selected_usb_name=context.get_selected_usb_name,
        )
    )


def unmount_drive() -> None:
    context = get_action_context()
    if not _ensure_drive_selected("UNMOUNT DRIVE", chr(57444)):
        return
    drive_actions.unmount_drive(
        state=context.state,
        log_debug=context.log_debug,
        get_selected_usb_name=context.get_selected_usb_name,
    )


def erase_drive() -> None:
    context = get_action_context()
    if not _ensure_drive_selected("ERASE DRIVE", chr(57639)):
        return
    _run_operation(
        lambda: drive_actions.erase_drive(
            state=context.state,
            log_debug=context.log_debug,
            get_selected_usb_name=context.get_selected_usb_name,
        )
    )
