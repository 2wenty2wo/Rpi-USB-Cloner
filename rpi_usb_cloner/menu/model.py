from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from rpi_usb_cloner.ui.icons import SCREEN_ICONS


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


def get_screen_icon(screen_id: str) -> Optional[str]:
    return SCREEN_ICONS.get(screen_id)
