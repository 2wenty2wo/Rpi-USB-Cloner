"""Bluetooth tethering menu definitions."""

from __future__ import annotations

from rpi_usb_cloner.menu.model import MenuItem, MenuScreen
from .. import actions as menu_actions
from . import menu_entry


BLUETOOTH_MENU = MenuScreen(
    screen_id="bluetooth",
    title="BLUETOOTH",
    items=[
        menu_entry("ENABLE/DISABLE", action=menu_actions.bluetooth_toggle),
        menu_entry("STATUS", action=menu_actions.bluetooth_status),
        menu_entry("MAKE DISCOVERABLE", action=menu_actions.bluetooth_discoverable),
        menu_entry("CONNECTION INFO", action=menu_actions.bluetooth_connection_info),
        menu_entry("PAIRED DEVICES", action=menu_actions.bluetooth_paired_devices),
    ],
)
