"""Settings action handlers for the Rpi-USB-Cloner application.

This package provides settings-related functionality including:
- UI settings (screensaver, keyboard, demos)
- Software updates and version management
- System power operations (restart, shutdown)
- System utilities and service management
"""

from .system_power import (
    confirm_action,
    restart_service,
    restart_system,
    shutdown_system,
    stop_service,
)
from .system_utils import (
    format_command_output,
    get_app_version,
    has_dirty_working_tree,
    is_dubious_ownership_error,
    is_git_repo,
    is_running_under_systemd,
    log_debug_msg,
    parse_git_progress_ratio,
    poweroff_system,
    reboot_system,
    run_command,
    run_git_pull,
)
from .ui_actions import (
    coming_soon,
    demo_confirmation_screen,
    demo_info_screen,
    demo_progress_screen,
    demo_status_screen,
    heroicons_demo,
    keyboard_test,
    lucide_demo,
    preview_title_font,
    screensaver_settings,
    select_restore_partition_mode,
    select_screensaver_gif,
    show_about_credits,
    toggle_screensaver_enabled,
    toggle_screensaver_mode,
    toggle_screenshots,
    toggle_web_server,
    wifi_settings,
)
from .update_manager import (
    build_update_info_lines,
    check_update_status,
    get_update_status,
    run_update_flow,
    update_version,
)


__all__ = [
    # UI actions
    "coming_soon",
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
    "toggle_screenshots",
    "toggle_web_server",
    "show_about_credits",
    # Update manager
    "update_version",
    "get_update_status",
    "check_update_status",
    "build_update_info_lines",
    "run_update_flow",
    # System power
    "restart_service",
    "stop_service",
    "restart_system",
    "shutdown_system",
    "confirm_action",
    # System utilities
    "get_app_version",
    "is_git_repo",
    "has_dirty_working_tree",
    "is_dubious_ownership_error",
    "is_running_under_systemd",
    "format_command_output",
    "log_debug_msg",
    "run_command",
    "run_git_pull",
    "parse_git_progress_ratio",
    "reboot_system",
    "poweroff_system",
]
