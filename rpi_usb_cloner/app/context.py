from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Dict, List, Optional, Sequence

from rpi_usb_cloner.ui.display import DisplayContext


@dataclass
class LogEntry:
    message: str
    level: str = "info"
    tags: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "message": self.message,
            "level": self.level,
            "tags": list(self.tags),
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
        }


@dataclass
class AppContext:
    display: Optional[DisplayContext] = None
    input_state: Dict[str, bool] = field(default_factory=dict)
    active_drive: Optional[str] = None
    discovered_drives: List[str] = field(default_factory=list)
    log_buffer: Deque[LogEntry] = field(default_factory=lambda: deque(maxlen=100))
    operation_active: bool = False
    allow_back_interrupt: bool = False

    def add_log(
        self,
        message: str | LogEntry,
        *,
        level: str = "info",
        tags: Optional[Sequence[str]] = None,
        timestamp: Optional[datetime] = None,
        source: Optional[str] = None,
    ) -> None:
        if isinstance(message, LogEntry):
            entry = message
        else:
            if not message:
                return
            entry = LogEntry(
                message=message,
                level=level,
                tags=list(tags) if tags else [],
                timestamp=timestamp or datetime.now(),
                source=source,
            )
        if entry.message:
            self.log_buffer.append(entry)
