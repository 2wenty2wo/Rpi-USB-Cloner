from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from rpi_usb_cloner.ui.display import DisplayContext


@dataclass
class AppContext:
    display: DisplayContext | None = None
    input_state: dict[str, bool] = field(default_factory=dict)
    active_drive: str | None = None
    discovered_drives: list[str] = field(default_factory=list)
    log_buffer: deque[str] = field(default_factory=lambda: deque(maxlen=100))
    operation_active: bool = False
    allow_back_interrupt: bool = False

    def add_log(self, message: str) -> None:
        if message:
            self.log_buffer.append(message)
