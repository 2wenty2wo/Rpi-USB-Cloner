"""Tests for UI error screen rendering.

Covers:
- render_error_screen function
- Error message formatting and display
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from rpi_usb_cloner.ui.screens.error import render_error_screen


class TestRenderErrorScreen:
    """Test render_error_screen function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock app context with display."""
        context = MagicMock()
        context.display = MagicMock()
        context.display.device = MagicMock()
        context.display.title_font = MagicMock()
        context.display.font = MagicMock()
        context.display.icon_font = MagicMock()
        context.display.width = 128
        context.display.height = 64
        return context

    def test_render_error_basic(self, mock_context):
        """Test basic error screen rendering."""
        # Create a real image for the draw operations
        test_image = Image.new("1", (128, 64), 0)

        with patch(
            "rpi_usb_cloner.ui.screens.error.Image.new", return_value=test_image
        ), patch("rpi_usb_cloner.ui.screens.error.render_status_bar"):
            render_error_screen(
                mock_context,
                title="Error",
                message="Something went wrong",
            )

        # Verify display was updated
        mock_context.display.device.display.assert_called_once()
        assert mock_context.current_screen_image is not None

    def test_render_error_with_exception(self, mock_context):
        """Test error screen rendering with exception details."""
        test_image = Image.new("1", (128, 64), 0)
        exception = ValueError("Test exception")

        with patch(
            "rpi_usb_cloner.ui.screens.error.Image.new", return_value=test_image
        ), patch("rpi_usb_cloner.ui.screens.error.render_status_bar"):
            render_error_screen(
                mock_context,
                title="Clone Failed",
                message="Could not write to device",
                exception=exception,
            )

        mock_context.display.device.display.assert_called_once()

    def test_render_error_long_message(self, mock_context):
        """Test error screen with long message handling."""
        test_image = Image.new("1", (128, 64), 0)
        long_message = "This is a very long error message that might need special handling in the display"

        with patch(
            "rpi_usb_cloner.ui.screens.error.Image.new", return_value=test_image
        ), patch("rpi_usb_cloner.ui.screens.error.render_status_bar"):
            render_error_screen(
                mock_context,
                title="Error",
                message=long_message,
            )

        mock_context.display.device.display.assert_called_once()
