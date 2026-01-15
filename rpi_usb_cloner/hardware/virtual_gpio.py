"""Virtual GPIO button press handler for web UI control.

This module provides a mechanism to inject virtual button presses
from the web UI into the main event loop, allowing remote control
of the device through the web interface.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Dict, Optional

# Queue for virtual button presses (pin -> timestamp)
_virtual_button_queue: queue.Queue[tuple[int, float]] = queue.Queue()

# Track active virtual button presses with their expiry times
_active_virtual_presses: Dict[int, float] = {}
_virtual_press_lock = threading.Lock()

# Duration for virtual button press (seconds)
VIRTUAL_PRESS_DURATION = 0.15


def inject_button_press(pin: int) -> None:
    """Inject a virtual button press for the specified GPIO pin.

    Args:
        pin: GPIO pin number (from gpio.py constants)
    """
    press_time = time.monotonic()
    _virtual_button_queue.put((pin, press_time))


def has_virtual_press(pin: int) -> bool:
    """Check if there is an active virtual press for the specified pin.

    This should be called from the main loop to check for web UI button presses.

    Args:
        pin: GPIO pin number

    Returns:
        True if the pin has an active virtual press, False otherwise
    """
    with _virtual_press_lock:
        # Process any pending button presses from the queue
        while True:
            try:
                queued_pin, press_time = _virtual_button_queue.get_nowait()
                # Set expiry time for this press
                _active_virtual_presses[queued_pin] = press_time + VIRTUAL_PRESS_DURATION
            except queue.Empty:
                break

        # Check if this pin has an active press
        if pin in _active_virtual_presses:
            now = time.monotonic()
            if now < _active_virtual_presses[pin]:
                return True
            else:
                # Press expired, remove it
                del _active_virtual_presses[pin]

        return False


def clear_virtual_presses() -> None:
    """Clear all active virtual button presses.

    Useful for resetting state, e.g., when waking from screensaver.
    """
    with _virtual_press_lock:
        _active_virtual_presses.clear()
        # Drain the queue
        while True:
            try:
                _virtual_button_queue.get_nowait()
            except queue.Empty:
                break
