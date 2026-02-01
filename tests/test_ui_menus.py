"""Tests for UI menu utilities.

This module tests the helper functions in rpi_usb_cloner.ui.menus,
focusing on non-GPIO functions that can be unit tested.
"""

from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from rpi_usb_cloner.ui import menus


# =============================================================================
# MenuItem and Menu Dataclass Tests
# =============================================================================


class TestMenuItem:
    """Test MenuItem dataclass."""

    def test_creation_with_lines_only(self):
        """Test creating MenuItem with just lines."""
        item = menus.MenuItem(lines=["Line 1", "Line 2"])

        assert item.lines == ["Line 1", "Line 2"]
        assert item.line_widths is None

    def test_creation_with_line_widths(self):
        """Test creating MenuItem with line widths."""
        item = menus.MenuItem(lines=["Line 1", "Line 2"], line_widths=[100, 150])

        assert item.lines == ["Line 1", "Line 2"]
        assert item.line_widths == [100, 150]

    def test_empty_lines(self):
        """Test MenuItem with empty lines."""
        item = menus.MenuItem(lines=[])

        assert item.lines == []
        assert item.line_widths is None


class TestMenu:
    """Test Menu dataclass."""

    def test_defaults(self):
        """Test Menu with default values."""
        items = [menus.MenuItem(lines=["Item 1"])]
        menu = menus.Menu(items=items)

        assert menu.items == items
        assert menu.selected_index == 0
        assert menu.title is None
        assert menu.title_icon is None
        assert menu.screen_id is None
        assert menu.footer is None
        assert menu.enable_horizontal_scroll is False

    def test_full_configuration(self):
        """Test Menu with all values set."""
        items = [
            menus.MenuItem(lines=["Item 1"]),
            menus.MenuItem(lines=["Item 2"]),
        ]
        menu = menus.Menu(
            items=items,
            selected_index=1,
            title="Test Menu",
            title_icon="icon",
            screen_id="test_screen",
            footer=["Back", "Select"],
            footer_selected_index=0,
            enable_horizontal_scroll=True,
            scroll_speed=50.0,
            scroll_gap=30,
        )

        assert menu.items == items
        assert menu.selected_index == 1
        assert menu.title == "Test Menu"
        assert menu.title_icon == "icon"
        assert menu.screen_id == "test_screen"
        assert menu.footer == ["Back", "Select"]
        assert menu.footer_selected_index == 0
        assert menu.enable_horizontal_scroll is True
        assert menu.scroll_speed == 50.0
        assert menu.scroll_gap == 30


# =============================================================================
# Footer Position Tests
# =============================================================================


class TestGetDefaultFooterPositions:
    """Test _get_default_footer_positions function."""

    def test_single_footer_item(self):
        """Test positions with single footer item."""
        positions = menus._get_default_footer_positions(128, ["Back"])

        assert len(positions) == 1
        assert positions[0] == 128 // 2 - 10  # Centered

    def test_two_footer_items(self):
        """Test positions with two footer items."""
        positions = menus._get_default_footer_positions(120, ["Back", "Select"])

        assert len(positions) == 2
        # Spacing = 120 // 3 = 40
        # Position 0 = 40 - 10 = 30
        # Position 1 = 80 - 10 = 70
        assert positions[0] == 30
        assert positions[1] == 70

    def test_three_footer_items(self):
        """Test positions with three footer items."""
        positions = menus._get_default_footer_positions(128, ["A", "B", "C"])

        assert len(positions) == 3
        # Spacing = 128 // 4 = 32
        # Position 0 = 32 - 10 = 22
        # Position 1 = 64 - 10 = 54
        # Position 2 = 96 - 10 = 86
        assert positions[0] == 22
        assert positions[1] == 54
        assert positions[2] == 86

    def test_narrow_screen(self):
        """Test with narrow screen."""
        positions = menus._get_default_footer_positions(64, ["A", "B"])

        assert len(positions) == 2
        # Spacing = 64 // 3 = 21
        assert positions[0] == 21 - 10
        assert positions[1] == 42 - 10


# =============================================================================
# Line Height Tests
# =============================================================================


class TestGetLineHeight:
    """Test _get_line_height function."""

    def test_uses_min_height_for_none_font(self):
        """Test that min height is used when font is None."""
        height = menus._get_line_height(None, min_height=8)

        assert height == 8

    def test_uses_font_bbox(self):
        """Test using font bbox for height calculation."""
        mock_font = Mock()
        mock_font.getbbox = Mock(return_value=(0, 0, 10, 16))  # height = 16

        height = menus._get_line_height(mock_font, min_height=8)

        assert height == 16

    def test_uses_font_metrics(self):
        """Test using font metrics when bbox not available."""
        mock_font = Mock()
        mock_font.getbbox = Mock(side_effect=AttributeError())
        mock_font.getmetrics = Mock(return_value=(10, 4))  # ascent + descent = 14

        height = menus._get_line_height(mock_font, min_height=8)

        assert height == 14

    def test_min_height_takes_precedence(self):
        """Test that min_height is used when font metrics are smaller."""
        mock_font = Mock()
        mock_font.getbbox = Mock(return_value=(0, 0, 10, 5))  # height = 5

        height = menus._get_line_height(mock_font, min_height=10)

        assert height == 10


# =============================================================================
# Text Height Tests
# =============================================================================


class TestGetTextHeight:
    """Test _get_text_height function."""

    def test_calculates_from_bbox(self):
        """Test height calculation from text bbox."""
        image = Image.new("1", (128, 64))
        draw = ImageDraw.Draw(image)
        mock_font = Mock()

        with patch.object(draw, "textbbox", return_value=(10, 5, 50, 25)):
            height = menus._get_text_height(draw, "Test", mock_font)

        # height = 25 - 5 = 20
        assert height == 20

    def test_single_line_text(self):
        """Test with single line text."""
        image = Image.new("1", (128, 64))
        draw = ImageDraw.Draw(image)
        mock_font = Mock()

        with patch.object(draw, "textbbox", return_value=(0, 0, 30, 12)):
            height = menus._get_text_height(draw, "A", mock_font)

        assert height == 12


# =============================================================================
# Content Top Calculation Tests
# =============================================================================


class TestGetStandardContentTop:
    """Test get_standard_content_top function."""

    @patch("rpi_usb_cloner.ui.menus.display.get_display_context")
    def test_returns_context_top_for_empty_title(self, mock_get_context):
        """Test that context.top is returned when title is empty."""
        mock_context = Mock()
        mock_context.top = 16
        mock_context.fontdisks = Mock()
        mock_context.fonts = {"title": Mock()}
        mock_get_context.return_value = mock_context

        result = menus.get_standard_content_top("")

        assert result == 16


# =============================================================================
# Transition Settings Tests
# =============================================================================


class TestGetTransitionFrameCount:
    """Test _get_transition_frame_count function."""

    @patch("rpi_usb_cloner.ui.menus.display.get_display_context")
    @patch("rpi_usb_cloner.ui.menus.settings.get_setting")
    def test_uses_default_based_on_width(self, mock_get_setting, mock_get_context):
        """Test default frame count based on screen width."""
        mock_context = Mock()
        mock_context.width = 128
        mock_get_context.return_value = mock_context
        mock_get_setting.return_value = None

        result = menus._get_transition_frame_count()

        # default = max(8, min(24, 128 // 4)) = max(8, min(24, 32)) = max(8, 24) = 24
        assert result == 24

    @patch("rpi_usb_cloner.ui.menus.display.get_display_context")
    @patch("rpi_usb_cloner.ui.menus.settings.get_setting")
    def test_clamps_to_max(self, mock_get_setting, mock_get_context):
        """Test that frame count is clamped to max of 24."""
        mock_context = Mock()
        mock_context.width = 256  # Would give 64 without clamping
        mock_get_context.return_value = mock_context
        mock_get_setting.return_value = None

        result = menus._get_transition_frame_count()

        assert result == 24  # Max clamped

    @patch("rpi_usb_cloner.ui.menus.display.get_display_context")
    @patch("rpi_usb_cloner.ui.menus.settings.get_setting")
    def test_clamps_to_min(self, mock_get_setting, mock_get_context):
        """Test that frame count is clamped to min of 8."""
        mock_context = Mock()
        mock_context.width = 16  # Would give 4 without clamping
        mock_get_context.return_value = mock_context
        mock_get_setting.return_value = None

        result = menus._get_transition_frame_count()

        assert result == 8  # Min clamped

    @patch("rpi_usb_cloner.ui.menus.display.get_display_context")
    @patch("rpi_usb_cloner.ui.menus.settings.get_setting")
    def test_uses_setting_value(self, mock_get_setting, mock_get_context):
        """Test using value from settings."""
        mock_context = Mock()
        mock_context.width = 128
        mock_get_context.return_value = mock_context
        mock_get_setting.return_value = 16

        result = menus._get_transition_frame_count()

        assert result == 16

    @patch("rpi_usb_cloner.ui.menus.display.get_display_context")
    @patch("rpi_usb_cloner.ui.menus.settings.get_setting")
    def test_invalid_setting_uses_default(self, mock_get_setting, mock_get_context):
        """Test that invalid setting value uses default."""
        mock_context = Mock()
        mock_context.width = 128
        mock_get_context.return_value = mock_context
        mock_get_setting.return_value = "invalid"

        result = menus._get_transition_frame_count()

        # Falls back to default calculation
        assert result == 24


class TestGetTransitionFrameDelay:
    """Test _get_transition_frame_delay function."""

    @patch("rpi_usb_cloner.ui.menus.settings.get_setting")
    def test_uses_setting_value(self, mock_get_setting):
        """Test using delay from settings."""
        mock_get_setting.return_value = 0.05

        result = menus._get_transition_frame_delay()

        assert result == 0.05

    @patch("rpi_usb_cloner.ui.menus.settings.get_setting")
    def test_invalid_setting_uses_default(self, mock_get_setting):
        """Test that invalid setting uses default."""
        mock_get_setting.return_value = "invalid"

        result = menus._get_transition_frame_delay()

        assert result == menus.DEFAULT_TRANSITION_FRAME_DELAY

    @patch("rpi_usb_cloner.ui.menus.settings.get_setting")
    def test_zero_delay_allowed(self, mock_get_setting):
        """Test that zero delay is allowed."""
        mock_get_setting.return_value = 0.0

        result = menus._get_transition_frame_delay()

        assert result == 0.0
