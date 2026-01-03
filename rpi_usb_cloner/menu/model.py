from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class MenuItem:
    label: str
    action: Optional[Callable[[], None]] = None
    submenu: Optional[MenuScreen] = None


@dataclass
class MenuScreen:
    screen_id: str
    title: str
    items: List[MenuItem] = field(default_factory=list)
    status_line: Optional[str] = None


SCREEN_ICONS: Dict[str, str] = {
    "main": chr(57718),
    "settings": chr(57925),
    "develop": "",
    "update": "",
    "power": "",
    "screensaver": "",
    "wifi": "",
    "tools": chr(57580),
    "logs": "",
    "images": chr(57559),
    "drives": chr(58198),
}


def get_screen_icon(screen_id: str) -> Optional[str]:
    return SCREEN_ICONS.get(screen_id)
