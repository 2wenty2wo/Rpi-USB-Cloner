from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from rpi_usb_cloner.ui.icons import SCREEN_ICONS


@dataclass
class MenuItem:
    """A menu item with optional toggle state.

    Attributes:
        label: Display text for the menu item.
        action: Callable to execute when item is selected.
        submenu: Submenu to navigate to when item is selected.
        toggle: Optional boolean for toggle switch display.
            - None: No toggle shown (default)
            - True: Toggle shown in ON position
            - False: Toggle shown in OFF position
    """

    label: str
    action: Callable[[], None] | None = None
    submenu: MenuScreen | None = None
    toggle: bool | None = None


@dataclass
class MenuScreen:
    screen_id: str
    title: str
    items: list[MenuItem] = field(default_factory=list)
    status_line: str | None = None


def get_screen_icon(screen_id: str) -> str | None:
    return SCREEN_ICONS.get(screen_id)
