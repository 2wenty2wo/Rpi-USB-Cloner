"""Tests for UI renderer module."""

from unittest.mock import Mock

import pytest

from rpi_usb_cloner.ui import renderer


# ==============================================================================
# Helper Function Tests
# ==============================================================================


class TestHelperFunctions:
    """Test standalone helper functions in renderer.py."""

    def test_get_line_height_with_bbox(self):
        """Test getting line height using getbbox."""
        font = Mock()
        font.getbbox.return_value = (0, 0, 10, 12)  # height = 12

        height = renderer._get_line_height(font, min_height=8)
        assert height == 12

    def test_get_line_height_with_metrics(self):
        """Test getting line height using getmetrics fallback."""
        font = Mock()
        del font.getbbox  # Remove getbbox to trigger fallback
        font.getmetrics.return_value = (10, 4)  # 10 + 4 = 14

        height = renderer._get_line_height(font, min_height=8)
        assert height == 14

    def test_get_line_height_fallback_min(self):
        """Test fallback to min_height if no methods work."""
        font = Mock()
        del font.getbbox
        del font.getmetrics

        height = renderer._get_line_height(font, min_height=20)
        assert height == 20

    def test_measure_text_width_getlength(self):
        """Test measuring text using getlength."""
        font = Mock()
        font.getlength.return_value = 42.5

        width = renderer._measure_text_width(font, "test")
        assert width == 42

    def test_measure_text_width_bbox(self):
        """Test measuring text using getbbox fallback."""
        font = Mock()
        del font.getlength
        font.getbbox.return_value = (0, 0, 42, 10)  # width = 42

        width = renderer._measure_text_width(font, "test")
        assert width == 42

    def test_truncate_text_not_needed(self):
        """Test text is not truncated if it fits."""
        font = Mock()
        # Mock width measurement
        font.getlength.side_effect = lambda t: len(t) * 10

        # "test" -> 40px width, max 50
        result = renderer._truncate_text("test", font, 50)
        assert result == "test"

    def test_truncate_text_needed(self):
        """Test text is truncated with ellipsis if too long."""
        font = Mock()

        # Mock width measurement: "testlong" -> 80, "test..." -> 70
        def get_width(text):
            return len(text) * 10

        font.getlength.side_effect = get_width

        # Max 50 -> "test..." (7chars=70) might be too long?
        # Let's try simpler: "abc" fits (30), "abcde" (50) fits
        # "abcdef" (60) > 50. Ellipsis is "…" (1 char usually)

        # Setup specific behaviors for truncation loop
        # Ellipsis width
        # The function uses "…" char

        # Let's mock _measure_text_width logic indirectly via the font helpers
        # or better, mock _measure_text_width if we weren't testing private methods
        # But we are testing _truncate_text which calls internal _measure_text_width

        # Let's use a real simplistic approach for the mock
        font.getlength.side_effect = lambda t: len(t) * 10

        # "Hello World" -> 110px. Max 60px.
        # "…" -> 10px.
        # "Hello…" -> 60px. Fits. "Hello" is 5 chars.
        result = renderer._truncate_text("Hello World", font, 60)

        # The result should end with ellipsis
        assert result.endswith("…")
        # And fit within width
        assert len(result) * 10 <= 60

    def test_truncate_text_empty(self):
        """Test empty string returns empty."""
        assert renderer._truncate_text("", Mock(), 100) == ""


# ==============================================================================
# Scrolling Logic Tests
# ==============================================================================


class TestScrollingLogic:
    """Test horizontal scrolling calculation logic."""

    def test_no_scroll_needed(self):
        """Test returns 0 if text fits."""
        offset = renderer.calculate_horizontal_scroll_offset(
            now=10.0, scroll_start_time=5.0, text_width=50, max_width=100
        )
        assert offset == 0

    def test_no_start_time(self):
        """Test returns 0 if scroll_start_time is None."""
        offset = renderer.calculate_horizontal_scroll_offset(
            now=10.0, scroll_start_time=None, text_width=200, max_width=100
        )
        assert offset == 0

    def test_pause_at_start(self):
        """Test returns 0 during initial pause period."""
        # Delay is 2.0s
        # Elapsed is 1.0s (6.0 - 5.0)
        offset = renderer.calculate_horizontal_scroll_offset(
            now=6.0,
            scroll_start_time=5.0,
            text_width=200,
            max_width=100,
            scroll_start_delay=2.0,
        )
        assert offset == 0

    def test_scroll_movement(self):
        """Test offset calculation during movement phase."""
        # Text 200, Max 100. Gap 20. Cycle width 220.
        # Delay 0. Cycle 6s.
        # Elapsed 3s (halfway). Should be half of cycle width?
        # Actually logic is: scroll_speed = cycle_width / travel_duration
        # travel_phase = phase - pause

        offset = renderer.calculate_horizontal_scroll_offset(
            now=8.0,
            scroll_start_time=5.0,  # Elapsed 3.0s
            text_width=200,
            max_width=100,
            scroll_gap=20,
            target_cycle_seconds=6.0,
            scroll_start_delay=0.0,
        )

        # Expected:
        # cycle_width = 220
        # travel_duration = 6.0
        # speed = 220 / 6 = 36.66 px/s
        # travel_phase = 3.0
        # offset = -int(3.0 * 36.66) = -110

        assert -112 <= offset <= -108  # Allow float precision wiggle


# ==============================================================================
# Layout Calculation Tests
# ==============================================================================


class TestLayoutCalculations:
    """Test keys layout calculation functions."""

    @pytest.fixture
    def mock_context(self, mocker):
        """Mock the display context."""
        context = Mock()
        context.width = 128
        context.height = 64
        context.top = 0
        context.x = 0
        context.fonts = {"title": Mock(), "items": Mock(), "footer": Mock()}

        # Mock font heights defaults
        for f in context.fonts.values():
            f.getbbox.return_value = (0, 0, 10, 10)  # 10px height
            f.getlength.return_value = 5  # 5px char width

        mocker.patch(
            "rpi_usb_cloner.ui.display.get_display_context", return_value=context
        )
        return context

    def test_calculate_visible_rows_simple(self, mock_context):
        """Test calculating visible rows with just items."""
        # Total height 64.
        # Title height 0 (no title)
        # Footer height 0
        # Padding 1
        # Row height = 10 (font) + 1 (gap) = 11

        # Available = 64 - 1 = 63
        # Rows = 63 // 11 = 5

        rows = renderer.calculate_visible_rows(title="")
        assert rows == 5

    def test_calculate_visible_rows_with_title(self, mock_context):
        """Test with title consuming space."""
        # Title height 10 + padding 4 + gap 1 = 15
        # Available = 64 - 15 - 1 = 48
        # Row height 11
        # Rows = 48 // 11 = 4

        rows = renderer.calculate_visible_rows(title="Menu")
        assert rows == 4

    def test_calculate_visible_rows_with_status(self, mock_context):
        """Test with status line consuming space."""
        # Status height 10
        # Gap 4 (defined in function for status line)
        # Available = 64 - 10 - 4 - 1 = 49
        # Rows = 49 // 11 = 4

        rows = renderer.calculate_visible_rows(title="", status_line="Status")
        assert rows == 4

    def test_calculate_footer_bounds_no_footer(self, mock_context):
        """Test valid bounds when no footer present."""
        start, end = renderer.calculate_footer_bounds()
        assert start == 64
        assert end == 64

    def test_calculate_footer_bounds_with_status(self, mock_context):
        """Test valid bounds with status line."""
        # Footer height 10
        # Padding 1
        # y = 64 - 10 - 1 = 53
        # start = 53 - 1 + 1 = 53?
        # function: footer_start = footer_y - footer_padding + 1
        # footer_y = 53
        # footer_start = 53 - 1 + 1 = 53

        start, end = renderer.calculate_footer_bounds(status_line="Ready")
        assert start < end
        assert end == 64
        assert start == 53
