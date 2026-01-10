"""Menu hierarchy definitions.

Edit files in this directory to adjust menu labels or structure.
"""

from __future__ import annotations

from typing import Dict, Optional

from rpi_usb_cloner.menu.model import MenuItem, MenuScreen


def menu_entry(
    label: str,
    *,
    submenu: MenuScreen | None = None,
    action=None,
) -> MenuItem:
    if (submenu is None) == (action is None):
        raise ValueError("Menu entries must define exactly one of submenu or action.")
    return MenuItem(label=label, submenu=submenu, action=action)


def _collect_screens(root: MenuScreen) -> dict[str, MenuScreen]:
    screens: dict[str, MenuScreen] = {}

    def walk(screen: MenuScreen) -> None:
        if screen.screen_id in screens:
            return
        screens[screen.screen_id] = screen
        for item in screen.items:
            if item.submenu:
                walk(item.submenu)

    walk(root)
    return screens


# Import all menu definitions
from .drives import DRIVE_LIST_MENU, DRIVES_MENU
from .images import IMAGES_MENU
from .main import MAIN_MENU
from .settings import (
    DEVELOP_MENU,
    ICONS_MENU,
    POWER_MENU,
    SCREENS_MENU,
    SCREENSAVER_MENU,
    SETTINGS_MENU,
)
from .tools import TOOLS_MENU

# Collect all screens for navigation
SCREENS = _collect_screens(MAIN_MENU)

# Export all public items
__all__ = [
    "menu_entry",
    "MAIN_MENU",
    "DRIVES_MENU",
    "DRIVE_LIST_MENU",
    "IMAGES_MENU",
    "TOOLS_MENU",
    "SETTINGS_MENU",
    "SCREENSAVER_MENU",
    "POWER_MENU",
    "DEVELOP_MENU",
    "SCREENS_MENU",
    "ICONS_MENU",
    "SCREENS",
]
