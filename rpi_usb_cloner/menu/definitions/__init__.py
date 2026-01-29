"""Menu hierarchy definitions.

Edit files in this directory to adjust menu labels or structure.
"""

from __future__ import annotations

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


# Import all menu definitions after helper setup to avoid circular dependencies.
from .clone import CLONE_MENU  # noqa: E402
from .drives import DRIVE_LIST_MENU, DRIVES_MENU  # noqa: E402
from .main import MAIN_MENU  # noqa: E402
from .settings import (  # noqa: E402
    ADVANCED_MENU,
    CONNECTIVITY_MENU,
    DEVELOP_MENU,
    DISPLAY_MENU,
    ICONS_MENU,
    POWER_MENU,
    SCREENS_MENU,
    SCREENSAVER_MENU,
    SETTINGS_MENU,
    SYSTEM_MENU,
)
from .tools import TOOLS_MENU  # noqa: E402


# Collect all screens for navigation
SCREENS = _collect_screens(MAIN_MENU)

# Export all public items
__all__ = [
    "menu_entry",
    "MAIN_MENU",
    "DRIVES_MENU",
    "DRIVE_LIST_MENU",
    "CLONE_MENU",
    "TOOLS_MENU",
    "SETTINGS_MENU",
    "CONNECTIVITY_MENU",
    "DISPLAY_MENU",
    "SYSTEM_MENU",
    "ADVANCED_MENU",
    "SCREENSAVER_MENU",
    "POWER_MENU",
    "DEVELOP_MENU",
    "SCREENS_MENU",
    "ICONS_MENU",
    "SCREENS",
]
