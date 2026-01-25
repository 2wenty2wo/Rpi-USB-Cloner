"""System power management operations."""

import sys
import time
from typing import Optional

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.logging import LoggerFactory
from rpi_usb_cloner.ui import display, menus, screens

from .system_utils import (
    format_command_output,
    poweroff_system,
    reboot_system,
)
from .system_utils import (
    restart_service as restart_systemd_service,
)
from .system_utils import (
    stop_service as stop_systemd_service,
)


# Create logger for power management
log = LoggerFactory.for_system()


_SERVICE_NAME = "rpi-usb-cloner.service"


def restart_service() -> None:
    """Restart the service."""
    title = "POWER"
    screens.render_status_template(title, "Restarting...", progress_line=_SERVICE_NAME)
    display.clear_display()
    restart_result = restart_systemd_service()
    if restart_result.returncode != 0:
        log.debug(
            f"Service restart failed with return code {restart_result.returncode}",
            component="power",
        )
        screens.wait_for_paginated_input(
            title,
            ["Service restart failed"]
            + format_command_output(restart_result.stdout, restart_result.stderr),
        )
        return
    display.clear_display()
    sys.exit(0)


def stop_service() -> None:
    """Stop the service."""
    title = "POWER"
    screens.render_status_template(title, "Stopping...", progress_line=_SERVICE_NAME)
    display.clear_display()
    stop_result = stop_systemd_service()
    if stop_result.returncode != 0:
        log.debug(
            f"Service stop failed with return code {stop_result.returncode}",
            component="power",
        )
        screens.wait_for_paginated_input(
            title,
            ["Service stop failed"]
            + format_command_output(stop_result.stdout, stop_result.stderr),
        )
        return
    display.clear_display()
    sys.exit(0)


def restart_system() -> None:
    """Restart the system."""
    title = "POWER"
    if not confirm_power_action(title, "RESTART SYSTEM"):
        return
    screens.render_status_template(
        title, "Restarting...", progress_line="System reboot"
    )
    display.clear_display()
    reboot_result = reboot_system()
    if reboot_result.returncode != 0:
        log.debug(
            f"System reboot failed with return code {reboot_result.returncode}",
            component="power",
        )
        screens.wait_for_paginated_input(
            title,
            ["System reboot failed"]
            + format_command_output(reboot_result.stdout, reboot_result.stderr),
        )


def shutdown_system() -> None:
    """Shutdown the system."""
    title = "POWER"
    if not confirm_power_action(title, "SHUTDOWN SYSTEM"):
        return
    screens.render_status_template(
        title, "Shutting down...", progress_line="System poweroff"
    )
    display.clear_display()
    shutdown_result = poweroff_system()
    if shutdown_result.returncode != 0:
        log.debug(
            f"System poweroff failed with return code {shutdown_result.returncode}",
            component="power",
        )
        screens.wait_for_paginated_input(
            title,
            ["System poweroff failed"]
            + format_command_output(shutdown_result.stdout, shutdown_result.stderr),
        )
        return
    display.clear_display()
    display.display_lines(["Shutdown initiated", "Safe to remove power"])
    while True:
        time.sleep(1)


def confirm_power_action(
    title: str,
    action_label: str,
) -> bool:
    """Confirm a power action with the user."""
    prompt = f"Are you sure you want to {action_label.lower()}?"
    confirmed = confirm_action(title, prompt)
    log.debug(
        f"Power action confirmation {action_label}: confirmed={confirmed}",
        component="power",
    )
    return confirmed


def confirm_action(
    title: str,
    prompt: str,
    *,
    title_icon: Optional[str] = None,
) -> bool:
    """Display a confirmation dialog and get user response."""
    selection = app_state.CONFIRM_NO
    screens.render_confirmation_screen(
        title,
        [prompt],
        selected_index=selection,
        title_icon=title_icon,
    )
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B])
    prev_states = {
        "L": gpio.is_pressed(gpio.PIN_L),
        "R": gpio.is_pressed(gpio.PIN_R),
        "A": gpio.is_pressed(gpio.PIN_A),
        "B": gpio.is_pressed(gpio.PIN_B),
    }
    while True:
        current_r = gpio.is_pressed(gpio.PIN_R)
        if not prev_states["R"] and current_r and selection == app_state.CONFIRM_NO:
            selection = app_state.CONFIRM_YES
            log.debug(f"Confirmation selection changed: {selection}", component="power")
        current_l = gpio.is_pressed(gpio.PIN_L)
        if not prev_states["L"] and current_l and selection == app_state.CONFIRM_YES:
            selection = app_state.CONFIRM_NO
            log.debug(f"Confirmation selection changed: {selection}", component="power")
        current_a = gpio.is_pressed(gpio.PIN_A)
        if not prev_states["A"] and current_a:
            return False
        current_b = gpio.is_pressed(gpio.PIN_B)
        if not prev_states["B"] and current_b:
            return selection == app_state.CONFIRM_YES
        prev_states["R"] = current_r
        prev_states["L"] = current_l
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        screens.render_confirmation_screen(
            title,
            [prompt],
            selected_index=selection,
            title_icon=title_icon,
        )
        time.sleep(menus.BUTTON_POLL_DELAY)
