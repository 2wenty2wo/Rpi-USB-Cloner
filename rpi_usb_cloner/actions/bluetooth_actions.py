"""Action handlers for Bluetooth tethering."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpi_usb_cloner.app.context import AppContext

from rpi_usb_cloner.config.settings import get_bool, get_setting, set_bool, set_setting
from rpi_usb_cloner.services.bluetooth import (
    disable_bluetooth_tethering,
    enable_bluetooth_tethering,
    get_bluetooth_service,
    get_bluetooth_status,
    get_paired_devices,
    hide_discoverable,
    is_bluetooth_available,
    make_discoverable,
    remove_paired_device,
    trust_device,
)
from rpi_usb_cloner.ui.screens.confirmation import render_confirmation
from rpi_usb_cloner.ui.screens.error import render_error_screen
from rpi_usb_cloner.ui.screens.status import render_status

logger = logging.getLogger(__name__)


def bluetooth_menu_action(context: AppContext) -> None:
    """Show Bluetooth tethering menu."""
    from rpi_usb_cloner.menu.navigator import MenuNavigator
    from rpi_usb_cloner.menu.definitions.bluetooth import get_bluetooth_menu

    navigator = MenuNavigator()
    navigator.navigate_to(get_bluetooth_menu())


def toggle_bluetooth_action(context: AppContext) -> None:
    """Toggle Bluetooth tethering on/off."""
    if not is_bluetooth_available():
        render_error_screen(
            context,
            title="Bluetooth Error",
            message="Bluetooth adapter not found. Check hardware.",
        )
        return

    enabled = get_bool("bluetooth_enabled", default=False)

    if enabled:
        # Turn off
        confirmed = render_confirmation(
            context,
            title="Disable Bluetooth",
            message="Stop Bluetooth tethering?",
            default=False,
        )

        if not confirmed:
            return

        try:
            if disable_bluetooth_tethering():
                set_bool("bluetooth_enabled", False)
                render_status(context, "Bluetooth Disabled", "Tethering stopped")
            else:
                render_error_screen(
                    context,
                    title="Error",
                    message="Failed to disable Bluetooth",
                )
        except Exception as e:
            logger.error(f"Error disabling Bluetooth: {e}")
            render_error_screen(
                context,
                title="Error",
                message=f"Failed to disable: {str(e)}",
                exception=e,
            )
    else:
        # Turn on
        confirmed = render_confirmation(
            context,
            title="Enable Bluetooth",
            message="Start Bluetooth tethering?",
            default=True,
        )

        if not confirmed:
            return

        try:
            render_status(context, "Starting...", "Enabling Bluetooth PAN")

            if enable_bluetooth_tethering():
                set_bool("bluetooth_enabled", True)

                # Get status to show IP
                status = get_bluetooth_status()
                ip_msg = f"IP: {status.ip_address}" if status.ip_address else "Ready"

                render_status(
                    context,
                    "Bluetooth Enabled",
                    f"Tethering active\n{ip_msg}\n\nPair from iPhone:\nSettings > Bluetooth",
                )
            else:
                render_error_screen(
                    context,
                    title="Error",
                    message="Failed to enable Bluetooth.\n\nCheck logs for details.",
                )
        except Exception as e:
            logger.error(f"Error enabling Bluetooth: {e}")
            render_error_screen(
                context,
                title="Error",
                message=f"Failed to enable: {str(e)}",
                exception=e,
            )


def make_discoverable_action(context: AppContext) -> None:
    """Make device discoverable for pairing."""
    if not is_bluetooth_available():
        render_error_screen(
            context,
            title="Bluetooth Error",
            message="Bluetooth adapter not found",
        )
        return

    timeout = get_setting("bluetooth_discoverable_timeout", default=300)

    confirmed = render_confirmation(
        context,
        title="Make Discoverable",
        message=f"Allow pairing for {timeout//60} minutes?",
        default=True,
    )

    if not confirmed:
        return

    try:
        if make_discoverable(timeout):
            device_name = get_setting("bluetooth_device_name", default="RPi USB Cloner")
            render_status(
                context,
                "Discoverable",
                f"Device: {device_name}\n\nVisible for {timeout//60} min\n\nPair from:\niPhone Settings > Bluetooth",
            )
        else:
            render_error_screen(
                context,
                title="Error",
                message="Failed to enable discoverable mode",
            )
    except Exception as e:
        logger.error(f"Error making discoverable: {e}")
        render_error_screen(
            context,
            title="Error",
            message=f"Failed: {str(e)}",
            exception=e,
        )


def hide_discoverable_action(context: AppContext) -> None:
    """Hide device from discovery."""
    if not is_bluetooth_available():
        return

    try:
        if hide_discoverable():
            render_status(context, "Hidden", "Device no longer discoverable")
        else:
            render_error_screen(
                context,
                title="Error",
                message="Failed to hide device",
            )
    except Exception as e:
        logger.error(f"Error hiding device: {e}")
        render_error_screen(
            context,
            title="Error",
            message=str(e),
            exception=e,
        )


def show_bluetooth_status_action(context: AppContext) -> None:
    """Show current Bluetooth status."""
    if not is_bluetooth_available():
        render_error_screen(
            context,
            title="Bluetooth Status",
            message="Bluetooth adapter: Not found\n\nCheck hardware connection",
        )
        return

    try:
        status = get_bluetooth_status()

        lines = []
        lines.append(f"Adapter: {'Yes' if status.adapter_present else 'No'}")
        lines.append(f"Powered: {'On' if status.powered else 'Off'}")
        lines.append(f"PAN: {'Active' if status.pan_active else 'Inactive'}")

        if status.ip_address:
            lines.append(f"IP: {status.ip_address}")

        if status.discoverable:
            lines.append("Mode: Discoverable")

        paired_count = len(status.connected_devices)
        if paired_count > 0:
            lines.append(f"Paired: {paired_count} device(s)")

        message = "\n".join(lines)

        render_status(context, "Bluetooth Status", message)

    except Exception as e:
        logger.error(f"Error getting Bluetooth status: {e}")
        render_error_screen(
            context,
            title="Error",
            message=str(e),
            exception=e,
        )


def manage_paired_devices_action(context: AppContext) -> None:
    """Show and manage paired devices."""
    if not is_bluetooth_available():
        render_error_screen(
            context,
            title="Bluetooth Error",
            message="Bluetooth adapter not found",
        )
        return

    try:
        devices = get_paired_devices()

        if not devices:
            render_status(
                context,
                "Paired Devices",
                "No paired devices\n\nMake discoverable to pair",
            )
            return

        # Show device list
        lines = [f"Found {len(devices)} device(s):\n"]
        for i, device in enumerate(devices, 1):
            status_icon = "✓" if device.connected else " "
            lines.append(f"{status_icon} {device.name}")

        message = "\n".join(lines)
        render_status(context, "Paired Devices", message)

    except Exception as e:
        logger.error(f"Error listing paired devices: {e}")
        render_error_screen(
            context,
            title="Error",
            message=str(e),
            exception=e,
        )


def toggle_auto_start_action(context: AppContext) -> None:
    """Toggle Bluetooth auto-start on boot."""
    enabled = get_bool("bluetooth_auto_start", default=False)

    new_state = not enabled
    set_bool("bluetooth_auto_start", new_state)

    state_text = "enabled" if new_state else "disabled"
    render_status(
        context,
        "Auto-Start Updated",
        f"Bluetooth auto-start:\n{state_text.upper()}\n\nTakes effect on next boot",
    )


def set_device_name_action(context: AppContext) -> None:
    """Set Bluetooth device name."""
    from rpi_usb_cloner.ui.keyboard import render_keyboard

    current_name = get_setting("bluetooth_device_name", default="RPi USB Cloner")

    new_name = render_keyboard(
        context,
        title="Device Name",
        initial_value=current_name,
    )

    if new_name and new_name != current_name:
        set_setting("bluetooth_device_name", new_name)

        # Update system Bluetooth name
        try:
            import subprocess

            subprocess.run(
                ["bluetoothctl", "system-alias", new_name],
                capture_output=True,
                timeout=5,
                check=True,
            )

            render_status(
                context,
                "Name Updated",
                f"Device name:\n{new_name}\n\nRestart to apply fully",
            )
        except Exception as e:
            logger.warning(f"Failed to update system Bluetooth name: {e}")
            render_status(
                context,
                "Name Saved",
                f"Name: {new_name}\n\nRestart to apply",
            )


def show_connection_info_action(context: AppContext) -> None:
    """Show connection information for accessing web UI."""
    if not is_bluetooth_available():
        render_error_screen(
            context,
            title="Bluetooth Error",
            message="Bluetooth adapter not found",
        )
        return

    try:
        status = get_bluetooth_status()

        if not status.pan_active:
            render_status(
                context,
                "Connection Info",
                "Bluetooth not active\n\nEnable tethering first",
            )
            return

        ip = status.ip_address or "192.168.55.1"
        url = f"http://{ip}:8000"

        render_status(
            context,
            "Web UI Access",
            f"1. Pair iPhone to Pi\n2. Connect to Bluetooth\n3. Open Safari:\n\n{url}",
        )

    except Exception as e:
        logger.error(f"Error getting connection info: {e}")
        render_error_screen(
            context,
            title="Error",
            message=str(e),
            exception=e,
        )
