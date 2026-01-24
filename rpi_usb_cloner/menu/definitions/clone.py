"""Clone-related menu definitions (backup, restore, copy, verify)."""

from __future__ import annotations

from rpi_usb_cloner.menu.model import MenuScreen

from .. import actions as menu_actions
from . import menu_entry


CLONE_MENU: MenuScreen = MenuScreen(
    screen_id="clone",
    title="CLONE",
    items=[
        menu_entry("DRIVE → DRIVE", action=menu_actions.copy_drive),
        menu_entry("BACKUP → IMAGE", action=menu_actions.backup_image),
        menu_entry("RESTORE ← IMAGE", action=menu_actions.write_image),
        menu_entry("VERIFY CLONE", action=menu_actions.verify_clone),
    ],
)
