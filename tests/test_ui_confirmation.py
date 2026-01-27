"""Tests for confirmation screen behavior."""

from typing import Dict, Iterable
from unittest.mock import Mock

import pytest

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.ui.screens import confirmation


def _make_is_pressed(sequences: Dict[int, Iterable[bool]]):
    iterators = {pin: iter(values) for pin, values in sequences.items()}

    def is_pressed(pin: int) -> bool:
        iterator = iterators.get(pin)
        if iterator is None:
            return False
        return next(iterator, False)

    return is_pressed


@pytest.mark.parametrize(
    ("default", "expected_index", "expected_result"),
    [
        (False, app_state.CONFIRM_NO, False),
        (True, app_state.CONFIRM_YES, True),
    ],
)
def test_default_confirmation_selection(
    default, expected_index, expected_result, mocker
):
    """Default selection should map to the expected button."""
    render_mock = mocker.patch(
        "rpi_usb_cloner.ui.screens.confirmation.render_confirmation_screen"
    )
    mocker.patch(
        "rpi_usb_cloner.ui.screens.confirmation.menus.wait_for_buttons_release"
    )
    mocker.patch("rpi_usb_cloner.ui.screens.confirmation.time.sleep")
    sequences = {
        gpio.PIN_L: [False, False],
        gpio.PIN_R: [False, False],
        gpio.PIN_A: [False, False],
        gpio.PIN_B: [True, False],
    }
    mocker.patch(
        "rpi_usb_cloner.ui.screens.confirmation.gpio.is_pressed",
        side_effect=_make_is_pressed(sequences),
    )

    result = confirmation.render_confirmation(
        Mock(),
        "CONFIRM",
        "Proceed?",
        default=default,
    )

    render_mock.assert_any_call(
        "CONFIRM",
        ["Proceed?"],
        selected_index=expected_index,
    )
    assert result is expected_result


def test_selection_toggles_when_moving_right(mocker):
    """Selection should move when the right button is released."""
    render_mock = mocker.patch(
        "rpi_usb_cloner.ui.screens.confirmation.render_confirmation_screen"
    )
    mocker.patch(
        "rpi_usb_cloner.ui.screens.confirmation.menus.wait_for_buttons_release"
    )
    mocker.patch("rpi_usb_cloner.ui.screens.confirmation.time.sleep")
    sequences = {
        gpio.PIN_L: [False, False, False, False],
        gpio.PIN_R: [True, False, False, False],
        gpio.PIN_A: [False, False, False, False],
        gpio.PIN_B: [False, False, True, False],
    }
    mocker.patch(
        "rpi_usb_cloner.ui.screens.confirmation.gpio.is_pressed",
        side_effect=_make_is_pressed(sequences),
    )

    result = confirmation.render_confirmation(
        Mock(),
        "CONFIRM",
        "Proceed?",
        default=False,
    )

    expected_calls = [
        mocker.call(
            "CONFIRM",
            ["Proceed?"],
            selected_index=app_state.CONFIRM_NO,
        ),
        mocker.call(
            "CONFIRM",
            ["Proceed?"],
            selected_index=app_state.CONFIRM_YES,
        ),
    ]
    render_mock.assert_has_calls(expected_calls)
    assert result is True


def test_cancel_with_a_returns_false_even_with_default_yes(mocker):
    """Pressing the cancel button should return False regardless of default."""
    render_mock = mocker.patch(
        "rpi_usb_cloner.ui.screens.confirmation.render_confirmation_screen"
    )
    mocker.patch(
        "rpi_usb_cloner.ui.screens.confirmation.menus.wait_for_buttons_release"
    )
    mocker.patch("rpi_usb_cloner.ui.screens.confirmation.time.sleep")
    sequences = {
        gpio.PIN_L: [False, False],
        gpio.PIN_R: [False, False],
        gpio.PIN_A: [True, False],
        gpio.PIN_B: [False, False],
    }
    mocker.patch(
        "rpi_usb_cloner.ui.screens.confirmation.gpio.is_pressed",
        side_effect=_make_is_pressed(sequences),
    )

    result = confirmation.render_confirmation(
        Mock(),
        "CONFIRM",
        "Proceed?",
        default=True,
    )

    render_mock.assert_called_with(
        "CONFIRM",
        ["Proceed?"],
        selected_index=app_state.CONFIRM_YES,
    )
    assert result is False
