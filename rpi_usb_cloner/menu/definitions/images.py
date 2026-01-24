"""Image-related menu definitions."""

from __future__ import annotations

from rpi_usb_cloner.menu.model import MenuScreen

from .. import actions as menu_actions
from . import menu_entry


IMAGES_MENU = MenuScreen(
    screen_id="images",
    title="IMAGES",
    items=[
        menu_entry("BACKUP IMAGE", action=menu_actions.backup_image),
        menu_entry("WRITE IMAGE", action=menu_actions.write_image),
    ],
)
