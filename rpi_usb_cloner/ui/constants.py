"""
UI timing and interaction constants.

This module contains shared constants used across the UI layer.
Separated from menus.py to avoid circular imports.
"""

# Re-export from settings for backward compatibility
from rpi_usb_cloner.config.settings import DEFAULT_SCROLL_REFRESH_INTERVAL

# Button repeat timing
INITIAL_REPEAT_DELAY = 0.25  # Delay before button starts repeating (seconds)
REPEAT_INTERVAL = 0.08  # Interval between repeats once started (seconds)
BUTTON_POLL_DELAY = 0.02  # Polling interval for button state (seconds)

# Horizontal text scrolling
DEFAULT_SCROLL_CYCLE_SECONDS = 6.0  # Time for one complete scroll cycle

__all__ = [
    "INITIAL_REPEAT_DELAY",
    "REPEAT_INTERVAL",
    "BUTTON_POLL_DELAY",
    "DEFAULT_SCROLL_CYCLE_SECONDS",
    "DEFAULT_SCROLL_REFRESH_INTERVAL",
]
