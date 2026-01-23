"""
UI timing and interaction constants.

This module contains shared constants used across the UI layer.
Separated from menus.py to avoid circular imports.
"""

# Button repeat timing
INITIAL_REPEAT_DELAY = 0.3  # Delay before button starts repeating (seconds)
REPEAT_INTERVAL = 0.08  # Interval between repeats once started (seconds)
BUTTON_POLL_DELAY = 0.01  # Polling interval for button state (seconds)

# Horizontal text scrolling
DEFAULT_SCROLL_CYCLE_SECONDS = 6.0  # Time for one complete scroll cycle
DEFAULT_SCROLL_REFRESH_INTERVAL = 0.04  # Refresh interval for scroll animation
