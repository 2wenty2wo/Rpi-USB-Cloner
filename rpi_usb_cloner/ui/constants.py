"""
UI constants for the Raspberry Pi USB Cloner.

This module contains constants used across the UI layer, extracted to prevent
circular import issues. These constants define timing parameters, scroll speeds,
and other UI configuration values.
"""

# Button repeat timing constants
INITIAL_REPEAT_DELAY = 0.3  # Delay before button repeat starts (seconds)
REPEAT_INTERVAL = 0.08      # Interval between repeated button events (seconds)
BUTTON_POLL_DELAY = 0.01    # Delay between button state polling (seconds)

# Scrolling constants
DEFAULT_SCROLL_CYCLE_SECONDS = 6.0        # Default time for one scroll cycle (seconds)
DEFAULT_SCROLL_REFRESH_INTERVAL = 0.04    # Refresh interval for scroll animation (seconds)
