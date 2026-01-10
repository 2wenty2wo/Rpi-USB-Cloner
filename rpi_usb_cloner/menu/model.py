from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


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


SCREEN_ICONS: dict[str, str] = {
    # Lucide decimal 59059 (layers-plus).
    "main": chr(59059),
    "settings": chr(57925),
    "develop": "",
    "update": "",
    "power": "",
    "screensaver": "",
    "wifi": "",
    "tools": chr(57580),
    "logs": "",
    "images": chr(57559),
    # Lucide decimal 57581 (hard-drive).
    "drives": chr(57581),
    # Lucide decimal 57581 (hard-drive).
    "drive_list": chr(57581),
    # Lucide decimal 57922.
    "icons": chr(57922),
    # Lucide decimal 57629.
    "screens": chr(57629),
}


def get_screen_icon(screen_id: str) -> str | None:
    return SCREEN_ICONS.get(screen_id)
