from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from rpi_usb_cloner.ui.icons import SCREEN_ICONS


@dataclass
class MenuItem:
    label: str
    action: Callable[[], None] | None = None
    submenu: MenuScreen | None = None


@dataclass
class MenuScreen:
    screen_id: str
    title: str
    items: list[MenuItem] = field(default_factory=list)
    status_line: str | None = None


def get_screen_icon(screen_id: str) -> str | None:
    return SCREEN_ICONS.get(screen_id)
