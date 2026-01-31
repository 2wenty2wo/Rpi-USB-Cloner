"""Settings action handlers (compatibility layer).

This module provides backwards compatibility by re-exporting functionality
from the refactored settings package.

For new code, prefer importing directly from:
    rpi_usb_cloner.actions.settings.*
"""

from __future__ import annotations

import importlib
from typing import Any


_EXPORTS = {
    # UI actions
    "coming_soon": ("rpi_usb_cloner.actions.settings.ui_actions", "coming_soon"),
    "wifi_settings": ("rpi_usb_cloner.actions.settings.ui_actions", "wifi_settings"),
    "select_restore_partition_mode": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "select_restore_partition_mode",
    ),
    "select_transition_speed": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "select_transition_speed",
    ),
    "screensaver_settings": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "screensaver_settings",
    ),
    "toggle_screensaver_enabled": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "toggle_screensaver_enabled",
    ),
    "toggle_screensaver_mode": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "toggle_screensaver_mode",
    ),
    "select_screensaver_gif": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "select_screensaver_gif",
    ),
    "keyboard_test": ("rpi_usb_cloner.actions.settings.ui_actions", "keyboard_test"),
    "demo_confirmation_screen": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "demo_confirmation_screen",
    ),
    "demo_status_screen": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "demo_status_screen",
    ),
    "demo_info_screen": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "demo_info_screen",
    ),
    "demo_progress_screen": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "demo_progress_screen",
    ),
    "lucide_demo": ("rpi_usb_cloner.actions.settings.ui_actions", "lucide_demo"),
    "heroicons_demo": ("rpi_usb_cloner.actions.settings.ui_actions", "heroicons_demo"),
    "preview_title_font": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "preview_title_font",
    ),
    "preview_screensaver": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "preview_screensaver",
    ),
    "toggle_screenshots": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "toggle_screenshots",
    ),
    "toggle_menu_icon_preview": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "toggle_menu_icon_preview",
    ),
    "toggle_web_server": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "toggle_web_server",
    ),
    "show_about_credits": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "show_about_credits",
    ),
    # Status bar toggles
    "toggle_status_bar_enabled": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "toggle_status_bar_enabled",
    ),
    "toggle_status_bar_wifi": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "toggle_status_bar_wifi",
    ),
    "toggle_status_bar_bluetooth": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "toggle_status_bar_bluetooth",
    ),
    "toggle_status_bar_web": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "toggle_status_bar_web",
    ),
    "toggle_status_bar_drives": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "toggle_status_bar_drives",
    ),
    # Update manager
    "update_version": (
        "rpi_usb_cloner.actions.settings.update_manager",
        "update_version",
    ),
    "get_update_status": (
        "rpi_usb_cloner.actions.settings.update_manager",
        "get_update_status",
    ),
    "check_update_status": (
        "rpi_usb_cloner.actions.settings.update_manager",
        "check_update_status",
    ),
    "build_update_info_lines": (
        "rpi_usb_cloner.actions.settings.update_manager",
        "build_update_info_lines",
    ),
    "run_update_flow": (
        "rpi_usb_cloner.actions.settings.update_manager",
        "run_update_flow",
    ),
    # System power
    "restart_service": (
        "rpi_usb_cloner.actions.settings.system_power",
        "restart_service",
    ),
    "stop_service": (
        "rpi_usb_cloner.actions.settings.system_power",
        "stop_service",
    ),
    "restart_system": (
        "rpi_usb_cloner.actions.settings.system_power",
        "restart_system",
    ),
    "shutdown_system": (
        "rpi_usb_cloner.actions.settings.system_power",
        "shutdown_system",
    ),
    "confirm_action": (
        "rpi_usb_cloner.actions.settings.system_power",
        "confirm_action",
    ),
    # System utilities
    "get_app_version": (
        "rpi_usb_cloner.actions.settings.system_utils",
        "get_app_version",
    ),
    "is_git_repo": ("rpi_usb_cloner.actions.settings.system_utils", "is_git_repo"),
    "has_dirty_working_tree": (
        "rpi_usb_cloner.actions.settings.system_utils",
        "has_dirty_working_tree",
    ),
    "is_dubious_ownership_error": (
        "rpi_usb_cloner.actions.settings.system_utils",
        "is_dubious_ownership_error",
    ),
    "is_running_under_systemd": (
        "rpi_usb_cloner.actions.settings.system_utils",
        "is_running_under_systemd",
    ),
    "format_command_output": (
        "rpi_usb_cloner.actions.settings.system_utils",
        "format_command_output",
    ),
    "run_command": ("rpi_usb_cloner.actions.settings.system_utils", "run_command"),
    "run_git_pull": ("rpi_usb_cloner.actions.settings.system_utils", "run_git_pull"),
    "parse_git_progress_ratio": (
        "rpi_usb_cloner.actions.settings.system_utils",
        "parse_git_progress_ratio",
    ),
    "reboot_system": ("rpi_usb_cloner.actions.settings.system_utils", "reboot_system"),
    "poweroff_system": (
        "rpi_usb_cloner.actions.settings.system_utils",
        "poweroff_system",
    ),
    # Bluetooth PAN
    "bluetooth_settings": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "bluetooth_settings",
    ),
    "toggle_bluetooth_pan": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "toggle_bluetooth_pan",
    ),
    "show_bluetooth_qr": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "show_bluetooth_qr",
    ),
    "enable_bluetooth_pan": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "enable_bluetooth_pan",
    ),
    "disable_bluetooth_pan": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "disable_bluetooth_pan",
    ),
    "bluetooth_trusted_devices": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "bluetooth_trusted_devices",
    ),
    "bluetooth_trust_current": (
        "rpi_usb_cloner.actions.settings.ui_actions",
        "bluetooth_trust_current",
    ),
}

__all__ = list(_EXPORTS.keys())


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attribute = _EXPORTS[name]
    module = importlib.import_module(module_path)
    return getattr(module, attribute)


def __dir__() -> list[str]:
    return sorted(__all__)
