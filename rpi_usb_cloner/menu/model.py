from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MenuItem:
    label: str
    action: Optional[str] = None
    next_screen: Optional[str] = None


@dataclass
class MenuScreen:
    screen_id: str
    title: str
    items: List[MenuItem] = field(default_factory=list)
    status_line: Optional[str] = None
