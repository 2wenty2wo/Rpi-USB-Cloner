import time
from typing import Callable, Dict, Optional, Any

import RPi.GPIO as GPIO

from rpi_usb_cloner.hardware import virtual_gpio

PIN_A = 5
PIN_B = 6
PIN_L = 27
PIN_R = 23
PIN_U = 17
PIN_D = 22
PIN_C = 4

PINS = (PIN_A, PIN_B, PIN_L, PIN_R, PIN_U, PIN_D, PIN_C)


def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in PINS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def read_button(pin):
    """Read button state from GPIO pin or virtual button press.

    Returns GPIO.HIGH (1) if not pressed, GPIO.LOW (0) if pressed.
    Virtual button presses from the web UI are merged with physical button states.
    """
    physical_state = GPIO.input(pin)
    # If physical button is pressed, return LOW
    if physical_state == GPIO.LOW:
        return GPIO.LOW
    # Otherwise check for virtual press
    if virtual_gpio.has_virtual_press(pin):
        return GPIO.LOW
    return GPIO.HIGH


def read_buttons(pins):
    return {pin: read_button(pin) for pin in pins}


def is_pressed(pin):
    return read_button(pin) == GPIO.LOW


def cleanup():
    GPIO.cleanup()


def poll_button_events(
    button_handlers: Dict[int, Callable[[], Optional[Any]]],
    poll_interval: float = 0.1,
    loop_callback: Optional[Callable[[], None]] = None,
) -> Optional[Any]:
    """
    Poll button events and call handlers when buttons are pressed (falling edge).

    This utility eliminates duplicated button polling code by providing a reusable
    event loop that:
    - Tracks button state (pressed/released)
    - Detects falling edge events (button press, transition from HIGH to LOW)
    - Calls registered callbacks when buttons are pressed
    - Supports early exit when a callback returns a value

    Args:
        button_handlers: Dictionary mapping button pins to callback functions.
                        Each callback is called when its button is pressed.
                        If a callback returns a non-None value, the loop exits
                        with that value.
        poll_interval: Time to sleep between polling iterations (seconds).
                      Default is 0.1 (100ms).
        loop_callback: Optional function called on each loop iteration after
                      processing buttons but before sleeping. Useful for
                      updating displays or checking other conditions.

    Returns:
        The value returned by any button callback (if non-None), or None if
        the loop exits naturally (e.g., via external interruption).

    Example:
        >>> def on_button_a():
        ...     print("A pressed")
        ...     return "exit"  # Exits loop
        >>>
        >>> def on_button_b():
        ...     print("B pressed")
        ...     # Returns None implicitly, continues loop
        >>>
        >>> result = poll_button_events({
        ...     PIN_A: on_button_a,
        ...     PIN_B: on_button_b,
        ... }, poll_interval=0.1)
    """
    # Initialize previous button states (HIGH = not pressed, LOW = pressed)
    prev_states = {pin: read_button(pin) for pin in button_handlers.keys()}

    while True:
        # Check each button for falling edge (press event)
        for pin, handler in button_handlers.items():
            current_state = read_button(pin)
            # Falling edge: button was HIGH (not pressed) and is now LOW (pressed)
            if prev_states[pin] and not current_state:
                result = handler()
                if result is not None:
                    return result
            prev_states[pin] = current_state

        # Call loop callback if provided (e.g., for screen updates)
        if loop_callback:
            loop_callback()

        # Sleep to prevent CPU spinning
        time.sleep(poll_interval)
