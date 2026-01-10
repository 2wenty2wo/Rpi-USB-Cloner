"""Settings storage for application configuration."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict


SETTINGS_PATH = Path(
    os.environ.get(
        "RPI_USB_CLONER_SETTINGS_PATH",
        Path.home() / ".config" / "rpi-usb-cloner" / "settings.json",
    )
)
DEFAULT_SETTINGS: Dict[str, Any] = {
    "screensaver_enabled": False,
    "screensaver_mode": "random",
    "screensaver_gif": None,
    "restore_partition_mode": "k0",
    "scroll_refresh_interval": 0.04,
}


@dataclass
class SettingsStore:
    values: Dict[str, Any] = field(default_factory=dict)


settings_store = SettingsStore()


def load_settings() -> None:
    settings_store.values = dict(DEFAULT_SETTINGS)
    if not SETTINGS_PATH.exists():
        return
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(data, dict):
        settings_store.values.update(data)


def save_settings() -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(settings_store.values, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def get_setting(key: str, default: Any | None = None) -> Any:
    return settings_store.values.get(key, default)


def set_setting(key: str, value: Any) -> None:
    settings_store.values[key] = value
    save_settings()


def get_bool(key: str, default: bool = False) -> bool:
    return bool(get_setting(key, default))


def set_bool(key: str, value: bool) -> None:
    set_setting(key, bool(value))


load_settings()
