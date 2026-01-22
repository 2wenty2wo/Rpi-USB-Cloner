"""Tools menu definitions."""

from __future__ import annotations

from rpi_usb_cloner.menu.model import MenuScreen

from .. import actions as menu_actions
from . import menu_entry


TOOLS_MENU = MenuScreen(
    screen_id="tools",
    title="TOOLS",
    items=[
        menu_entry("LOGS", action=menu_actions.view_logs),
        menu_entry("FILE BROWSER", action=menu_actions.file_browser),
    ],
)
