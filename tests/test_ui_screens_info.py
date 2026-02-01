"""Tests for UI info and paginated screen rendering.

Covers:
- render_info_screen function
- render_key_value_screen function
- wait_for_paginated_input function
- wait_for_paginated_key_value_input function
- wait_for_scrollable_key_value_input function
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rpi_usb_cloner.ui.screens.info import (
    render_info_screen,
    render_key_value_screen,
    wait_for_paginated_input,
    wait_for_paginated_key_value_input,
    wait_for_scrollable_key_value_input,
)


class TestRenderInfoScreen:
    """Test render_info_screen function."""

    def test_render_info_screen_basic(self):
        """Test basic info screen rendering."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            mock_display.render_paginated_lines.return_value = (1, 0)
            
            result = render_info_screen("Info", ["Line 1", "Line 2"])
            
            mock_display.render_paginated_lines.assert_called_once()
            assert result == (1, 0)

    def test_render_info_screen_with_icon(self):
        """Test info screen with title icon."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            mock_display.render_paginated_lines.return_value = (1, 0)
            
            render_info_screen("Info", ["Line 1"], title_icon="info")
            
            call_args = mock_display.render_paginated_lines.call_args
            assert call_args.kwargs["title_icon"] == "info"

    def test_render_info_screen_custom_page(self):
        """Test info screen with custom page index."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            mock_display.render_paginated_lines.return_value = (3, 2)
            
            result = render_info_screen("Info", ["Line 1"] * 100, page_index=2)
            
            call_args = mock_display.render_paginated_lines.call_args
            assert call_args.kwargs["page_index"] == 2


class TestRenderKeyValueScreen:
    """Test render_key_value_screen function."""

    def test_render_key_value_screen_basic(self):
        """Test basic key-value screen rendering."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            mock_display.render_paginated_key_value_lines.return_value = (1, 0)
            
            lines = [("Key1", "Value1"), ("Key2", "Value2")]
            result = render_key_value_screen("Settings", lines)
            
            mock_display.render_paginated_key_value_lines.assert_called_once()
            assert result == (1, 0)

    def test_render_key_value_screen_with_icon(self):
        """Test key-value screen with icon."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            mock_display.render_paginated_key_value_lines.return_value = (1, 0)
            
            lines = [("Key", "Value")]
            render_key_value_screen("Settings", lines, title_icon="settings")
            
            call_args = mock_display.render_paginated_key_value_lines.call_args
            assert call_args.kwargs["title_icon"] == "settings"


class TestWaitForPaginatedInput:
    """Test wait_for_paginated_input function."""

    def test_wait_for_paginated_button_a(self):
        """Test paginated input exits on button A."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            with patch("rpi_usb_cloner.ui.screens.info.menus"):
                with patch("rpi_usb_cloner.ui.screens.info.gpio") as mock_gpio:
                    mock_gpio.PIN_A = 1
                    mock_gpio.PIN_B = 2
                    mock_gpio.PIN_L = 3
                    mock_gpio.PIN_R = 4
                    mock_gpio.PIN_U = 5
                    mock_gpio.PIN_D = 6
                    mock_gpio.is_pressed.return_value = False
                    mock_gpio.is_pressed.side_effect = [
                        True, True, True, True, True, True,  # Initial states
                        False, False, False, False, False, False,  # Released
                        True, False, False, False, False, False,  # A pressed
                        False, False, False, False, False, False,  # A released (exit)
                    ]
                    
                    mock_display.render_paginated_lines.return_value = (1, 0)
                    wait_for_paginated_input("Title", ["Line"])

    def test_wait_for_paginated_button_b(self):
        """Test paginated input exits on button B."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            with patch("rpi_usb_cloner.ui.screens.info.menus"):
                with patch("rpi_usb_cloner.ui.screens.info.gpio") as mock_gpio:
                    mock_gpio.PIN_A = 1
                    mock_gpio.PIN_B = 2
                    mock_gpio.is_pressed.return_value = False
                    mock_gpio.is_pressed.side_effect = [
                        True, True, True, True, True, True,
                        False, False, False, False, False, False,
                        False, True, False, False, False, False,  # B pressed
                        False, False, False, False, False, False,
                    ]
                    
                    mock_display.render_paginated_lines.return_value = (1, 0)
                    wait_for_paginated_input("Title", ["Line"])

    def test_wait_for_paginated_navigation(self):
        """Test paginated navigation with arrow buttons."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            with patch("rpi_usb_cloner.ui.screens.info.menus"):
                with patch("rpi_usb_cloner.ui.screens.info.gpio") as mock_gpio:
                    mock_gpio.PIN_A = 1
                    mock_gpio.PIN_R = 4
                    mock_gpio.is_pressed.return_value = False
                    mock_gpio.is_pressed.side_effect = [
                        True, True, True, True, True, True,
                        False, False, False, False, False, False,
                        False, False, False, True, False, False,  # R pressed
                        False, False, False, False, False, False,
                        True, False, False, False, False, False,  # A pressed to exit
                        False, False, False, False, False, False,
                    ]
                    
                    mock_display.render_paginated_lines.return_value = (3, 0)
                    wait_for_paginated_input("Title", ["Line"] * 50)

    def test_wait_for_paginated_single_page_no_nav(self):
        """Test that navigation buttons don't work with single page."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            with patch("rpi_usb_cloner.ui.screens.info.menus"):
                with patch("rpi_usb_cloner.ui.screens.info.gpio") as mock_gpio:
                    mock_gpio.PIN_A = 1
                    mock_gpio.is_pressed.return_value = False
                    mock_gpio.is_pressed.side_effect = [
                        True, True, True, True, True, True,
                        False, False, False, False, False, False,
                        True, False, False, False, False, False,
                        False, False, False, False, False, False,
                    ]
                    
                    mock_display.render_paginated_lines.return_value = (1, 0)
                    wait_for_paginated_input("Title", ["Line"])


class TestWaitForPaginatedKeyValueInput:
    """Test wait_for_paginated_key_value_input function."""

    def test_wait_for_paginated_kv_basic(self):
        """Test paginated key-value input."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            with patch("rpi_usb_cloner.ui.screens.info.menus"):
                with patch("rpi_usb_cloner.ui.screens.info.gpio") as mock_gpio:
                    mock_gpio.PIN_A = 1
                    mock_gpio.is_pressed.return_value = False
                    mock_gpio.is_pressed.side_effect = [
                        True, True, True, True, True, True,
                        False, False, False, False, False, False,
                        True, False, False, False, False, False,
                        False, False, False, False, False, False,
                    ]
                    
                    mock_display.render_paginated_key_value_lines.return_value = (1, 0)
                    lines = [("Key", "Value")]
                    wait_for_paginated_key_value_input("Title", lines)


class TestWaitForScrollableKeyValueInput:
    """Test wait_for_scrollable_key_value_input function."""

    def test_scrollable_kv_basic(self):
        """Test scrollable key-value input basic flow."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            with patch("rpi_usb_cloner.ui.screens.info.menus"):
                with patch("rpi_usb_cloner.ui.screens.info.gpio") as mock_gpio:
                    mock_gpio.PIN_A = 1
                    mock_gpio.is_pressed.return_value = False
                    mock_gpio.is_pressed.side_effect = [
                        True, True, True, True, True, True,
                        False, False, False, False, False, False,
                        True, False, False, False, False, False,
                        False, False, False, False, False, False,
                    ]
                    
                    mock_context = MagicMock()
                    mock_display.get_display_context.return_value = mock_context
                    mock_display.render_scrollable_key_value_lines.return_value = (10, 0)
                    
                    lines = [(f"Key{i}", f"Value{i}") for i in range(20)]
                    wait_for_scrollable_key_value_input("Title", lines)

    def test_scrollable_kv_with_transition(self):
        """Test scrollable key-value with slide transition."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            with patch("rpi_usb_cloner.ui.screens.info.menus"):
                with patch("rpi_usb_cloner.ui.screens.info.gpio") as mock_gpio:
                    with patch("rpi_usb_cloner.ui.screens.info.transitions"):
                        mock_gpio.PIN_A = 1
                        mock_gpio.is_pressed.return_value = False
                        mock_gpio.is_pressed.side_effect = [
                            True, True, True, True, True, True,
                            False, False, False, False, False, False,
                            True, False, False, False, False, False,
                            False, False, False, False, False, False,
                        ]
                        
                        mock_context = MagicMock()
                        mock_display.get_display_context.return_value = mock_context
                        mock_display.render_scrollable_key_value_lines.return_value = (10, 0)
                        mock_display.render_scrollable_key_value_lines_image.return_value = (MagicMock(), 20, 0)
                        
                        lines = [(f"Key{i}", f"Value{i}") for i in range(20)]
                        wait_for_scrollable_key_value_input("Title", lines, transition_direction="forward")

    def test_scrollable_kv_scroll_up_down(self):
        """Test scrollable key-value with up/down scrolling."""
        with patch("rpi_usb_cloner.ui.screens.info.display") as mock_display:
            with patch("rpi_usb_cloner.ui.screens.info.menus"):
                with patch("rpi_usb_cloner.ui.screens.info.gpio") as mock_gpio:
                    mock_gpio.PIN_A = 1
                    mock_gpio.PIN_U = 5
                    mock_gpio.PIN_D = 6
                    mock_gpio.is_pressed.return_value = False
                    mock_gpio.is_pressed.side_effect = [
                        True, True, True, True, True, True,
                        False, False, False, False, False, False,
                        False, False, False, False, True, False,  # U pressed
                        False, False, False, False, False, False,
                        False, False, False, False, False, True,  # D pressed
                        False, False, False, False, False, False,
                        True, False, False, False, False, False,  # A to exit
                        False, False, False, False, False, False,
                    ]
                    
                    mock_context = MagicMock()
                    mock_display.get_display_context.return_value = mock_context
                    mock_display.render_scrollable_key_value_lines.return_value = (20, 0)
                    
                    lines = [(f"Key{i}", f"Value{i}") for i in range(30)]
                    wait_for_scrollable_key_value_input("Title", lines)
