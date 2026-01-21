"""Bluetooth menu action handlers."""

from __future__ import annotations

import logging

from rpi_usb_cloner.config.settings import get_bool, get_setting, set_bool, set_setting
from rpi_usb_cloner.services.bluetooth import (
    disable_bluetooth_tethering,
    enable_bluetooth_tethering,
    get_bluetooth_status,
    get_bluetooth_last_error,
    get_paired_devices,
    hide_discoverable,
    is_bluetooth_available,
    make_discoverable,
)
from rpi_usb_cloner.ui import screens
from rpi_usb_cloner.ui.screens.confirmation import render_confirmation
from rpi_usb_cloner.ui.screens.status import render_status_screen, wait_for_ack

from . import get_action_context

logger = logging.getLogger(__name__)


def _append_bluetooth_error(message: str) -> str:
    """Append the last Bluetooth error reason to a message if available."""
    error_text = get_bluetooth_last_error()
    if error_text:
        return f"{message}\nReason: {error_text}"
    return message


def bluetooth_toggle():
    """Toggle Bluetooth tethering on/off."""
    ctx = get_action_context()
    app_ctx = ctx.app_context

    if not is_bluetooth_available():
        screens.render_error_screen(
            title="Bluetooth Error",
            message="Bluetooth adapter not found.\nCheck hardware.",
        )
        return

    enabled = get_bool("bluetooth_enabled", default=False)

    if enabled:
        # Turn off
        confirmed = render_confirmation(
            app_ctx,
            title="Disable Bluetooth",
            message="Stop Bluetooth tethering?",
            default=False,
        )

        if not confirmed:
            return

        try:
            if disable_bluetooth_tethering():
                set_bool("bluetooth_enabled", False)
                render_status_screen("Bluetooth Disabled", "Tethering stopped")
            else:
                screens.render_error_screen(
                    title="Error",
                    message=_append_bluetooth_error("Failed to disable Bluetooth"),
                )
        except Exception as e:
            logger.error(f"Error disabling Bluetooth: {e}")
            screens.render_error_screen(
                title="Error",
                message=f"Failed to disable:\n{str(e)}",
                exception=e,
            )
    else:
        # Turn on
        confirmed = render_confirmation(
            app_ctx,
            title="Enable Bluetooth",
            message="Start Bluetooth tethering?",
            default=True,
        )

        if not confirmed:
            return

        try:
            render_status_screen("Starting...", "Enabling Bluetooth PAN")

            if enable_bluetooth_tethering():
                set_bool("bluetooth_enabled", True)

                # Get status to show IP
                status = get_bluetooth_status()
                ip_msg = f"IP: {status.ip_address}" if status.ip_address else "Ready"

                render_status_screen(
                    "Bluetooth Enabled",
                    f"Tethering active\n{ip_msg}\n\nPair from iPhone:\nSettings > Bluetooth",
                )
            else:
                screens.render_error_screen(
                    title="Error",
                    message=_append_bluetooth_error(
                        "Failed to enable Bluetooth.\nCheck logs for details."
                    ),
                )
        except Exception as e:
            logger.error(f"Error enabling Bluetooth: {e}")
            screens.render_error_screen(
                title="Error",
                message=f"Failed to enable:\n{str(e)}",
                exception=e,
            )


def bluetooth_status():
    """Show current Bluetooth status."""
    ctx = get_action_context()
    app_ctx = ctx.app_context

    if not is_bluetooth_available():
        screens.render_error_screen(
            title="Bluetooth Status",
            message="Bluetooth adapter:\nNot found\n\nCheck hardware connection",
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

        render_status_screen("Bluetooth Status", message)
        wait_for_ack()

    except Exception as e:
        logger.error(f"Error getting Bluetooth status: {e}")
        screens.render_error_screen(
            title="Error",
            message=str(e),
            exception=e,
        )


def bluetooth_discoverable():
    """Make device discoverable for pairing."""
    ctx = get_action_context()
    app_ctx = ctx.app_context

    if not is_bluetooth_available():
        screens.render_error_screen(
            title="Bluetooth Error",
            message="Bluetooth adapter not found",
        )
        return

    timeout = get_setting("bluetooth_discoverable_timeout", default=300)

    confirmed = render_confirmation(
        app_ctx,
        title="Make Discoverable",
        message=f"Allow pairing for\n{timeout//60} minutes?",
        default=True,
    )

    if not confirmed:
        return

    try:
        if make_discoverable(timeout):
            device_name = get_setting("bluetooth_device_name", default="RPi USB Cloner")
            render_status_screen(
                "Discoverable",
                f"Device: {device_name}\n\nVisible for {timeout//60} min\n\nPair from:\niPhone Settings >\nBluetooth",
            )
        else:
            screens.render_error_screen(
                title="Error",
                message=_append_bluetooth_error("Failed to enable\ndiscoverable mode"),
            )
    except Exception as e:
        logger.error(f"Error making discoverable: {e}")
        screens.render_error_screen(
            title="Error",
            message=f"Failed:\n{str(e)}",
            exception=e,
        )


def bluetooth_connection_info():
    """Show connection information for accessing web UI."""
    ctx = get_action_context()
    app_ctx = ctx.app_context

    if not is_bluetooth_available():
        screens.render_error_screen(
            title="Bluetooth Error",
            message="Bluetooth adapter not found",
        )
        return

    try:
        status = get_bluetooth_status()

        if not status.pan_active:
            render_status_screen(
                "Connection Info",
                "Bluetooth not active\n\nEnable tethering first",
            )
            wait_for_ack()
            return

        ip = status.ip_address or "192.168.55.1"
        url = f"http://{ip}:8000"

        render_status_screen(
            "Web UI Access",
            f"1. Pair iPhone to Pi\n2. Connect Bluetooth\n3. Open Safari:\n\n{url}",
        )
        wait_for_ack()

    except Exception as e:
        logger.error(f"Error getting connection info: {e}")
        screens.render_error_screen(
            title="Error",
            message=str(e),
            exception=e,
        )


def bluetooth_paired_devices():
    """Show and manage paired devices."""
    ctx = get_action_context()
    app_ctx = ctx.app_context

    if not is_bluetooth_available():
        screens.render_error_screen(
            title="Bluetooth Error",
            message="Bluetooth adapter not found",
        )
        return

    try:
        devices = get_paired_devices()

        if not devices:
            render_status_screen(
                "Paired Devices",
                "No paired devices\n\nMake discoverable to pair",
            )
            wait_for_ack()
            return

        # Show device list
        lines = [f"Found {len(devices)} device(s):\n"]
        for i, device in enumerate(devices, 1):
            status_icon = "✓" if device.connected else " "
            # Truncate name to fit on screen
            name = device.name[:18]
            lines.append(f"{status_icon} {name}")

        message = "\n".join(lines)
        render_status_screen("Paired Devices", message)
        wait_for_ack()

    except Exception as e:
        logger.error(f"Error listing paired devices: {e}")
        screens.render_error_screen(
            title="Error",
            message=str(e),
            exception=e,
        )
