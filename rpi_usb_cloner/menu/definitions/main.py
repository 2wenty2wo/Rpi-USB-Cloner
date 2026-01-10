"""Main menu definition."""

from __future__ import annotations

from rpi_usb_cloner.menu.model import MenuScreen

from . import menu_entry
from .drives import DRIVES_MENU
from .images import IMAGES_MENU
from .settings import SETTINGS_MENU
from .tools import TOOLS_MENU

MAIN_MENU = MenuScreen(
    screen_id="main",
    title="Rpi USB CLONER",
    items=[
        menu_entry("DRIVES", submenu=DRIVES_MENU),
        menu_entry("IMAGES", submenu=IMAGES_MENU),
        menu_entry("TOOLS", submenu=TOOLS_MENU),
        menu_entry("SETTINGS", submenu=SETTINGS_MENU),
    ],
)
