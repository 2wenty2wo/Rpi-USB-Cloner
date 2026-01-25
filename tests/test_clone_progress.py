"""Tests for progress monitoring and formatting."""

import pytest

from rpi_usb_cloner.storage.clone.progress import (
    format_eta,
    format_progress_display,
    format_progress_lines,
    parse_progress_from_output,
)


class TestFormatEta:
    """Tests for format_eta function."""

    def test_format_eta_seconds_only(self):
        """Test ETA formatting with seconds only."""
        assert format_eta(45) == "00:45"

    def test_format_eta_minutes_and_seconds(self):
        """Test ETA formatting with minutes and seconds."""
        assert format_eta(125) == "02:05"
        assert format_eta(600) == "10:00"

    def test_format_eta_hours(self):
        """Test ETA formatting with hours."""
        assert format_eta(3665) == "1:01:05"
        assert format_eta(7200) == "2:00:00"
        assert format_eta(36000) == "10:00:00"

    def test_format_eta_none(self):
        """Test ETA formatting with None input."""
        assert format_eta(None) is None

    def test_format_eta_negative(self):
        """Test ETA formatting with negative values."""
        assert format_eta(-10) is None
        assert format_eta(-100) is None

    def test_format_eta_zero(self):
        """Test ETA formatting with zero."""
        assert format_eta(0) == "00:00"

    def test_format_eta_large_value(self):
        """Test ETA formatting with very large values."""
        # 24 hours
        assert format_eta(86400) == "24:00:00"
        # 100 hours
        assert format_eta(360000) == "100:00:00"

    def test_format_eta_float_conversion(self):
        """Test ETA formatting converts floats to ints."""
        assert format_eta(45.7) == "00:45"
        assert format_eta(125.9) == "02:05"


class TestFormatProgressLines:
    """Tests for format_progress_lines function (legacy format)."""

    def test_format_basic_progress(self):
        """Test basic progress formatting."""
        lines = format_progress_lines(
            title="CLONING",
            device="USB Drive",
            mode="SMART",
            bytes_copied=None,
            total_bytes=None,
            rate=None,
            eta=None,
        )

        assert "CLONING" in lines
        assert "USB Drive" in lines
        assert "Mode SMART" in lines
        assert "Working..." in lines

    def test_format_progress_with_bytes(self):
        """Test progress formatting with bytes copied."""
        lines = format_progress_lines(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=50000000,  # 50MB
            total_bytes=100000000,  # 100MB
            rate=None,
            eta=None,
        )

        assert "CLONING" in lines
        assert "50.0%" in " ".join(lines)
        assert "Wrote" in " ".join(lines)

    def test_format_progress_with_rate(self):
        """Test progress formatting with transfer rate."""
        lines = format_progress_lines(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=50000000,
            total_bytes=100000000,
            rate=10485760,  # 10 MB/s
            eta=None,
        )

        rate_line = " ".join(lines)
        assert "/s" in rate_line

    def test_format_progress_with_eta(self):
        """Test progress formatting with ETA."""
        lines = format_progress_lines(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=50000000,
            total_bytes=100000000,
            rate=10485760,
            eta="00:05",
        )

        full_text = " ".join(lines)
        assert "ETA" in full_text
        assert "00:05" in full_text

    def test_format_progress_max_6_lines(self):
        """Test that output is limited to 6 lines."""
        lines = format_progress_lines(
            title="CLONING",
            device="Very Long Device Name",
            mode="SMART",
            bytes_copied=50000000,
            total_bytes=100000000,
            rate=10485760,
            eta="00:05",
        )

        assert len(lines) <= 6

    def test_format_progress_no_title(self):
        """Test progress formatting without title."""
        lines = format_progress_lines(
            title=None,
            device="USB Drive",
            mode=None,
            bytes_copied=None,
            total_bytes=None,
            rate=None,
            eta=None,
        )

        assert "USB Drive" in lines
        assert "Working..." in lines

    def test_format_progress_percentage_without_total(self):
        """Test percentage is not shown without total_bytes."""
        lines = format_progress_lines(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=50000000,
            total_bytes=None,
            rate=None,
            eta=None,
        )

        full_text = " ".join(lines)
        assert "%" not in full_text


class TestFormatProgressDisplay:
    """Tests for format_progress_display function (modern format)."""

    def test_format_display_basic(self):
        """Test basic display formatting."""
        lines = format_progress_display(
            title="CLONING",
            device="USB Drive",
            mode="SMART",
            bytes_copied=None,
            total_bytes=None,
            percent=None,
            rate=None,
            eta=None,
        )

        assert "CLONING" in lines
        assert "USB Drive" in lines
        assert "Mode SMART" in lines
        assert "Working..." in lines

    def test_format_display_with_spinner(self):
        """Test display formatting with spinner."""
        lines = format_progress_display(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=None,
            total_bytes=None,
            percent=None,
            rate=None,
            eta=None,
            spinner="|",
        )

        assert "CLONING |" in lines

    def test_format_display_with_subtitle(self):
        """Test display formatting with subtitle."""
        lines = format_progress_display(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=None,
            total_bytes=None,
            percent=None,
            rate=None,
            eta=None,
            subtitle="Partition 1/4",
        )

        assert "CLONING" in lines
        assert "Partition 1/4" in lines

    def test_format_display_bytes_and_total(self):
        """Test display with bytes copied and total."""
        lines = format_progress_display(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=50000000,
            total_bytes=100000000,
            percent=None,
            rate=None,
            eta=None,
        )

        full_text = " ".join(lines)
        assert "50.0%" in full_text
        assert "Wrote" in full_text

    def test_format_display_percent_only(self):
        """Test display with standalone percentage."""
        lines = format_progress_display(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=None,
            total_bytes=None,
            percent=75.5,
            rate=None,
            eta=None,
        )

        # Percentage without bytes shows "Working..."
        assert "Working..." in lines

    def test_format_display_bytes_with_percent_override(self):
        """Test bytes display with separate percentage value."""
        lines = format_progress_display(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=50000000,
            total_bytes=None,
            percent=80.0,
            rate=None,
            eta=None,
        )

        full_text = " ".join(lines)
        assert "80.0%" in full_text

    def test_format_display_with_rate_and_eta(self):
        """Test display with rate and ETA."""
        lines = format_progress_display(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=50000000,
            total_bytes=100000000,
            percent=None,
            rate=10485760,
            eta="00:05",
        )

        full_text = " ".join(lines)
        assert "/s" in full_text
        assert "ETA" in full_text
        assert "00:05" in full_text

    def test_format_display_max_6_lines(self):
        """Test that output is limited to 6 lines."""
        lines = format_progress_display(
            title="CLONING",
            device="Device",
            mode="SMART",
            bytes_copied=50000000,
            total_bytes=100000000,
            percent=None,
            rate=10485760,
            eta="00:05",
            subtitle="Subtitle",
        )

        assert len(lines) <= 6


class TestParseProgressFromOutput:
    """Tests for parse_progress_from_output function."""

    def test_parse_bytes_progress(self, mock_display_lines):
        """Test parsing bytes from output."""
        stderr_output = "12345678 bytes transferred\n"

        parse_progress_from_output(stderr_output)

        # Should have displayed progress
        assert mock_display_lines.call_count > 0

    def test_parse_percentage_progress(self, mock_display_lines):
        """Test parsing percentage from output."""
        stderr_output = "50.5% complete\n"

        parse_progress_from_output(stderr_output, total_bytes=None)

        # Should have displayed percentage
        assert mock_display_lines.call_count > 0
        # Check that percentage was shown
        calls_text = str(mock_display_lines.call_args_list)
        assert "50.5%" in calls_text

    def test_parse_bytes_with_total(self, mock_display_lines):
        """Test parsing bytes with total_bytes for percentage calculation."""
        stderr_output = "50000000 bytes\n"

        parse_progress_from_output(stderr_output, total_bytes=100000000)

        # Should calculate and display percentage
        calls_text = str(mock_display_lines.call_args_list)
        assert "50.0%" in calls_text

    def test_parse_empty_output(self, mock_display_lines):
        """Test parsing empty output."""
        parse_progress_from_output("")

        # Should not display anything
        assert mock_display_lines.call_count == 0

    def test_parse_none_output(self, mock_display_lines):
        """Test parsing None output."""
        parse_progress_from_output(None)

        # Should not display anything or crash
        assert mock_display_lines.call_count == 0

    def test_parse_multiline_output(self, mock_display_lines):
        """Test parsing multi-line output."""
        stderr_output = """Starting transfer...
10000000 bytes
25.0% complete
50000000 bytes
75.5% complete
100000000 bytes
Complete
"""

        parse_progress_from_output(stderr_output, total_bytes=100000000)

        # Should have displayed multiple progress updates
        assert mock_display_lines.call_count > 0

    def test_parse_custom_title(self, mock_display_lines):
        """Test parsing with custom title."""
        stderr_output = "12345678 bytes\n"

        parse_progress_from_output(stderr_output, title="CUSTOM")

        # Check that custom title was used
        calls_text = str(mock_display_lines.call_args_list)
        assert "CUSTOM" in calls_text

    def test_parse_no_progress_info(self, mock_display_lines):
        """Test parsing output with no progress information."""
        stderr_output = "Some random output without progress\n"

        parse_progress_from_output(stderr_output)

        # Should not display anything
        assert mock_display_lines.call_count == 0
@pytest.fixture
def mock_display_lines(monkeypatch):
    """Mock the display_lines function."""
    from unittest.mock import Mock

    mock = Mock()
    monkeypatch.setattr("rpi_usb_cloner.ui.display.display_lines", mock)
    return mock
