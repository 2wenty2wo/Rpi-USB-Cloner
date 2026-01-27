"""Drive-related menu definitions."""

from __future__ import annotations

from rpi_usb_cloner.menu.model import MenuScreen

from .. import actions as menu_actions
from . import menu_entry


DRIVE_LIST_MENU: MenuScreen = MenuScreen(
    screen_id="drive_list",
    title="SELECT DRIVE",
)

DRIVES_MENU: MenuScreen = MenuScreen(
    screen_id="drives",
    title="DRIVES",
    items=[
        menu_entry("SELECT DRIVE", submenu=DRIVE_LIST_MENU),
        menu_entry("DRIVE INFO", action=menu_actions.drive_info),
        menu_entry("UNMOUNT DRIVE", action=menu_actions.unmount_drive),
        menu_entry("COPY IMAGES", action=menu_actions.copy_images),
        menu_entry("FORMAT DRIVE", action=menu_actions.format_drive),
        menu_entry("ERASE DRIVE", action=menu_actions.erase_drive),
        menu_entry("CREATE REPO DRIVE", action=menu_actions.create_repo_drive),
    ],
)
