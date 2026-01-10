"""Tools menu actions."""

from __future__ import annotations

from rpi_usb_cloner.actions import tools_actions
from rpi_usb_cloner.ui import screens

from . import get_action_context


def tools_coming_soon() -> None:
    tools_actions.coming_soon()


def view_logs() -> None:
    context = get_action_context()
    screens.show_logs(context.app_context)
