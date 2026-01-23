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
from .drives import copy_drive, drive_info, erase_drive, format_drive, unmount_drive
from .images import backup_image, images_coming_soon, write_image
from .settings import (
    demo_confirmation_screen,
    demo_info_screen,
    demo_progress_screen,
    demo_status_screen,
    heroicons_demo,
    keyboard_test,
    lucide_demo,
    preview_title_font,
    restart_service,
    restart_system,
    screensaver_settings,
    select_restore_partition_mode,
    select_screensaver_gif,
    settings_coming_soon,
    show_about_credits,
    shutdown_system,
    stop_service,
    toggle_menu_view_mode,
    toggle_screensaver_enabled,
    toggle_screensaver_mode,
    toggle_screenshots,
    toggle_web_server,
    update_version,
    wifi_settings,
)
from .tools import file_browser, tools_coming_soon, view_logs


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
    "format_drive",
    "unmount_drive",
    "erase_drive",
    # Image actions
    "backup_image",
    "write_image",
    "images_coming_soon",
    # Tool actions
    "view_logs",
    "tools_coming_soon",
    "file_browser",
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
    "toggle_menu_view_mode",
    "toggle_screenshots",
    "toggle_web_server",
    "update_version",
    "restart_service",
    "stop_service",
    "restart_system",
    "shutdown_system",
    "show_about_credits",
    # Utility
    "noop",
]
