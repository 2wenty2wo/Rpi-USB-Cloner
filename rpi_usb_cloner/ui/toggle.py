"""Toggle switch icons for boolean settings.

This module provides toggle switch icons that can be displayed inline
with menu item text for ON/OFF boolean settings.

Toggle icons are 12x5 pixels, suitable for inline display with the
silkscreen font on the 128x64 OLED display.

Usage in menu labels:
    from rpi_usb_cloner.ui.toggle import format_toggle_label

    # In menu_builders.py
    label = format_toggle_label("SCREENSAVER", enabled)
    # Returns: "SCREENSAVER {{TOGGLE:ON}}" or "SCREENSAVER {{TOGGLE:OFF}}"

The renderer detects these markers and replaces them with toggle images.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from PIL import Image

# Asset paths
ASSETS_PATH = Path(__file__).parent / "assets"
TOGGLE_ON_PATH = ASSETS_PATH / "toggle-on.png"
TOGGLE_OFF_PATH = ASSETS_PATH / "toggle-off.png"

# Toggle image dimensions
TOGGLE_WIDTH = 12
TOGGLE_HEIGHT = 5

# Toggle markers for label strings
# These markers are detected by the renderer and replaced with toggle images
TOGGLE_ON_MARKER = "{{TOGGLE:ON}}"
TOGGLE_OFF_MARKER = "{{TOGGLE:OFF}}"
TOGGLE_MARKER_PATTERN = re.compile(r"\{\{TOGGLE:(ON|OFF)\}\}")


def format_toggle_label(label: str, state: bool) -> str:
    """Format a label with a toggle marker.

    Args:
        label: The base label text (e.g., "SCREENSAVER").
        state: True for ON, False for OFF.

    Returns:
        Label with toggle marker appended (e.g., "SCREENSAVER {{TOGGLE:ON}}").
    """
    marker = TOGGLE_ON_MARKER if state else TOGGLE_OFF_MARKER
    return f"{label} {marker}"


def parse_toggle_label(label: str) -> tuple[str, bool | None]:
    """Parse a label to extract text and toggle state.

    Args:
        label: Label that may contain a toggle marker.

    Returns:
        Tuple of (clean_label, toggle_state).
        toggle_state is None if no marker found, True for ON, False for OFF.
    """
    match = TOGGLE_MARKER_PATTERN.search(label)
    if not match:
        return label, None
    clean_label = label[: match.start()].rstrip()
    toggle_state = match.group(1) == "ON"
    return clean_label, toggle_state


def has_toggle_marker(label: str) -> bool:
    """Check if a label contains a toggle marker.

    Args:
        label: Label to check.

    Returns:
        True if label contains a toggle marker.
    """
    return TOGGLE_MARKER_PATTERN.search(label) is not None


@lru_cache(maxsize=2)
def _load_toggle_image(on: bool) -> Image.Image:
    """Load and cache toggle image.

    Args:
        on: True for toggle-on, False for toggle-off.

    Returns:
        PIL Image in mode "1" (1-bit monochrome) for OLED display.
    """
    path = TOGGLE_ON_PATH if on else TOGGLE_OFF_PATH
    if not path.exists():
        # Return a simple fallback rectangle if image not found
        img = Image.new("1", (TOGGLE_WIDTH, TOGGLE_HEIGHT), 0)
        return img
    return Image.open(path).convert("1")


def get_toggle_on() -> Image.Image:
    """Get the toggle-on image.

    Returns:
        PIL Image (12x5, mode "1") showing toggle in ON position.
    """
    return _load_toggle_image(True)


def get_toggle_off() -> Image.Image:
    """Get the toggle-off image.

    Returns:
        PIL Image (12x5, mode "1") showing toggle in OFF position.
    """
    return _load_toggle_image(False)


def get_toggle(state: bool) -> Image.Image:
    """Get toggle image for given state.

    Args:
        state: True for ON, False for OFF.

    Returns:
        PIL Image (12x5, mode "1") showing toggle in appropriate position.
    """
    return _load_toggle_image(state)


def clear_cache() -> None:
    """Clear the cached toggle images.

    Call this if the toggle images are updated at runtime.
    """
    _load_toggle_image.cache_clear()
