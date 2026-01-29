"""Tests for toggle switch icons module."""

import pytest
from PIL import Image

from rpi_usb_cloner.ui.toggle import (
    TOGGLE_HEIGHT,
    TOGGLE_OFF_MARKER,
    TOGGLE_ON_MARKER,
    TOGGLE_WIDTH,
    clear_cache,
    format_toggle_label,
    get_toggle,
    get_toggle_off,
    get_toggle_on,
    has_toggle_marker,
    parse_toggle_label,
)


class TestToggleMarkers:
    """Tests for toggle marker formatting and parsing."""

    def test_format_toggle_label_on(self):
        """Test formatting label with ON toggle."""
        result = format_toggle_label("SCREENSAVER", True)
        assert result == f"SCREENSAVER {TOGGLE_ON_MARKER}"

    def test_format_toggle_label_off(self):
        """Test formatting label with OFF toggle."""
        result = format_toggle_label("WEB SERVER", False)
        assert result == f"WEB SERVER {TOGGLE_OFF_MARKER}"

    def test_parse_toggle_label_on(self):
        """Test parsing label with ON toggle marker."""
        label = f"SCREENSAVER {TOGGLE_ON_MARKER}"
        clean_label, toggle_state = parse_toggle_label(label)
        assert clean_label == "SCREENSAVER"
        assert toggle_state is True

    def test_parse_toggle_label_off(self):
        """Test parsing label with OFF toggle marker."""
        label = f"WEB SERVER {TOGGLE_OFF_MARKER}"
        clean_label, toggle_state = parse_toggle_label(label)
        assert clean_label == "WEB SERVER"
        assert toggle_state is False

    def test_parse_toggle_label_no_marker(self):
        """Test parsing label without toggle marker."""
        label = "SETTINGS"
        clean_label, toggle_state = parse_toggle_label(label)
        assert clean_label == "SETTINGS"
        assert toggle_state is None

    def test_has_toggle_marker_true(self):
        """Test detecting toggle marker."""
        assert has_toggle_marker(f"TEST {TOGGLE_ON_MARKER}") is True
        assert has_toggle_marker(f"TEST {TOGGLE_OFF_MARKER}") is True

    def test_has_toggle_marker_false(self):
        """Test label without toggle marker."""
        assert has_toggle_marker("SETTINGS") is False
        assert has_toggle_marker("TOGGLE: ON") is False

    def test_roundtrip_on(self):
        """Test formatting then parsing with ON state."""
        original = "MY SETTING"
        formatted = format_toggle_label(original, True)
        clean_label, toggle_state = parse_toggle_label(formatted)
        assert clean_label == original
        assert toggle_state is True

    def test_roundtrip_off(self):
        """Test formatting then parsing with OFF state."""
        original = "MY SETTING"
        formatted = format_toggle_label(original, False)
        clean_label, toggle_state = parse_toggle_label(formatted)
        assert clean_label == original
        assert toggle_state is False


class TestToggleImages:
    """Tests for toggle image loading."""

    def test_get_toggle_on_returns_image(self):
        """Test that get_toggle_on returns a valid image."""
        img = get_toggle_on()
        assert isinstance(img, Image.Image)
        assert img.mode == "1"
        assert img.size == (TOGGLE_WIDTH, TOGGLE_HEIGHT)

    def test_get_toggle_off_returns_image(self):
        """Test that get_toggle_off returns a valid image."""
        img = get_toggle_off()
        assert isinstance(img, Image.Image)
        assert img.mode == "1"
        assert img.size == (TOGGLE_WIDTH, TOGGLE_HEIGHT)

    def test_get_toggle_with_true(self):
        """Test get_toggle with True returns ON image."""
        img = get_toggle(True)
        assert isinstance(img, Image.Image)
        assert img.size == (TOGGLE_WIDTH, TOGGLE_HEIGHT)

    def test_get_toggle_with_false(self):
        """Test get_toggle with False returns OFF image."""
        img = get_toggle(False)
        assert isinstance(img, Image.Image)
        assert img.size == (TOGGLE_WIDTH, TOGGLE_HEIGHT)

    def test_images_are_different(self):
        """Test that ON and OFF images are different."""
        on_img = get_toggle_on()
        off_img = get_toggle_off()
        # Compare pixel data - they should be different
        # Use tobytes() for comparison as getdata() is deprecated in Pillow 14
        on_data = on_img.tobytes()
        off_data = off_img.tobytes()
        assert on_data != off_data

    def test_clear_cache(self):
        """Test that clear_cache doesn't raise."""
        # Load images first
        get_toggle_on()
        get_toggle_off()
        # Clear should not raise
        clear_cache()
        # Images should still load after clearing
        img = get_toggle_on()
        assert isinstance(img, Image.Image)


class TestToggleDimensions:
    """Tests for toggle dimension constants."""

    def test_toggle_width(self):
        """Test toggle width constant."""
        assert TOGGLE_WIDTH == 12

    def test_toggle_height(self):
        """Test toggle height constant."""
        assert TOGGLE_HEIGHT == 5
