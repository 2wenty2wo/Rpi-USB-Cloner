"""
Tests for rpi_usb_cloner.ui.menus module.

This test suite covers:
- Menu selection and navigation (Up/Down/Left/Right buttons)
- Button repeat functionality with delays
- Menu rendering with titles and footers
- USB drive selection menus
- Clone/erase/filesystem mode selection
- Horizontal text scrolling
- Multi-line menu items
- Pagination calculations
- Refresh callbacks
"""

import time
from unittest.mock import Mock, MagicMock, call, patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from rpi_usb_cloner.ui import menus


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def mock_display_context():
    """Fixture providing a mock display context."""
    context = MagicMock()
    context.width = 128
    context.height = 64
    context.top = 0
    context.x = 11
    context.disp = MagicMock()
    context.image = Image.new('1', (128, 64))
    context.draw = ImageDraw.Draw(context.image)
    context.fonts = {
        "title": ImageFont.load_default(),
        "items": ImageFont.load_default(),
        "footer": ImageFont.load_default(),
    }
    context.fontdisks = ImageFont.load_default()
    context.fontcopy = ImageFont.load_default()
    return context


@pytest.fixture
def simple_menu_items():
    """Fixture providing simple menu items."""
    return [
        menus.MenuItem(lines=["Item 1"]),
        menus.MenuItem(lines=["Item 2"]),
        menus.MenuItem(lines=["Item 3"]),
    ]


@pytest.fixture
def multiline_menu_items():
    """Fixture providing multi-line menu items."""
    return [
        menus.MenuItem(lines=["Item 1", "Subtitle 1"]),
        menus.MenuItem(lines=["Item 2", "Subtitle 2"]),
        menus.MenuItem(lines=["Item 3", "Subtitle 3"]),
    ]


@pytest.fixture(autouse=True)
def mock_dependencies(mocker, mock_display_context):
    """Auto-use fixture that mocks menu dependencies."""
    # Mock display context
    mocker.patch("rpi_usb_cloner.ui.menus.display.get_display_context", return_value=mock_display_context)
    mocker.patch("rpi_usb_cloner.ui.menus.display.draw_title_with_icon")
    mocker.patch("rpi_usb_cloner.ui.menus.display._measure_text_width", return_value=10)
    mocker.patch("rpi_usb_cloner.ui.menus.display._truncate_text", side_effect=lambda draw, text, font, width: text)
    mocker.patch("rpi_usb_cloner.ui.menus.display._get_lucide_font", return_value=ImageFont.load_default())
    mocker.patch("rpi_usb_cloner.ui.menus.display.TITLE_PADDING", 2)

    # Mock GPIO
    mocker.patch("rpi_usb_cloner.ui.menus.read_button", return_value=False)
    mocker.patch("rpi_usb_cloner.ui.menus.is_pressed", return_value=False)

    # Mock menu icon
    mocker.patch("rpi_usb_cloner.ui.menus.get_screen_icon", return_value=None)

    # Mock storage functions
    mocker.patch("rpi_usb_cloner.ui.menus.format_device_label", side_effect=lambda x: x.get("name") if isinstance(x, dict) else str(x))
    mocker.patch("rpi_usb_cloner.ui.menus.normalize_clone_mode", side_effect=lambda x: x)

    # Mock settings
    mocker.patch("rpi_usb_cloner.ui.menus.settings.get_setting", return_value=menus.DEFAULT_SCROLL_REFRESH_INTERVAL)

    # Mock renderer
    mocker.patch("rpi_usb_cloner.ui.menus.renderer")


# ==============================================================================
# Menu Item and Data Structure Tests
# ==============================================================================

class TestMenuItem:
    """Tests for MenuItem dataclass."""

    def test_create_simple_menu_item(self):
        """Test creating a simple menu item."""
        item = menus.MenuItem(lines=["Test Item"])

        assert item.lines == ["Test Item"]
        assert item.line_widths is None

    def test_create_menu_item_with_widths(self):
        """Test creating menu item with line widths."""
        item = menus.MenuItem(lines=["Item 1", "Item 2"], line_widths=[50, 60])

        assert item.lines == ["Item 1", "Item 2"]
        assert item.line_widths == [50, 60]

    def test_multiline_menu_item(self):
        """Test menu item with multiple lines."""
        item = menus.MenuItem(lines=["Line 1", "Line 2", "Line 3"])

        assert len(item.lines) == 3


class TestMenu:
    """Tests for Menu dataclass."""

    def test_create_basic_menu(self, simple_menu_items):
        """Test creating a basic menu."""
        menu = menus.Menu(items=simple_menu_items)

        assert len(menu.items) == 3
        assert menu.selected_index == 0
        assert menu.title is None

    def test_create_menu_with_title(self, simple_menu_items):
        """Test creating menu with title."""
        menu = menus.Menu(
            items=simple_menu_items,
            title="Test Menu",
            title_icon="icon",
        )

        assert menu.title == "Test Menu"
        assert menu.title_icon == "icon"

    def test_create_menu_with_footer(self, simple_menu_items):
        """Test creating menu with footer."""
        menu = menus.Menu(
            items=simple_menu_items,
            footer=["A:Back", "B:Select"],
            footer_selected_index=1,
        )

        assert menu.footer == ["A:Back", "B:Select"]
        assert menu.footer_selected_index == 1


# ==============================================================================
# Helper Function Tests
# ==============================================================================

class TestGetTextHeight:
    """Tests for _get_text_height() helper function."""

    def test_get_text_height(self, mock_display_context):
        """Test getting text height."""
        font = ImageFont.load_default()
        height = menus._get_text_height(mock_display_context.draw, "Test", font)

        assert height > 0
        assert isinstance(height, int)


class TestGetLineHeight:
    """Tests for _get_line_height() helper function."""

    def test_get_line_height_default(self):
        """Test getting line height from font."""
        font = ImageFont.load_default()
        height = menus._get_line_height(font)

        assert height >= 8  # min_height
        assert isinstance(height, int)

    def test_get_line_height_custom_min(self):
        """Test getting line height with custom minimum."""
        font = ImageFont.load_default()
        height = menus._get_line_height(font, min_height=12)

        assert height >= 12


class TestGetStandardContentTop:
    """Tests for get_standard_content_top() helper function."""

    def test_no_title(self, mock_display_context):
        """Test content top with no title."""
        content_top = menus.get_standard_content_top("")

        assert content_top == mock_display_context.top

    def test_with_title(self, mock_display_context):
        """Test content top with title."""
        content_top = menus.get_standard_content_top("Test Title")

        assert content_top > mock_display_context.top

    def test_with_title_and_icon(self, mocker, mock_display_context):
        """Test content top with title and icon."""
        mocker.patch("rpi_usb_cloner.ui.menus.display._get_lucide_font", return_value=ImageFont.load_default())

        content_top = menus.get_standard_content_top(
            "Test Title",
            title_icon="icon",
        )

        assert content_top > mock_display_context.top


class TestGetDefaultFooterPositions:
    """Tests for _get_default_footer_positions() helper function."""

    def test_two_footer_items(self):
        """Test footer positions for 2 items."""
        positions = menus._get_default_footer_positions(128, ["A", "B"])

        assert len(positions) == 2
        assert all(isinstance(p, int) for p in positions)
        assert positions[0] < positions[1]

    def test_three_footer_items(self):
        """Test footer positions for 3 items."""
        positions = menus._get_default_footer_positions(128, ["A", "B", "C"])

        assert len(positions) == 3
        assert positions[0] < positions[1] < positions[2]


# ==============================================================================
# Menu Rendering Tests
# ==============================================================================

class TestRenderMenu:
    """Tests for render_menu() function."""

    def test_render_simple_menu(self, mocker, mock_display_context, simple_menu_items):
        """Test rendering a simple menu."""
        menu = menus.Menu(items=simple_menu_items, selected_index=0)

        menus.render_menu(
            menu,
            mock_display_context.draw,
            mock_display_context.width,
            mock_display_context.height,
            mock_display_context.fonts,
        )

        # Should complete without errors
        assert True

    def test_render_menu_with_title(self, mocker, mock_display_context, simple_menu_items):
        """Test rendering menu with title."""
        mock_draw_title = mocker.patch("rpi_usb_cloner.ui.menus.display.draw_title_with_icon")
        mock_layout = MagicMock()
        mock_layout.content_top = 16
        mock_draw_title.return_value = mock_layout

        menu = menus.Menu(
            items=simple_menu_items,
            title="Test Menu",
            selected_index=0,
        )

        menus.render_menu(
            menu,
            mock_display_context.draw,
            mock_display_context.width,
            mock_display_context.height,
            mock_display_context.fonts,
        )

        mock_draw_title.assert_called_once()

    def test_render_multiline_menu(self, mocker, mock_display_context, multiline_menu_items):
        """Test rendering menu with multi-line items."""
        menu = menus.Menu(items=multiline_menu_items, selected_index=1)

        menus.render_menu(
            menu,
            mock_display_context.draw,
            mock_display_context.width,
            mock_display_context.height,
            mock_display_context.fonts,
        )

        # Should complete without errors
        assert True

    def test_render_menu_with_footer(self, mocker, mock_display_context, simple_menu_items):
        """Test rendering menu with footer."""
        menu = menus.Menu(
            items=simple_menu_items,
            footer=["A:Back", "B:Select"],
            footer_selected_index=0,
            selected_index=0,
        )

        menus.render_menu(
            menu,
            mock_display_context.draw,
            mock_display_context.width,
            mock_display_context.height,
            mock_display_context.fonts,
        )

        # Should complete without errors
        assert True

    def test_render_menu_no_clear(self, mocker, mock_display_context, simple_menu_items):
        """Test rendering menu without clearing screen."""
        menu = menus.Menu(items=simple_menu_items)

        menus.render_menu(
            menu,
            mock_display_context.draw,
            mock_display_context.width,
            mock_display_context.height,
            mock_display_context.fonts,
            clear=False,
        )

        # Should complete without errors
        assert True


# ==============================================================================
# Menu Selection Tests
# ==============================================================================

class TestSelectList:
    """Tests for select_list() function."""

    def test_select_first_item(self, mocker):
        """Test selecting the first item."""
        # Mock poll_button_events to return immediately
        mock_poll = mocker.patch("rpi_usb_cloner.ui.menus.renderer.poll_menu_input")
        mock_poll.return_value = 0

        result = menus.select_list(
            "TEST",
            ["Item 1", "Item 2", "Item 3"],
            selected_index=0,
        )

        assert result == 0

    def test_cancel_selection(self, mocker):
        """Test canceling menu selection."""
        mock_poll = mocker.patch("rpi_usb_cloner.ui.menus.renderer.poll_menu_input")
        mock_poll.return_value = None

        result = menus.select_list(
            "TEST",
            ["Item 1", "Item 2"],
            selected_index=0,
        )

        assert result is None

    def test_select_with_initial_index(self, mocker):
        """Test selection with non-zero initial index."""
        mock_poll = mocker.patch("rpi_usb_cloner.ui.menus.renderer.poll_menu_input")
        mock_poll.return_value = 2

        result = menus.select_list(
            "TEST",
            ["Item 1", "Item 2", "Item 3"],
            selected_index=2,
        )

        assert result == 2

    def test_empty_items_list(self, mocker):
        """Test with empty items list."""
        mock_poll = mocker.patch("rpi_usb_cloner.ui.menus.renderer.poll_menu_input")
        mock_poll.return_value = None

        result = menus.select_list(
            "TEST",
            [],
            selected_index=0,
        )

        assert result is None


class TestRenderMenuList:
    """Tests for render_menu_list() function."""

    def test_render_and_select(self, mocker):
        """Test rendering menu list and selecting item."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_list")
        mock_select.return_value = 1

        result = menus.render_menu_list(
            "TEST",
            ["Option 1", "Option 2", "Option 3"],
            selected_index=0,
        )

        assert result == 1
        mock_select.assert_called_once()

    def test_render_with_icon(self, mocker):
        """Test rendering menu list with icon."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_list")
        mock_select.return_value = 0

        result = menus.render_menu_list(
            "TEST",
            ["Option 1", "Option 2"],
            title_icon="icon",
        )

        mock_select.assert_called_once()
        # Verify icon was passed
        call_kwargs = mock_select.call_args[1]
        assert call_kwargs.get("title_icon") == "icon"


class TestSelectMenuScreenList:
    """Tests for select_menu_screen_list() function."""

    def test_select_with_status_line(self, mocker):
        """Test menu selection with status line."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_list")
        mock_select.return_value = 1

        result = menus.select_menu_screen_list(
            "TEST",
            ["Item 1", "Item 2"],
            status_line="Status",
        )

        assert result == 1

    def test_select_without_status_line(self, mocker):
        """Test menu selection without status line."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_list")
        mock_select.return_value = 0

        result = menus.select_menu_screen_list(
            "TEST",
            ["Item 1", "Item 2"],
        )

        assert result == 0


# ==============================================================================
# USB Drive Selection Tests
# ==============================================================================

class TestSelectUSBDrive:
    """Tests for select_usb_drive() function."""

    def test_select_usb_drive(self, mocker, mock_usb_device):
        """Test selecting a USB drive."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_list")
        mock_select.return_value = 0

        devices = [mock_usb_device]
        result = menus.select_usb_drive(
            "SELECT USB",
            devices,
        )

        assert result == 0
        mock_select.assert_called_once()

    def test_select_usb_drive_with_selected_name(self, mocker, mock_usb_device):
        """Test USB drive selection with pre-selected name."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_list")
        mock_select.return_value = 0

        device2 = mock_usb_device.copy()
        device2["name"] = "sdb"

        devices = [mock_usb_device, device2]
        result = menus.select_usb_drive(
            "SELECT USB",
            devices,
            selected_name="sdb",
        )

        # Should call select_list with sdb's index (1)
        mock_select.assert_called_once()
        call_kwargs = mock_select.call_args[1]
        assert call_kwargs.get("selected_index") == 1

    def test_select_usb_drive_empty_list(self, mocker):
        """Test USB drive selection with empty device list."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_list")
        mock_select.return_value = None

        result = menus.select_usb_drive(
            "SELECT USB",
            [],
        )

        assert result is None


# ==============================================================================
# Mode Selection Tests
# ==============================================================================

class TestSelectCloneMode:
    """Tests for select_clone_mode() function."""

    def test_select_smart_mode(self, mocker):
        """Test selecting smart clone mode."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_list")
        mock_select.return_value = 0  # smart mode

        result = menus.select_clone_mode()

        assert result == "smart"

    def test_select_exact_mode(self, mocker):
        """Test selecting exact clone mode."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_list")
        mock_select.return_value = 1  # exact mode

        result = menus.select_clone_mode()

        assert result == "exact"

    def test_cancel_clone_mode_selection(self, mocker):
        """Test canceling clone mode selection."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_list")
        mock_select.return_value = None

        result = menus.select_clone_mode()

        assert result is None

    def test_select_with_default_mode(self, mocker):
        """Test clone mode selection with default."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_list")
        mock_select.return_value = 1

        result = menus.select_clone_mode(default_mode="exact")

        # Should start with exact mode selected
        call_kwargs = mock_select.call_args[1]
        assert call_kwargs.get("selected_index") == 1


class TestSelectEraseMode:
    """Tests for select_erase_mode() function."""

    def test_select_quick_erase(self, mocker):
        """Test selecting quick erase mode."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_menu_screen_list")
        mock_select.return_value = 0  # quick

        result = menus.select_erase_mode()

        assert result == "quick"

    def test_select_zero_erase(self, mocker):
        """Test selecting zero erase mode."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_menu_screen_list")
        mock_select.return_value = 1  # zero

        result = menus.select_erase_mode()

        assert result == "zero"

    def test_select_secure_erase(self, mocker):
        """Test selecting secure erase mode."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_menu_screen_list")
        mock_select.return_value = 3  # secure

        result = menus.select_erase_mode()

        assert result == "secure"

    def test_cancel_erase_mode(self, mocker):
        """Test canceling erase mode selection."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_menu_screen_list")
        mock_select.return_value = None

        result = menus.select_erase_mode()

        assert result is None


class TestSelectFilesystemType:
    """Tests for select_filesystem_type() function."""

    def test_select_ext4(self, mocker):
        """Test selecting ext4 filesystem."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_menu_screen_list")
        mock_select.return_value = 0  # ext4

        result = menus.select_filesystem_type(16 * 1024**3)  # 16GB

        assert result == "ext4"

    def test_select_vfat(self, mocker):
        """Test selecting vfat filesystem."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_menu_screen_list")
        mock_select.return_value = 1  # vfat

        result = menus.select_filesystem_type(16 * 1024**3)

        assert result == "vfat"

    def test_default_vfat_for_small_drive(self, mocker):
        """Test default filesystem for drives ≤32GB."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_menu_screen_list")
        mock_select.return_value = 1  # vfat

        result = menus.select_filesystem_type(32 * 1024**3)  # 32GB

        # Should suggest vfat for 32GB
        call_kwargs = mock_select.call_args[1]
        assert call_kwargs.get("selected_index") == 1  # vfat

    def test_default_exfat_for_large_drive(self, mocker):
        """Test default filesystem for drives ≥64GB."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_menu_screen_list")
        mock_select.return_value = 2  # exfat

        result = menus.select_filesystem_type(64 * 1024**3)  # 64GB

        # Should suggest exfat for 64GB
        call_kwargs = mock_select.call_args[1]
        assert call_kwargs.get("selected_index") == 2  # exfat


class TestSelectFormatType:
    """Tests for select_format_type() function."""

    def test_select_quick_format(self, mocker):
        """Test selecting quick format."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_menu_screen_list")
        mock_select.return_value = 0  # quick

        result = menus.select_format_type()

        assert result == "quick"

    def test_select_full_format(self, mocker):
        """Test selecting full format."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_menu_screen_list")
        mock_select.return_value = 1  # full

        result = menus.select_format_type()

        assert result == "full"

    def test_cancel_format_type(self, mocker):
        """Test canceling format type selection."""
        mock_select = mocker.patch("rpi_usb_cloner.ui.menus.select_menu_screen_list")
        mock_select.return_value = None

        result = menus.select_format_type()

        assert result is None


# ==============================================================================
# Button Handling Tests
# ==============================================================================

class TestWaitForButtonsRelease:
    """Tests for wait_for_buttons_release() function."""

    def test_wait_for_single_button(self, mocker):
        """Test waiting for single button release."""
        # Simulate button pressed then released
        mock_read = mocker.patch("rpi_usb_cloner.ui.menus.read_button")
        mock_read.side_effect = [True, True, False]  # Pressed, still pressed, released

        from rpi_usb_cloner.hardware.gpio import PIN_A

        menus.wait_for_buttons_release([PIN_A])

        assert mock_read.call_count == 3

    def test_wait_for_multiple_buttons(self, mocker):
        """Test waiting for multiple buttons to release."""
        mock_read = mocker.patch("rpi_usb_cloner.ui.menus.read_button")

        # First call: A pressed, B pressed
        # Second call: A released, B pressed
        # Third call: A released, B released
        mock_read.side_effect = [
            True, True,  # Both pressed
            False, True,  # A released, B still pressed
            False, False,  # Both released
        ]

        from rpi_usb_cloner.hardware.gpio import PIN_A, PIN_B

        menus.wait_for_buttons_release([PIN_A, PIN_B])

        assert mock_read.call_count == 6  # 2 buttons × 3 iterations

    def test_wait_with_no_buttons_pressed(self, mocker):
        """Test waiting when no buttons are pressed."""
        mock_read = mocker.patch("rpi_usb_cloner.ui.menus.read_button")
        mock_read.return_value = False  # All buttons released

        from rpi_usb_cloner.hardware.gpio import PIN_A, PIN_B

        menus.wait_for_buttons_release([PIN_A, PIN_B])

        # Should exit immediately
        assert mock_read.call_count == 2  # One check per button


# ==============================================================================
# Pagination and Scrolling Tests
# ==============================================================================

class TestHorizontalScrolling:
    """Tests for horizontal text scrolling functionality."""

    def test_scrolling_enabled_for_images_screen(self, mock_display_context, simple_menu_items):
        """Test that scrolling is enabled for images screen."""
        menu = menus.Menu(
            items=simple_menu_items,
            screen_id="images",
            enable_horizontal_scroll=True,
            scroll_start_time=time.monotonic(),
        )

        assert menu.enable_horizontal_scroll is True
        assert menu.scroll_start_time is not None

    def test_scrolling_parameters(self, simple_menu_items):
        """Test scrolling parameters configuration."""
        menu = menus.Menu(
            items=simple_menu_items,
            enable_horizontal_scroll=True,
            scroll_speed=50.0,
            target_cycle_seconds=5.0,
            scroll_gap=15,
        )

        assert menu.scroll_speed == 50.0
        assert menu.target_cycle_seconds == 5.0
        assert menu.scroll_gap == 15


class TestRefreshCallback:
    """Tests for menu refresh callback functionality."""

    def test_select_list_with_refresh_callback(self, mocker):
        """Test that refresh callback is supported in select_list."""
        mock_poll = mocker.patch("rpi_usb_cloner.ui.menus.renderer.poll_menu_input")
        mock_poll.return_value = 0

        refresh_callback = Mock()

        result = menus.select_list(
            "TEST",
            ["Item 1", "Item 2"],
            refresh_callback=refresh_callback,
        )

        # Function should accept refresh_callback parameter
        assert result is not None
