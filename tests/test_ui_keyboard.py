"""Tests for keyboard input state transitions."""

from typing import Dict, Iterable

import pytest

from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.ui import keyboard


def _make_is_pressed(sequences: Dict[int, Iterable[bool]]):
    iterators = {pin: iter(values) for pin, values in sequences.items()}

    def is_pressed(pin: int) -> bool:
        iterator = iterators.get(pin)
        if iterator is None:
            return False
        return next(iterator, False)

    return is_pressed


@pytest.mark.parametrize("initial", ["", "hi"])
def test_prompt_text_mode_switch_to_ok_returns_value(mocker, initial):
    """Navigating to OK in mode strip returns the current value."""
    mocker.patch("rpi_usb_cloner.ui.keyboard.menus.wait_for_buttons_release")
    mocker.patch("rpi_usb_cloner.ui.keyboard.time.sleep")
    monotonic = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    mocker.patch(
        "rpi_usb_cloner.ui.keyboard.time.monotonic",
        side_effect=lambda: next(monotonic),
    )
    render_mock = mocker.patch("rpi_usb_cloner.ui.keyboard._render_keyboard")

    sequences = {
        gpio.PIN_U: [False] * 12,
        gpio.PIN_D: [False, True, False] + [False] * 9,
        gpio.PIN_L: [False] * 12,
        gpio.PIN_R: [
            False,
            False,
            True,
            False,
            True,
            False,
            True,
            False,
            True,
            False,
            False,
            False,
        ],
        gpio.PIN_A: [False] * 12,
        gpio.PIN_B: [False] * 10 + [True, False],
        gpio.PIN_C: [False] * 12,
    }
    mocker.patch(
        "rpi_usb_cloner.ui.keyboard.is_pressed",
        side_effect=_make_is_pressed(sequences),
    )

    result = keyboard.prompt_text("Title", initial=initial)

    assert result == initial
    last_call = render_mock.call_args_list[-1]
    assert last_call.args[6] == "modes"
    assert last_call.args[7] == 5
