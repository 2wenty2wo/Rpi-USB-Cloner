"""
Tests for rpi_usb_cloner.ui.display module.

This test suite covers:
- Display context initialization
- Font loading (truetype and default)
- Text rendering and measurement
- Text wrapping and truncation
- Title rendering with icons
- Paginated text rendering
- Display line functions
- Screenshot capture
- Display dirty flag management
- Thread-safe display operations
"""

import threading
from pathlib import Path
from unittest.mock import Mock, MagicMock, call, patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from rpi_usb_cloner.ui import display


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def mock_ssd1306_device():
    """Fixture providing a mock SSD1306 OLED device."""
    device = MagicMock()
    device.width = 128
    device.height = 64
    device.display = MagicMock()
    return device


@pytest.fixture
def mock_i2c_interface():
    """Fixture providing a mock I2C interface."""
    interface = MagicMock()
    return interface


@pytest.fixture
def mock_display_context(mock_ssd1306_device):
    """Fixture providing a complete display context."""
    context = display.DisplayContext(
        disp=mock_ssd1306_device,
        draw=ImageDraw.Draw(Image.new('1', (128, 64))),
        image=Image.new('1', (128, 64)),
        fonts={
            "title": ImageFont.load_default(),
            "items": ImageFont.load_default(),
            "footer": ImageFont.load_default(),
        },
        width=128,
        height=64,
        x=11,
        top=0,
        bottom=64,
        fontcopy=ImageFont.load_default(),
        fontinsert=ImageFont.load_default(),
        fontdisks=ImageFont.load_default(),
        fontmain=ImageFont.load_default(),
    )
    return context


@pytest.fixture(autouse=True)
def reset_display_context():
    """Auto-use fixture to reset display context before each test."""
    display._display_context = None
    display._display_dirty = False
    yield
    display._display_context = None
    display._display_dirty = False


@pytest.fixture(autouse=True)
def mock_hardware_dependencies(mocker):
    """Auto-use fixture that mocks hardware dependencies."""
    # Mock luma.oled
    mocker.patch("rpi_usb_cloner.ui.display.ssd1306")
    mocker.patch("rpi_usb_cloner.ui.display.i2c")

    # Mock font paths
    mocker.patch("rpi_usb_cloner.ui.display.Path")

    # Mock settings
    mocker.patch("rpi_usb_cloner.ui.display.get_setting", return_value=None)


# ==============================================================================
# Display Context Tests
# ==============================================================================

class TestDisplayContext:
    """Tests for DisplayContext dataclass."""

    def test_create_display_context(self, mock_ssd1306_device):
        """Test creating a display context."""
        image = Image.new('1', (128, 64))
        draw = ImageDraw.Draw(image)

        context = display.DisplayContext(
            disp=mock_ssd1306_device,
            draw=draw,
            image=image,
            fonts={},
            width=128,
            height=64,
            x=11,
            top=0,
            bottom=64,
            fontcopy=ImageFont.load_default(),
            fontinsert=ImageFont.load_default(),
            fontdisks=ImageFont.load_default(),
            fontmain=ImageFont.load_default(),
        )

        assert context.width == 128
        assert context.height == 64
        assert context.disp == mock_ssd1306_device
        assert context.image == image

    def test_display_context_singleton(self, mock_display_context):
        """Test that display context works as singleton."""
        display.set_display_context(mock_display_context)

        retrieved = display.get_display_context()

        assert retrieved == mock_display_context


class TestDisplayInitialization:
    """Tests for display initialization functions."""

    def test_initialize_display(self, mocker, mock_ssd1306_device, mock_i2c_interface):
        """Test display initialization."""
        mock_ssd1306_class = mocker.patch("rpi_usb_cloner.ui.display.ssd1306")
        mock_ssd1306_class.return_value = mock_ssd1306_device

        mock_i2c_class = mocker.patch("rpi_usb_cloner.ui.display.i2c")
        mock_i2c_class.return_value = mock_i2c_interface

        # Mock font loading
        mocker.patch("rpi_usb_cloner.ui.display.ImageFont.truetype", return_value=ImageFont.load_default())

        context = display.initialize_display()

        assert context is not None
        assert context.width == 128
        assert context.height == 64

    def test_init_display_alias(self, mocker, mock_ssd1306_device):
        """Test that init_display is an alias for initialize_display."""
        mock_init = mocker.patch("rpi_usb_cloner.ui.display.initialize_display")
        mock_init.return_value = MagicMock()

        result = display.init_display()

        mock_init.assert_called_once()


# ==============================================================================
# Text Measurement Tests
# ==============================================================================

class TestTextMeasurement:
    """Tests for text measurement functions."""

    def test_get_line_height(self):
        """Test getting line height from font."""
        font = ImageFont.load_default()

        height = display._get_line_height(font)

        assert height > 0
        assert isinstance(height, int)

    def test_measure_text_width(self, mock_display_context):
        """Test measuring text width."""
        font = ImageFont.load_default()

        width = display._measure_text_width(mock_display_context.draw, "Test Text", font)

        assert width > 0
        assert isinstance(width, int)

    def test_measure_text_width_empty_string(self, mock_display_context):
        """Test measuring width of empty string."""
        font = ImageFont.load_default()

        width = display._measure_text_width(mock_display_context.draw, "", font)

        assert width >= 0


# ==============================================================================
# Text Wrapping and Truncation Tests
# ==============================================================================

class TestTextTruncation:
    """Tests for text truncation functions."""

    def test_truncate_short_text(self, mock_display_context):
        """Test truncating text that fits within width."""
        font = ImageFont.load_default()
        text = "Short"
        max_width = 1000  # Large width

        result = display._truncate_text(mock_display_context.draw, text, font, max_width)

        assert result == "Short"

    def test_truncate_long_text(self, mock_display_context):
        """Test truncating text that exceeds width."""
        font = ImageFont.load_default()
        text = "This is a very long text that needs to be truncated"
        max_width = 50  # Small width

        result = display._truncate_text(mock_display_context.draw, text, font, max_width)

        # Should be truncated with ellipsis
        assert len(result) < len(text)
        assert "..." in result or result.endswith("…")

    def test_truncate_text_exact_fit(self, mock_display_context):
        """Test truncating text that exactly fits."""
        font = ImageFont.load_default()
        text = "Fit"

        # Get actual width of text
        text_width = display._measure_text_width(mock_display_context.draw, text, font)

        result = display._truncate_text(mock_display_context.draw, text, font, text_width)

        assert result == text


class TestTextWrapping:
    """Tests for text wrapping functions."""

    def test_wrap_short_lines(self, mock_display_context):
        """Test wrapping lines that fit within width."""
        font = ImageFont.load_default()
        lines = ["Short", "Lines", "Here"]
        max_width = 1000

        result = display._wrap_lines_to_width(lines, font, max_width)

        assert result == lines

    def test_wrap_long_lines(self, mock_display_context):
        """Test wrapping lines that exceed width."""
        font = ImageFont.load_default()
        lines = ["This is a very long line that needs to be wrapped to fit"]
        max_width = 50

        result = display._wrap_lines_to_width(lines, font, max_width)

        # Should have more lines after wrapping
        assert len(result) > len(lines)

    def test_wrap_empty_lines(self, mock_display_context):
        """Test wrapping empty lines list."""
        font = ImageFont.load_default()
        lines = []
        max_width = 100

        result = display._wrap_lines_to_width(lines, font, max_width)

        assert result == []

    def test_split_long_word(self):
        """Test splitting long words across lines."""
        font = ImageFont.load_default()
        word = "verylongwordthatcannotfit"
        max_width = 30

        result = display._split_long_word(word, font, max_width)

        # Should split into multiple parts
        assert len(result) >= 1
        assert isinstance(result, list)


# ==============================================================================
# Display Lines Tests
# ==============================================================================

class TestDisplayLines:
    """Tests for display_lines() function."""

    def test_display_simple_lines(self, mocker, mock_display_context):
        """Test displaying simple text lines."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        display.display_lines(["Line 1", "Line 2", "Line 3"])

        # Should call display on the device
        assert mock_display_context.disp.display.called

    def test_display_max_lines(self, mocker, mock_display_context):
        """Test displaying maximum number of lines (6)."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        lines = ["Line 1", "Line 2", "Line 3", "Line 4", "Line 5", "Line 6"]
        display.display_lines(lines)

        assert mock_display_context.disp.display.called

    def test_display_too_many_lines(self, mocker, mock_display_context):
        """Test displaying more than 6 lines (should truncate)."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        lines = ["Line 1", "Line 2", "Line 3", "Line 4", "Line 5", "Line 6", "Line 7", "Line 8"]
        display.display_lines(lines)

        # Should complete without error (may truncate to 6 lines)
        assert mock_display_context.disp.display.called

    def test_display_empty_lines(self, mocker, mock_display_context):
        """Test displaying empty lines list."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        display.display_lines([])

        assert mock_display_context.disp.display.called


class TestClearDisplay:
    """Tests for clear_display() function."""

    def test_clear_display(self, mocker, mock_display_context):
        """Test clearing the display."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        display.clear_display()

        # Should call display on the device
        assert mock_display_context.disp.display.called


# ==============================================================================
# Title Rendering Tests
# ==============================================================================

class TestDrawTitleWithIcon:
    """Tests for draw_title_with_icon() function."""

    def test_draw_title_without_icon(self, mocker, mock_display_context):
        """Test drawing title without icon."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        layout = display.draw_title_with_icon("Test Title")

        assert layout is not None
        assert layout.content_top > 0

    def test_draw_title_with_icon(self, mocker, mock_display_context):
        """Test drawing title with icon."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)
        mocker.patch("rpi_usb_cloner.ui.display._get_lucide_font", return_value=ImageFont.load_default())

        layout = display.draw_title_with_icon(
            "Test Title",
            icon="icon_char",
        )

        assert layout is not None
        assert layout.content_top > 0

    def test_draw_title_with_custom_font(self, mocker, mock_display_context):
        """Test drawing title with custom font."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        custom_font = ImageFont.load_default()
        layout = display.draw_title_with_icon(
            "Test Title",
            title_font=custom_font,
        )

        assert layout is not None

    def test_draw_title_with_custom_draw(self, mocker, mock_display_context):
        """Test drawing title with custom draw object."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        custom_draw = ImageDraw.Draw(Image.new('1', (128, 64)))
        layout = display.draw_title_with_icon(
            "Test Title",
            draw=custom_draw,
        )

        assert layout is not None


# ==============================================================================
# Paginated Rendering Tests
# ==============================================================================

class TestRenderPaginatedLines:
    """Tests for render_paginated_lines() function."""

    def test_render_single_page(self, mocker, mock_display_context):
        """Test rendering lines that fit on one page."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        lines = ["Line 1", "Line 2", "Line 3"]
        total_pages, current_page = display.render_paginated_lines(
            title="Test",
            lines=lines,
            page_index=0,
        )

        assert total_pages >= 1
        assert current_page >= 0

    def test_render_multiple_pages(self, mocker, mock_display_context):
        """Test rendering lines that span multiple pages."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        # Create many lines to force pagination
        lines = [f"Line {i}" for i in range(20)]
        total_pages, current_page = display.render_paginated_lines(
            title="Test",
            lines=lines,
            page_index=0,
        )

        assert total_pages >= 1

    def test_render_second_page(self, mocker, mock_display_context):
        """Test rendering a specific page."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        lines = [f"Line {i}" for i in range(20)]
        total_pages, current_page = display.render_paginated_lines(
            title="Test",
            lines=lines,
            page_index=1,
        )

        assert current_page == 1


# ==============================================================================
# Screenshot Tests
# ==============================================================================

class TestScreenshot:
    """Tests for screenshot capture functions."""

    def test_capture_screenshot(self, mocker, mock_display_context, tmp_path):
        """Test capturing a screenshot."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)
        mocker.patch("rpi_usb_cloner.ui.display.settings.get_setting", return_value=str(tmp_path))

        screenshot_path = display.capture_screenshot()

        assert screenshot_path is not None
        assert isinstance(screenshot_path, Path)

    def test_capture_screenshot_no_directory(self, mocker, mock_display_context):
        """Test screenshot capture when directory is not set."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)
        mocker.patch("rpi_usb_cloner.ui.display.settings.get_setting", return_value=None)

        screenshot_path = display.capture_screenshot()

        # Should handle gracefully (may return None or use default)
        assert screenshot_path is None or isinstance(screenshot_path, Path)

    def test_get_display_png_bytes(self, mocker, mock_display_context):
        """Test getting display as PNG bytes."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        png_bytes = display.get_display_png_bytes()

        assert png_bytes is not None
        assert isinstance(png_bytes, bytes)


# ==============================================================================
# Dirty Flag Tests
# ==============================================================================

class TestDirtyFlag:
    """Tests for display dirty flag management."""

    def test_mark_display_dirty(self):
        """Test marking display as dirty."""
        display.mark_display_dirty()

        # Should set internal flag
        assert display._display_dirty is True

    def test_clear_dirty_flag(self):
        """Test clearing dirty flag."""
        display.mark_display_dirty()
        display.clear_dirty_flag()

        assert display._display_dirty is False

    def test_wait_for_display_update(self, mocker):
        """Test waiting for display update."""
        # Mock threading.Event
        mock_event = MagicMock()
        mocker.patch("rpi_usb_cloner.ui.display.threading.Event", return_value=mock_event)

        display.mark_display_dirty()

        # Simulate event being set
        mock_event.wait.return_value = True

        result = display.wait_for_display_update(timeout=1.0)

        # Should wait for event
        assert mock_event.wait.called


# ==============================================================================
# Thread Safety Tests
# ==============================================================================

class TestThreadSafety:
    """Tests for thread-safe display operations."""

    def test_concurrent_display_lines(self, mocker, mock_display_context):
        """Test concurrent display_lines calls."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)

        def display_worker(lines):
            display.display_lines(lines)

        # Create multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=display_worker, args=([f"Line {i}"],))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # All threads should complete without deadlock
        assert True

    def test_concurrent_dirty_flag_operations(self):
        """Test concurrent dirty flag operations."""
        def mark_dirty_worker():
            for _ in range(10):
                display.mark_display_dirty()
                display.clear_dirty_flag()

        # Create multiple threads
        threads = []
        for _ in range(5):
            t = threading.Thread(target=mark_dirty_worker)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Should complete without errors
        assert True


# ==============================================================================
# Font Loading Tests
# ==============================================================================

class TestFontLoading:
    """Tests for font loading functions."""

    def test_get_lucide_font(self, mocker):
        """Test loading Lucide icon font."""
        mocker.patch("rpi_usb_cloner.ui.display.ImageFont.truetype", return_value=ImageFont.load_default())

        font = display._get_lucide_font()

        assert font is not None

    def test_get_lucide_font_fallback(self, mocker):
        """Test Lucide font loading with fallback."""
        # Mock font loading to fail
        mocker.patch("rpi_usb_cloner.ui.display.ImageFont.truetype", side_effect=OSError("Font not found"))

        font = display._get_lucide_font()

        # Should fall back to default font
        assert font is not None


# ==============================================================================
# Base Menu Tests
# ==============================================================================

class TestBaseMenu:
    """Tests for basemenu() function."""

    def test_basemenu_no_devices(self, mocker, mock_display_context):
        """Test base menu with no USB devices."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)
        mocker.patch("rpi_usb_cloner.ui.display.list_usb_disks", return_value=[])
        mocker.patch("rpi_usb_cloner.ui.display.menus")

        display.basemenu()

        # Should complete without error
        assert True

    def test_basemenu_with_devices(self, mocker, mock_display_context, mock_usb_device):
        """Test base menu with USB devices."""
        mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=mock_display_context)
        mocker.patch("rpi_usb_cloner.ui.display.list_usb_disks", return_value=[mock_usb_device])
        mocker.patch("rpi_usb_cloner.ui.display.menus")

        display.basemenu()

        # Should complete without error
        assert True


# ==============================================================================
# Debug Helper Tests
# ==============================================================================

class TestDebugHelpers:
    """Tests for debug helper functions."""

    def test_configure_display_helpers(self):
        """Test configuring display helpers."""
        mock_callback = Mock()

        display.configure_display_helpers(log_debug=mock_callback)

        # Should accept callback without error
        assert True
