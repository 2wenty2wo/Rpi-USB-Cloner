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
        test_image = Image.new("1", (128, 64), 0)
        mock_context.draw = MagicMock()
        mock_context.image = test_image
        mock_context.disp = MagicMock()
        mock_context.width = 128
        mock_context.height = 64
        mock_context.top = 0
        mock_context.x = 0
        mock_context.fontdisks = MagicMock()
        mock_context.fontdisks.getbbox.return_value = (0, 0, 10, 10)
        mock_context.fonts = MagicMock()
        mock_context.fonts.get.return_value = mock_context.fontdisks

        layout = MagicMock()
        layout.content_top = 0
        with patch(
            "rpi_usb_cloner.ui.screens.error.display.get_display_context",
            return_value=mock_context,
        ), patch(
            "rpi_usb_cloner.ui.screens.error.display.draw_title_with_icon",
            return_value=layout,
        ):
            render_error_screen(
                title="Error",
                message="Something went wrong",
            )

        mock_context.disp.display.assert_called_once()

    def test_render_error_with_exception(self, mock_context):
        """Test error screen rendering with exception details."""
        test_image = Image.new("1", (128, 64), 0)
        mock_context.draw = MagicMock()
        mock_context.image = test_image
        mock_context.disp = MagicMock()
        mock_context.width = 128
        mock_context.height = 64
        mock_context.top = 0
        mock_context.x = 0
        mock_context.fontdisks = MagicMock()
        mock_context.fontdisks.getbbox.return_value = (0, 0, 10, 10)
        mock_context.fonts = MagicMock()
        mock_context.fonts.get.return_value = mock_context.fontdisks

        layout = MagicMock()
        layout.content_top = 0
        with patch(
            "rpi_usb_cloner.ui.screens.error.display.get_display_context",
            return_value=mock_context,
        ), patch(
            "rpi_usb_cloner.ui.screens.error.display.draw_title_with_icon",
            return_value=layout,
        ):
            render_error_screen(
                title="Clone Failed",
                message="Could not write to device",
            )

        mock_context.disp.display.assert_called_once()

    def test_render_error_long_message(self, mock_context):
        """Test error screen with long message handling."""
        test_image = Image.new("1", (128, 64), 0)
        long_message = "This is a very long error message that might need special handling in the display"
        mock_context.draw = MagicMock()
        mock_context.image = test_image
        mock_context.disp = MagicMock()
        mock_context.width = 128
        mock_context.height = 64
        mock_context.top = 0
        mock_context.x = 0
        mock_context.fontdisks = MagicMock()
        mock_context.fontdisks.getbbox.return_value = (0, 0, 10, 10)
        mock_context.fonts = MagicMock()
        mock_context.fonts.get.return_value = mock_context.fontdisks

        layout = MagicMock()
        layout.content_top = 0
        with patch(
            "rpi_usb_cloner.ui.screens.error.display.get_display_context",
            return_value=mock_context,
        ), patch(
            "rpi_usb_cloner.ui.screens.error.display.draw_title_with_icon",
            return_value=layout,
        ):
            render_error_screen(
                title="Error",
                message=long_message,
            )

        mock_context.disp.display.assert_called_once()
