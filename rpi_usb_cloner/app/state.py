from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple

MENU_COPY = 0
MENU_VIEW = 1
MENU_ERASE = 2
MENU_NONE = -1

CONFIRM_NO = 0
CONFIRM_YES = 1

QUICK_WIPE_MIB = 32
USB_REFRESH_INTERVAL = 2.0
VISIBLE_ROWS = 3
ENABLE_SLEEP = False
SLEEP_TIMEOUT = 30.0


@dataclass
class AppState:
    index: int = MENU_NONE
    usb_list_index: int = 0
    run_once: int = 0
    lcdstart: datetime = field(default_factory=datetime.now)
    last_usb_check: float = 0.0
    last_seen_devices: List[str] = field(default_factory=list)
    last_seen_raw_devices: List[str] = field(default_factory=list)
    last_seen_mount_snapshot: List[Tuple[str, str]] = field(default_factory=list)
