"""Virtual GPIO button press injection for web UI control.

This module provides a thread-safe queue-based system for injecting virtual button
presses from the web UI into the main GPIO event loop.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock


# Default duration for virtual button presses (seconds)
DEFAULT_PRESS_DURATION = 0.15

# Queue of virtual button presses
_virtual_presses: deque[VirtualPress] = deque()
_virtual_presses_lock = Lock()


class VirtualPress:
    """Represents a virtual button press with a pin number and expiry time."""

    def __init__(self, pin: int, duration: float = DEFAULT_PRESS_DURATION):
        self.pin = pin
        self.start_time = time.time()
        self.expiry_time = self.start_time + duration

    def is_active(self) -> bool:
        """Check if this virtual press is still active (not expired)."""
        return time.time() < self.expiry_time


def inject_button_press(pin: int, duration: float = DEFAULT_PRESS_DURATION):
    """Queue a virtual button press for the given pin.

    Args:
        pin: GPIO pin number to simulate
        duration: How long the button press should last (seconds)
    """
    with _virtual_presses_lock:
        _virtual_presses.append(VirtualPress(pin, duration))


def is_virtual_button_pressed(pin: int) -> bool:
    """Check if a virtual button press is currently active for the given pin.

    This function is called by the main event loop during button polling.
    It returns True if there's an active virtual press for the pin, and
    automatically removes expired presses from the queue.

    Args:
        pin: GPIO pin number to check

    Returns:
        True if the virtual button is currently pressed, False otherwise
    """
    with _virtual_presses_lock:
        # Remove expired presses
        while _virtual_presses and not _virtual_presses[0].is_active():
            _virtual_presses.popleft()

        # Check if any active press matches this pin
        for press in _virtual_presses:
            if press.pin == pin and press.is_active():
                return True

    return False


def clear_virtual_presses():
    """Clear all queued virtual button presses."""
    with _virtual_presses_lock:
        _virtual_presses.clear()


def get_active_virtual_presses() -> list[int]:
    """Get list of pins that currently have active virtual presses.

    Returns:
        List of GPIO pin numbers with active virtual presses
    """
    with _virtual_presses_lock:
        # Remove expired presses
        while _virtual_presses and not _virtual_presses[0].is_active():
            _virtual_presses.popleft()

        # Return unique pins
        return list({press.pin for press in _virtual_presses if press.is_active()})
