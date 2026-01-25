"""Drive-related menu actions."""

from __future__ import annotations

import time

from rpi_usb_cloner.actions import drive_actions
from rpi_usb_cloner.ui import screens
from rpi_usb_cloner.ui.icons import (
    ALERT_ICON,
    DRIVES_ICON,
    EJECT_ICON,
    FOLDER_ICON,
    SPARKLES_ICON,
)

from . import get_action_context


def _ensure_drive_selected(title: str, title_icon: str) -> bool:
    context = get_action_context()
    if context.app_context.active_drive:
        return True
    screens.render_error_screen(
        title,
        message="No drive selected",
        title_icon=title_icon,
        message_icon=ALERT_ICON,
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
    if not _ensure_drive_selected("COPY DRIVE", DRIVES_ICON):
        return
    _run_operation(
        lambda: drive_actions.copy_drive(
            state=context.state,
            clone_mode=context.clone_mode,
            get_selected_usb_name=context.get_selected_usb_name,
        )
    )


def drive_info() -> None:
    context = get_action_context()
    if not _ensure_drive_selected("DRIVE INFO", DRIVES_ICON):
        return
    drive_actions.drive_info(
        state=context.state,
        get_selected_usb_name=context.get_selected_usb_name,
    )


def format_drive() -> None:
    context = get_action_context()
    if not _ensure_drive_selected("FORMAT DRIVE", SPARKLES_ICON):
        return
    _run_operation(
        lambda: drive_actions.format_drive(
            state=context.state,
            get_selected_usb_name=context.get_selected_usb_name,
        )
    )


def unmount_drive() -> None:
    context = get_action_context()
    if not _ensure_drive_selected("UNMOUNT DRIVE", EJECT_ICON):
        return
    drive_actions.unmount_drive(
        state=context.state,
        get_selected_usb_name=context.get_selected_usb_name,
    )


def erase_drive() -> None:
    context = get_action_context()
    if not _ensure_drive_selected("ERASE DRIVE", ALERT_ICON):
        return
    _run_operation(
        lambda: drive_actions.erase_drive(
            state=context.state,
            get_selected_usb_name=context.get_selected_usb_name,
        )
    )


def create_repo_drive() -> None:
    context = get_action_context()
    if not _ensure_drive_selected("CREATE REPO", FOLDER_ICON):
        return
    drive_actions.create_repo_drive(
        state=context.state,
        get_selected_usb_name=context.get_selected_usb_name,
    )
