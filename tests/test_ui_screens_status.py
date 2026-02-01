"""Tests for UI status screen rendering.

Covers:
- render_status_screen function
- render_status_template function
- show_coming_soon function
- wait_for_ack function
"""

from __future__ import annotations

from unittest.mock import patch

from rpi_usb_cloner.ui.screens.status import (
    render_status_screen,
    render_status_template,
    show_coming_soon,
    wait_for_ack,
)


class TestRenderStatusScreen:
    """Test render_status_screen function."""

    def test_render_status_screen_basic(self):
        """Test basic status screen rendering."""
        with patch("rpi_usb_cloner.ui.screens.status.display") as mock_display:
            render_status_screen(
                title="Success",
                status="Operation completed",
            )

        mock_display.render_paginated_lines.assert_called_once()
        call_args = mock_display.render_paginated_lines.call_args
        assert call_args.kwargs["title"] == "Success"

    def test_render_status_screen_with_progress(self):
        """Test status screen with progress line."""
        with patch("rpi_usb_cloner.ui.screens.status.display") as mock_display:
            render_status_screen(
                title="Progress",
                status="Working...",
                progress_line="50% complete",
            )

        mock_display.render_paginated_lines.assert_called_once()
        call_args = mock_display.render_paginated_lines.call_args
        lines = call_args.args[1]
        assert "50% complete" in lines

    def test_render_status_screen_with_extra_lines(self):
        """Test status screen with extra lines."""
        with patch("rpi_usb_cloner.ui.screens.status.display") as mock_display:
            render_status_screen(
                title="Info",
                status="Main status",
                extra_lines=["Line 1", "Line 2"],
            )

        mock_display.render_paginated_lines.assert_called_once()
        call_args = mock_display.render_paginated_lines.call_args
        lines = call_args.args[1]
        assert "Line 1" in lines
        assert "Line 2" in lines


class TestRenderStatusTemplate:
    """Test render_status_template function."""

    def test_render_status_template_with_icon(self):
        """Test status template with icon."""
        with patch("rpi_usb_cloner.ui.screens.status.display") as mock_display:
            render_status_template(
                title="Done",
                status="Complete",
                title_icon="check",
            )

        mock_display.render_paginated_lines.assert_called_once()
        call_args = mock_display.render_paginated_lines.call_args
        assert call_args.kwargs["title_icon"] == "check"


class TestShowComingSoon:
    """Test show_coming_soon function."""

    def test_show_coming_soon_default(self):
        """Test show_coming_soon with default parameters."""
        with patch("rpi_usb_cloner.ui.screens.status.display") as mock_display, patch(
            "rpi_usb_cloner.ui.screens.status.time.sleep"
        ) as mock_sleep:
            show_coming_soon()

        mock_display.display_lines.assert_called_once()
        mock_sleep.assert_called_once_with(1)

    def test_show_coming_soon_custom_title(self):
        """Test show_coming_soon with custom title."""
        with patch("rpi_usb_cloner.ui.screens.status.display") as mock_display, patch(
            "rpi_usb_cloner.ui.screens.status.time.sleep"
        ):
            show_coming_soon(title="NOT READY")

        call_args = mock_display.display_lines.call_args
        lines = call_args.args[0]
        assert "NOT READY" in lines

    def test_show_coming_soon_no_delay(self):
        """Test show_coming_soon with no delay."""
        with patch("rpi_usb_cloner.ui.screens.status.display"), patch(
            "rpi_usb_cloner.ui.screens.status.time.sleep"
        ) as mock_sleep:
            show_coming_soon(delay=0)

        mock_sleep.assert_not_called()


class TestWaitForAck:
    """Test wait_for_ack function."""

    def test_wait_for_ack_default_buttons(self):
        """Test wait_for_ack with default buttons."""
        with patch("rpi_usb_cloner.ui.screens.status.menus") as mock_menus, patch(
            "rpi_usb_cloner.ui.screens.status.gpio"
        ) as mock_gpio:
            mock_gpio.PIN_A = 1
            mock_gpio.PIN_B = 2
            mock_gpio.poll_button_events.return_value = None

            wait_for_ack()

        mock_menus.wait_for_buttons_release.assert_called_once()
        mock_gpio.poll_button_events.assert_called_once()

    def test_wait_for_ack_custom_buttons(self):
        """Test wait_for_ack with custom buttons."""
        with patch("rpi_usb_cloner.ui.screens.status.menus") as mock_menus, patch(
            "rpi_usb_cloner.ui.screens.status.gpio"
        ) as mock_gpio:
            mock_gpio.poll_button_events.return_value = None

            wait_for_ack(buttons=[5, 6])

        mock_menus.wait_for_buttons_release.assert_called_once()
        call_args = mock_menus.wait_for_buttons_release.call_args
        assert set(call_args.args[0]) == {5, 6}
