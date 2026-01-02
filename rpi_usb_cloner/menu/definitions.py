"""Menu hierarchy definitions.

Edit this file to adjust menu labels or structure; it is the single source of truth for menu edits.
"""

from __future__ import annotations

from typing import Dict, Optional

from rpi_usb_cloner.menu.model import MenuItem, MenuScreen
from . import actions as menu_actions


def menu_entry(
    label: str,
    *,
    submenu: Optional[MenuScreen] = None,
    action=None,
) -> MenuItem:
    if (submenu is None) == (action is None):
        raise ValueError("Menu entries must define exactly one of submenu or action.")
    return MenuItem(label=label, submenu=submenu, action=action)


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

IMAGES_MENU = MenuScreen(
    screen_id="images",
    title="IMAGES",
    items=[
        menu_entry("BACKUP IMAGE", action=menu_actions.backup_image),
        menu_entry("WRITE IMAGE", action=menu_actions.write_image),
        menu_entry("COMING SOON", action=menu_actions.images_coming_soon),
    ],
)

TOOLS_MENU = MenuScreen(
    screen_id="tools",
    title="TOOLS",
    items=[
        menu_entry("LOGS", action=menu_actions.view_logs),
        menu_entry("COMING SOON", action=menu_actions.tools_coming_soon),
    ],
)

DEVELOP_MENU = MenuScreen(
    screen_id="develop",
    title="DEVELOP",
    items=[
        menu_entry("KEYBOARD", action=menu_actions.keyboard_test),
    ],
)

POWER_MENU = MenuScreen(
    screen_id="power",
    title="POWER",
    items=[
        menu_entry("RESTART RPI-USB-CLONER", action=menu_actions.restart_service),
        menu_entry("STOP RPI-USB-CLONER", action=menu_actions.stop_service),
        menu_entry("RESTART SYSTEM", action=menu_actions.restart_system),
        menu_entry("SHUTDOWN SYSTEM", action=menu_actions.shutdown_system),
    ],
)

SETTINGS_MENU = MenuScreen(
    screen_id="settings",
    title="SETTINGS",
    items=[
        menu_entry("WIFI", action=menu_actions.wifi_settings),
        menu_entry("SCREENSAVER", action=menu_actions.screensaver_settings),
        menu_entry("DEVELOP", submenu=DEVELOP_MENU),
        menu_entry("POWER", submenu=POWER_MENU),
    ],
)

MAIN_MENU = MenuScreen(
    screen_id="main",
    title="MAIN MENU",
    items=[
        menu_entry("DRIVES", submenu=DRIVES_MENU),
        menu_entry("IMAGES", submenu=IMAGES_MENU),
        menu_entry("TOOLS", submenu=TOOLS_MENU),
        menu_entry("SETTINGS", submenu=SETTINGS_MENU),
    ],
)


def _collect_screens(root: MenuScreen) -> Dict[str, MenuScreen]:
    screens: Dict[str, MenuScreen] = {}

    def walk(screen: MenuScreen) -> None:
        if screen.screen_id in screens:
            return
        screens[screen.screen_id] = screen
        for item in screen.items:
            if item.submenu:
                walk(item.submenu)

    walk(root)
    return screens


SCREENS = _collect_screens(MAIN_MENU)
