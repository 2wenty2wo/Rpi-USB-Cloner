"""Menu action handlers and context management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from rpi_usb_cloner.app.context import AppContext


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


def get_action_context() -> ActionContext:
    """Get the current action context. Raises RuntimeError if not configured."""
    if _ACTION_CONTEXT is None:
        raise RuntimeError("Menu action context has not been configured.")
    return _ACTION_CONTEXT


# Import all action modules
from .drives import copy_drive, drive_info, erase_drive
from .images import backup_image, write_image, images_coming_soon
from .tools import view_logs, tools_coming_soon
from .settings import (
    settings_coming_soon,
    wifi_settings,
    select_restore_partition_mode,
    screensaver_settings,
    toggle_screensaver_enabled,
    toggle_screensaver_mode,
    select_screensaver_gif,
    keyboard_test,
    demo_confirmation_screen,
    demo_status_screen,
    demo_info_screen,
    demo_progress_screen,
    lucide_demo,
    heroicons_demo,
    preview_title_font,
    update_version,
    restart_service,
    stop_service,
    restart_system,
    shutdown_system,
)

# Common utility (used by all action modules)
noop = lambda: None

# Export all public items
__all__ = [
    "ActionContext",
    "set_action_context",
    "get_action_context",
    # Drive actions
    "copy_drive",
    "drive_info",
    "erase_drive",
    # Image actions
    "backup_image",
    "write_image",
    "images_coming_soon",
    # Tool actions
    "view_logs",
    "tools_coming_soon",
    # Settings actions
    "settings_coming_soon",
    "wifi_settings",
    "select_restore_partition_mode",
    "screensaver_settings",
    "toggle_screensaver_enabled",
    "toggle_screensaver_mode",
    "select_screensaver_gif",
    "keyboard_test",
    "demo_confirmation_screen",
    "demo_status_screen",
    "demo_info_screen",
    "demo_progress_screen",
    "lucide_demo",
    "heroicons_demo",
    "preview_title_font",
    "update_version",
    "restart_service",
    "stop_service",
    "restart_system",
    "shutdown_system",
    # Utility
    "noop",
]
