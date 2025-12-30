from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from rpi_usb_cloner.actions import drive_actions, image_actions, settings_actions, tools_actions
from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.ui import display


@dataclass
class ActionContext:
    app_context: AppContext
    clone_mode: str
    state: object
    log_debug: Callable[[str], None]
    get_selected_usb_name: Callable[[], Optional[str]]
    show_drive_info: Callable[[], None]


_ACTION_CONTEXT: Optional[ActionContext] = None


def set_action_context(context: ActionContext) -> None:
    global _ACTION_CONTEXT
    _ACTION_CONTEXT = context


def _require_context() -> ActionContext:
    if _ACTION_CONTEXT is None:
        raise RuntimeError("Menu action context has not been configured.")
    return _ACTION_CONTEXT


def _ensure_drive_selected() -> bool:
    context = _require_context()
    if context.app_context.active_drive:
        return True
    display.display_lines(["NO DRIVE", "SELECTED"])
    time.sleep(1)
    return False


def copy_drive() -> None:
    context = _require_context()
    if not _ensure_drive_selected():
        return
    drive_actions.copy_drive(
        state=context.state,
        clone_mode=context.clone_mode,
        log_debug=context.log_debug,
        get_selected_usb_name=context.get_selected_usb_name,
    )


def drive_info() -> None:
    context = _require_context()
    if not _ensure_drive_selected():
        return
    context.show_drive_info()


def erase_drive() -> None:
    context = _require_context()
    if not _ensure_drive_selected():
        return
    drive_actions.erase_drive(
        state=context.state,
        log_debug=context.log_debug,
        get_selected_usb_name=context.get_selected_usb_name,
    )


def images_coming_soon() -> None:
    image_actions.coming_soon()


def tools_coming_soon() -> None:
    tools_actions.coming_soon()


def settings_coming_soon() -> None:
    settings_actions.coming_soon()


def noop() -> None:
    return None
