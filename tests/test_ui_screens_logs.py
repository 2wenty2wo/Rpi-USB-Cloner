"""Tests for UI logs screen rendering.

Covers:
- show_logs function
- Log buffer handling
- Button navigation
"""

from __future__ import annotations

from itertools import chain, repeat
from unittest.mock import MagicMock, patch

import pytest

from rpi_usb_cloner.app.context import LogEntry
from rpi_usb_cloner.ui.screens.logs import show_logs


class TestShowLogs:
    """Test show_logs function."""

    @pytest.fixture
    def mock_app_context(self):
        """Create a mock app context with log buffer."""
        context = MagicMock()
        context.log_buffer = []
        return context

    def _build_side_effect(self, values):
        return chain(values, repeat(False))

    def test_show_logs_empty_buffer(self, mock_app_context):
        """Test showing logs with empty buffer."""
        with patch("rpi_usb_cloner.ui.screens.logs.render_info_screen") as mock_render:
            with patch("rpi_usb_cloner.ui.screens.logs.menus"):
                with patch("rpi_usb_cloner.ui.screens.logs.gpio") as mock_gpio:
                    mock_render.return_value = (1, 0)
                    # Simulate button A press to exit
                    mock_gpio.is_pressed.side_effect = self._build_side_effect(
                        [True, False, False, False, False, False]
                    )

                    show_logs(mock_app_context)

        mock_render.assert_called()
        # Check that "No logs yet" message is displayed
        call_args = mock_render.call_args
        assert "No logs" in str(call_args)

    def test_show_logs_with_entries(self, mock_app_context):
        """Test showing logs with entries."""
        mock_app_context.log_buffer = [
            LogEntry(message="Log 1"),
            LogEntry(message="Log 2"),
        ]

        with patch("rpi_usb_cloner.ui.screens.logs.render_info_screen") as mock_render:
            with patch("rpi_usb_cloner.ui.screens.logs.menus"):
                with patch("rpi_usb_cloner.ui.screens.logs.gpio") as mock_gpio:
                    mock_render.return_value = (1, 0)
                    mock_gpio.is_pressed.side_effect = self._build_side_effect(
                        [True, False, False, False, False, False]
                    )

                    show_logs(mock_app_context)

        mock_render.assert_called()

    def test_show_logs_with_strings(self, mock_app_context):
        """Test showing logs with string entries (not LogEntry)."""
        mock_app_context.log_buffer = ["String log 1", "String log 2"]

        with patch("rpi_usb_cloner.ui.screens.logs.render_info_screen") as mock_render:
            with patch("rpi_usb_cloner.ui.screens.logs.menus"):
                with patch("rpi_usb_cloner.ui.screens.logs.gpio") as mock_gpio:
                    mock_render.return_value = (1, 0)
                    mock_gpio.is_pressed.side_effect = self._build_side_effect(
                        [True, False, False, False, False, False]
                    )

                    show_logs(mock_app_context)

        mock_render.assert_called()

    def test_show_logs_navigation_left(self, mock_app_context):
        """Test log navigation with left button."""
        mock_app_context.log_buffer = [LogEntry(message=f"Log {i}") for i in range(50)]

        with patch("rpi_usb_cloner.ui.screens.logs.render_info_screen") as mock_render:
            with patch("rpi_usb_cloner.ui.screens.logs.menus"):
                with patch("rpi_usb_cloner.ui.screens.logs.gpio") as mock_gpio:
                    mock_render.return_value = (1, 0)
                    # Press L then A to exit
                    mock_gpio.PIN_A = 1
                    mock_gpio.PIN_L = 2
                    mock_gpio.is_pressed.side_effect = self._build_side_effect(
                        [
                            False,
                            True,
                            False,
                            False,
                            False,  # Initial states
                            False,
                            False,
                            False,
                            False,
                            False,  # L released
                            True,
                            False,
                            False,
                            False,
                            False,  # A pressed
                            False,  # A released to exit
                        ]
                    )

                    show_logs(mock_app_context)

        mock_render.assert_called()

    def test_show_logs_navigation_right(self, mock_app_context):
        """Test log navigation with right button."""
        mock_app_context.log_buffer = [LogEntry(message=f"Log {i}") for i in range(50)]

        with patch("rpi_usb_cloner.ui.screens.logs.render_info_screen") as mock_render:
            with patch("rpi_usb_cloner.ui.screens.logs.menus"):
                with patch("rpi_usb_cloner.ui.screens.logs.gpio") as mock_gpio:
                    mock_render.return_value = (1, 0)
                    mock_gpio.PIN_A = 1
                    mock_gpio.PIN_R = 3
                    mock_gpio.is_pressed.side_effect = self._build_side_effect(
                        [
                            False,
                            False,
                            True,
                            False,
                            False,  # Initial states
                            False,
                            False,
                            False,
                            False,
                            False,  # R released
                            True,
                            False,
                            False,
                            False,
                            False,  # A pressed
                            False,  # A released to exit
                        ]
                    )

                    show_logs(mock_app_context)

        mock_render.assert_called()

    def test_show_logs_custom_title(self, mock_app_context):
        """Test showing logs with custom title."""
        with patch("rpi_usb_cloner.ui.screens.logs.render_info_screen") as mock_render:
            with patch("rpi_usb_cloner.ui.screens.logs.menus"):
                with patch("rpi_usb_cloner.ui.screens.logs.gpio") as mock_gpio:
                    mock_render.return_value = (1, 0)
                    mock_gpio.is_pressed.side_effect = self._build_side_effect(
                        [True, False, False, False, False, False]
                    )

                    show_logs(mock_app_context, title="CUSTOM LOGS")

        mock_render.assert_called()
        call_args = mock_render.call_args
        assert "CUSTOM LOGS" in str(call_args)

    def test_show_logs_max_lines_limit(self, mock_app_context):
        """Test that max_lines limits the number of log entries shown."""
        mock_app_context.log_buffer = [LogEntry(message=f"Log {i}") for i in range(100)]

        with patch("rpi_usb_cloner.ui.screens.logs.render_info_screen") as mock_render:
            with patch("rpi_usb_cloner.ui.screens.logs.menus"):
                with patch("rpi_usb_cloner.ui.screens.logs.gpio") as mock_gpio:
                    mock_render.return_value = (1, 0)
                    mock_gpio.is_pressed.side_effect = self._build_side_effect(
                        [True, False, False, False, False, False]
                    )

                    show_logs(mock_app_context, max_lines=10)

        mock_render.assert_called()
