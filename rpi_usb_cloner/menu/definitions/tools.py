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
        menu_entry("COMING SOON", action=menu_actions.tools_coming_soon),
    ],
)
