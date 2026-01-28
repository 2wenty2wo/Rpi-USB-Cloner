"""Device operation lock to prevent web UI interference during disk operations.

This module provides a simple lock mechanism that pauses web UI filesystem
scanning during disk-intensive operations like format, erase, and clone.

Usage:
    from rpi_usb_cloner.storage.device_lock import device_operation, is_operation_active

    # In disk operation code:
    with device_operation("sdb"):
        # Perform format/erase/clone
        ...

    # In web UI polling code:
    if is_operation_active():
        # Skip filesystem scanning, use cached data
        ...
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Generator

from rpi_usb_cloner.logging import LoggerFactory


log = LoggerFactory.for_clone()

# Lock for thread-safe access to operation state
_lock = threading.Lock()

# Current operation state
_active_device: str | None = None
_operation_count: int = 0


@contextmanager
def device_operation(device_name: str) -> Generator[None, None, None]:
    """Context manager that signals a disk operation is in progress.

    While inside this context, web UI handlers should skip filesystem
    scanning to avoid "device busy" errors during format/erase/clone.

    Args:
        device_name: Name of the device being operated on (e.g., "sdb")

    Example:
        with device_operation("sdb"):
            format_device(...)
    """
    global _active_device, _operation_count

    with _lock:
        _operation_count += 1
        _active_device = device_name
        log.debug(f"Device operation started on {device_name}")

    try:
        yield
    finally:
        with _lock:
            _operation_count -= 1
            if _operation_count == 0:
                _active_device = None
            log.debug(f"Device operation completed on {device_name}")


def is_operation_active() -> bool:
    """Check if any disk operation is currently in progress.

    Returns:
        True if a disk operation is active, False otherwise
    """
    with _lock:
        return _operation_count > 0


def get_active_device() -> str | None:
    """Get the name of the device currently being operated on.

    Returns:
        Device name (e.g., "sdb") or None if no operation is active
    """
    with _lock:
        return _active_device
