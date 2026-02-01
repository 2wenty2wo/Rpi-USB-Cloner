"""
Tests for app/drive_info.py module.

Covers:
- get_device_status_line function
- render_drive_info function
"""

from __future__ import annotations

from unittest.mock import Mock

from rpi_usb_cloner.app.drive_info import get_device_status_line, render_drive_info


class TestGetDeviceStatusLine:
    """Test get_device_status_line function."""

    def test_no_devices_returns_insert_usb(self):
        """Test returns 'INSERT USB' when no devices."""
        result = get_device_status_line(
            active_drive="sda",
            list_media_devices=list,
            get_device_name=lambda d: d["name"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
        )
        assert result == "INSERT USB"

    def test_active_drive_found_with_vendor_model(self):
        """Test returns vendor + model when active drive found."""
        devices = [
            {"name": "sda", "vendor": "Kingston", "model": "DataTraveler"},
            {"name": "sdb", "vendor": "SanDisk", "model": "Ultra"},
        ]
        result = get_device_status_line(
            active_drive="sda",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
        )
        assert result == "Kingston DataTraveler"

    def test_active_drive_found_vendor_only(self):
        """Test returns vendor only when model is empty."""
        devices = [
            {"name": "sda", "vendor": "Kingston", "model": ""},
        ]
        result = get_device_status_line(
            active_drive="sda",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
        )
        assert result == "Kingston"

    def test_active_drive_found_model_only(self):
        """Test returns model only when vendor is None."""
        devices = [
            {"name": "sda", "vendor": None, "model": "DataTraveler"},
        ]
        result = get_device_status_line(
            active_drive="sda",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
        )
        assert result == "DataTraveler"

    def test_active_drive_found_no_vendor_model(self):
        """Test returns device name when no vendor/model."""
        devices = [
            {"name": "sda", "vendor": None, "model": None},
        ]
        result = get_device_status_line(
            active_drive="sda",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
        )
        assert result == "sda"

    def test_active_drive_not_in_list(self):
        """Test returns 'NO DRIVE SELECTED' when active drive not found."""
        devices = [
            {"name": "sda", "vendor": "Kingston", "model": "DataTraveler"},
        ]
        result = get_device_status_line(
            active_drive="sdb",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
        )
        assert result == "NO DRIVE SELECTED"

    def test_vendor_model_whitespace_stripped(self):
        """Test that vendor/model whitespace is stripped."""
        devices = [
            {"name": "sda", "vendor": "  Kingston  ", "model": "  DataTraveler  "},
        ]
        result = get_device_status_line(
            active_drive="sda",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
        )
        assert result == "Kingston DataTraveler"


class TestRenderDriveInfo:
    """Test render_drive_info function."""

    def test_no_active_drive_displays_no_drive(self):
        """Test displays 'NO DRIVE SELECTED' when no active drive."""
        mock_display = Mock()

        render_drive_info(
            active_drive=None,
            list_media_devices=list,
            get_device_name=lambda d: d["name"],
            get_size=lambda d: d["size"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
            display_module=mock_display,
            screens_module=Mock(),
            page_index=0,
        )

        mock_display.display_lines.assert_called_once_with(["NO DRIVE", "SELECTED"])

    def test_active_drive_not_found_displays_no_drive(self):
        """Test displays 'NO DRIVE SELECTED' when drive not in list."""
        mock_display = Mock()
        devices = [{"name": "sdb", "size": 16000000000}]

        result = render_drive_info(
            active_drive="sda",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_size=lambda d: d["size"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
            display_module=mock_display,
            screens_module=Mock(),
            page_index=0,
        )

        mock_display.display_lines.assert_called_once_with(["NO DRIVE", "SELECTED"])
        assert result == (1, 0)

    def test_drive_found_renders_info_screen(self):
        """Test renders info screen when drive is found."""
        mock_screens = Mock()
        mock_display = Mock()
        mock_display_context = Mock()
        mock_display_context.fontcopy = Mock()
        mock_display.get_display_context.return_value = mock_display_context

        devices = [
            {
                "name": "sda",
                "size": 16106127360,
                "vendor": "Kingston",
                "model": "DataTraveler",
            },
        ]

        render_drive_info(
            active_drive="sda",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_size=lambda d: d["size"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
            display_module=mock_display,
            screens_module=mock_screens,
            page_index=0,
        )

        # Check that render_info_screen was called
        mock_screens.render_info_screen.assert_called_once()
        call_args = mock_screens.render_info_screen.call_args

        # Verify title (first positional arg or kwarg)
        title = call_args[0][0] if call_args[0] else call_args.kwargs.get("title")
        assert title == "DRIVE INFO"

        # Verify info lines (second positional arg or kwarg)
        info_lines = (
            call_args[0][1] if call_args[0] else call_args.kwargs.get("info_lines")
        )
        assert len(info_lines) == 2
        assert "sda" in info_lines[0]
        assert "15.00GB" in info_lines[0] or "14.99GB" in info_lines[0]
        assert "Kingston" in info_lines[1]
        assert "DataTraveler" in info_lines[1]

    def test_drive_found_no_vendor_model(self):
        """Test renders info screen with only device name when no vendor/model."""
        mock_screens = Mock()
        mock_display = Mock()
        mock_display_context = Mock()
        mock_display_context.fontcopy = Mock()
        mock_display.get_display_context.return_value = mock_display_context

        devices = [
            {"name": "sda", "size": 16106127360, "vendor": None, "model": None},
        ]

        render_drive_info(
            active_drive="sda",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_size=lambda d: d["size"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
            display_module=mock_display,
            screens_module=mock_screens,
            page_index=0,
        )

        call_args = mock_screens.render_info_screen.call_args
        info_lines = (
            call_args[0][1] if call_args[0] else call_args.kwargs.get("info_lines")
        )
        # Should only have one line (device name + size)
        assert len(info_lines) == 1
        assert "sda" in info_lines[0]

    def test_size_conversion_to_gb(self):
        """Test that size is correctly converted to GB."""
        mock_screens = Mock()
        mock_display = Mock()
        mock_display_context = Mock()
        mock_display_context.fontcopy = Mock()
        mock_display.get_display_context.return_value = mock_display_context

        # 8 GB in bytes
        size_bytes = 8 * 1024**3
        devices = [{"name": "sda", "size": size_bytes, "vendor": None, "model": None}]

        render_drive_info(
            active_drive="sda",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_size=lambda d: d["size"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
            display_module=mock_display,
            screens_module=mock_screens,
            page_index=0,
        )

        call_args = mock_screens.render_info_screen.call_args
        info_lines = (
            call_args[0][1] if call_args[0] else call_args.kwargs.get("info_lines")
        )
        assert "8.00GB" in info_lines[0]

    def test_page_index_passed_to_render(self):
        """Test that page_index is passed to render_info_screen."""
        mock_screens = Mock()
        mock_display = Mock()
        mock_display_context = Mock()
        mock_display_context.fontcopy = Mock()
        mock_display.get_display_context.return_value = mock_display_context

        devices = [{"name": "sda", "size": 10000000000}]

        render_drive_info(
            active_drive="sda",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_size=lambda d: d["size"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
            display_module=mock_display,
            screens_module=mock_screens,
            page_index=2,
        )

        call_args = mock_screens.render_info_screen.call_args
        assert call_args.kwargs["page_index"] == 2

    def test_title_icon_passed_to_render(self):
        """Test that DRIVES_ICON is passed to render_info_screen."""
        mock_screens = Mock()
        mock_display = Mock()
        mock_display_context = Mock()
        mock_display_context.fontcopy = Mock()
        mock_display.get_display_context.return_value = mock_display_context

        devices = [{"name": "sda", "size": 10000000000}]

        render_drive_info(
            active_drive="sda",
            list_media_devices=lambda: devices,
            get_device_name=lambda d: d["name"],
            get_size=lambda d: d["size"],
            get_vendor=lambda d: d.get("vendor"),
            get_model=lambda d: d.get("model"),
            display_module=mock_display,
            screens_module=mock_screens,
            page_index=0,
        )

        call_args = mock_screens.render_info_screen.call_args
        from rpi_usb_cloner.ui.icons import DRIVES_ICON

        assert call_args.kwargs["title_icon"] == DRIVES_ICON
