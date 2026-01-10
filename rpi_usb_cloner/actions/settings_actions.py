"""Settings action handlers (compatibility layer).

This module provides backwards compatibility by re-exporting functionality
from the refactored settings package.

For new code, prefer importing directly from:
    rpi_usb_cloner.actions.settings.*
"""
# Re-export all public APIs from the settings package
from rpi_usb_cloner.actions.settings import (
    build_update_info_lines,
    check_update_status,
    coming_soon,
    confirm_action,
    demo_confirmation_screen,
    demo_info_screen,
    demo_progress_screen,
    demo_status_screen,
    format_command_output,
    get_app_version,
    get_update_status,
    has_dirty_working_tree,
    heroicons_demo,
    is_dubious_ownership_error,
    is_git_repo,
    is_running_under_systemd,
    keyboard_test,
    log_debug_msg,
    lucide_demo,
    parse_git_progress_ratio,
    poweroff_system,
    preview_title_font,
    reboot_system,
    restart_service,
    restart_system,
    run_command,
    run_git_pull,
    run_update_flow,
    screensaver_settings,
    select_restore_partition_mode,
    select_screensaver_gif,
    shutdown_system,
    stop_service,
    toggle_screensaver_enabled,
    toggle_screensaver_mode,
    update_version,
    wifi_settings,
)

# Backwards compatibility aliases
_log_debug = log_debug_msg
_get_app_version = get_app_version
_is_git_repo = is_git_repo
_has_dirty_working_tree = has_dirty_working_tree
_run_git_pull = run_git_pull
_GIT_PROGRESS_STAGES = {
    "Receiving objects": 0,
    "Resolving deltas": 1,
    "Updating files": 2,
}
_parse_git_progress_ratio = parse_git_progress_ratio
_get_update_status = get_update_status
_check_update_status = check_update_status
_build_update_info_lines = build_update_info_lines
_format_command_output = format_command_output
_is_dubious_ownership_error = is_dubious_ownership_error
_is_running_under_systemd = is_running_under_systemd
_restart_systemd_service = restart_service
_stop_systemd_service = stop_service
_confirm_power_action = confirm_action
_confirm_action = confirm_action
_run_systemctl_command = run_command
_restart_service = restart_service
_stop_service = stop_service
_reboot_system = reboot_system
_poweroff_system = poweroff_system
_get_git_version = get_app_version
_run_command = run_command
_SERVICE_NAME = "rpi-usb-cloner.service"
_run_update_flow = run_update_flow

__all__ = [
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
    "update_version",
    "restart_service",
    "stop_service",
    "restart_system",
    "shutdown_system",
]
