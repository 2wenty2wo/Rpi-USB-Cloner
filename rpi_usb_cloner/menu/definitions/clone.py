"""Clone-related menu definitions (backup, restore, copy, verify)."""

from __future__ import annotations

from rpi_usb_cloner.menu.model import MenuScreen
from rpi_usb_cloner.ui.icons import ARROW_LEFT, ARROW_RIGHT

from .. import actions as menu_actions
from . import menu_entry


CLONE_MENU: MenuScreen = MenuScreen(
    screen_id="clone",
    title="CLONE",
    items=[
        menu_entry(f"DRIVE {ARROW_RIGHT} DRIVE", action=menu_actions.copy_drive),
        menu_entry(f"BACKUP {ARROW_RIGHT} IMAGE", action=menu_actions.backup_image),
        menu_entry(f"RESTORE {ARROW_LEFT} IMAGE", action=menu_actions.write_image),
        menu_entry("VERIFY CLONE", action=menu_actions.verify_clone),
    ],
)
