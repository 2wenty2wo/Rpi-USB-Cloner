"""Screen rendering functions for the OLED display."""

from .status import render_status_screen, render_status_template, show_coming_soon, wait_for_ack
from .confirmation import render_confirmation_screen, render_update_buttons_screen, render_verify_finish_buttons_screen
from .progress import render_progress_screen
from .info import render_info_screen, wait_for_paginated_input
from .error import render_error_screen
from .demos import show_lucide_demo, show_heroicons_demo, show_title_font_preview
from .wifi import show_wifi_settings
from .logs import show_logs
from .file_browser import show_file_browser

__all__ = [
    # Status screens
    "render_status_screen",
    "render_status_template",
    "show_coming_soon",
    "wait_for_ack",
    # Confirmation screens
    "render_confirmation_screen",
    "render_update_buttons_screen",
    "render_verify_finish_buttons_screen",
    # Progress screens
    "render_progress_screen",
    # Info screens
    "render_info_screen",
    "wait_for_paginated_input",
    # Error screens
    "render_error_screen",
    # Demo screens
    "show_lucide_demo",
    "show_heroicons_demo",
    "show_title_font_preview",
    # WiFi settings
    "show_wifi_settings",
    # Logs
    "show_logs",
    # File browser
    "show_file_browser",
]
