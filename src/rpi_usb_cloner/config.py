import os

DEBUG = False
CLONE_MODE = os.environ.get("CLONE_MODE", "smart").lower()
USB_REFRESH_INTERVAL = 2.0
VISIBLE_ROWS = 3
QUICK_WIPE_MIB = 32


def log_debug(message: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {message}")
