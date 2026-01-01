"""Settings storage for application configuration."""
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class SettingsStore:
    values: Dict[str, Any] = field(default_factory=dict)


settings_store = SettingsStore()
