from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from rpi_usb_cloner.ui.display import DisplayContext


@dataclass
class AppContext:
    display: Optional[DisplayContext] = None
    input_state: Dict[str, bool] = field(default_factory=dict)
    active_drive: Optional[str] = None
    discovered_drives: List[str] = field(default_factory=list)
    log_buffer: Deque[str] = field(default_factory=lambda: deque(maxlen=100))
    operation_active: bool = False
    allow_back_interrupt: bool = False

    def add_log(self, message: str) -> None:
        if message:
            self.log_buffer.append(message)
