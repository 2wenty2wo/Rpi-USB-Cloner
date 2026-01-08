"""Drive-related menu definitions."""

from __future__ import annotations

from rpi_usb_cloner.menu.model import MenuScreen
from .. import actions as menu_actions
from . import menu_entry


DRIVE_LIST_MENU = MenuScreen(
    screen_id="drive_list",
    title="SELECT DRIVE",
)

DRIVES_MENU = MenuScreen(
    screen_id="drives",
    title="DRIVES",
    items=[
        menu_entry("SELECT DRIVE", submenu=DRIVE_LIST_MENU),
        menu_entry("COPY DRIVE", action=menu_actions.copy_drive),
        menu_entry("DRIVE INFO", action=menu_actions.drive_info),
        menu_entry("ERASE DRIVE", action=menu_actions.erase_drive),
    ],
)
