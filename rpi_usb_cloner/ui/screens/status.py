"""Status screen rendering functions."""

import time
from typing import Iterable, Optional

from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.ui import display, menus
from rpi_usb_cloner.ui.constants import BUTTON_POLL_DELAY


def render_status_template(
    title: str,
    status: str = "Running...",
    *,
    progress_line: Optional[str] = None,
    extra_lines: Optional[Iterable[str]] = None,
    title_icon: Optional[str] = None,
    title_icon_font=None,
    title_font=None,
    body_font=None,
) -> None:
    lines = [status]
    if progress_line:
        lines.append(progress_line)
    if extra_lines:
        lines.extend(line for line in extra_lines if line)
    display.render_paginated_lines(
        title,
        lines,
        page_index=0,
        title_font=title_font,
        items_font=body_font,
        title_icon=title_icon,
        title_icon_font=title_icon_font,
    )


def show_coming_soon(title="COMING SOON", delay=1) -> None:
    display.display_lines([title, "Not implemented", "yet"])
    if delay:
        time.sleep(delay)


def wait_for_ack(
    *,
    buttons: Optional[Iterable[int]] = None,
    poll_delay: float = BUTTON_POLL_DELAY,
) -> None:
    if buttons is None:
        buttons = (gpio.PIN_A, gpio.PIN_B)
    buttons = tuple(buttons)
    menus.wait_for_buttons_release(buttons, poll_delay=poll_delay)
    # Use poll_button_events: any button press returns True, which exits the loop
    gpio.poll_button_events(
        {pin: lambda: True for pin in buttons}, poll_interval=poll_delay
    )


def render_status_screen(
    title: str,
    status: str = "Running...",
    *,
    progress_line: Optional[str] = None,
    extra_lines: Optional[Iterable[str]] = None,
    title_icon: Optional[str] = None,
    title_icon_font=None,
    title_font=None,
    body_font=None,
) -> None:
    render_status_template(
        title,
        status,
        progress_line=progress_line,
        extra_lines=extra_lines,
        title_icon=title_icon,
        title_icon_font=title_icon_font,
        title_font=title_font,
        body_font=body_font,
    )
