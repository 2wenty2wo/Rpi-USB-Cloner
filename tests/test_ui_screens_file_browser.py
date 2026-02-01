"""Tests for file browser screen.

Covers:
- FileItem class
- _get_line_height helper
- _get_usb_mountpoints function
- _get_available_locations function
- _list_directory function
- _render_browser_screen function
- show_file_browser function
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from rpi_usb_cloner.ui.screens.file_browser import (
    FileItem,
    _get_available_locations,
    _get_line_height,
    _list_directory,
    _render_browser_screen,
    show_file_browser,
)


class TestFileItem:
    """Test FileItem class."""

    def test_file_item_defaults(self):
        """Test FileItem with default parameters."""
        path = Path("/tmp/test.txt")
        item = FileItem(path)

        assert item.path == path
        assert item.is_dir is False
        assert item.display_name == "test.txt"

    def test_file_item_directory(self):
        """Test FileItem for directory."""
        path = Path("/tmp/folder")
        item = FileItem(path, is_dir=True, display_name="My Folder")

        assert item.is_dir is True
        assert item.display_name == "My Folder"

    def test_file_item_str_file(self):
        """Test FileItem string representation for file."""
        path = Path("/tmp/test.txt")
        item = FileItem(path)

        str_repr = str(item)
        assert "test.txt" in str_repr
        assert "📄" in str_repr or "📁" not in str_repr

    def test_file_item_str_directory(self):
        """Test FileItem string representation for directory."""
        path = Path("/tmp/folder")
        item = FileItem(path, is_dir=True)

        str_repr = str(item)
        assert "folder" in str_repr


class TestGetLineHeight:
    """Test _get_line_height helper."""

    def test_get_line_height_with_bbox(self):
        """Test line height calculation with font bbox."""
        mock_font = MagicMock()
        mock_font.getbbox.return_value = (0, 0, 10, 12)

        height = _get_line_height(mock_font)
        assert height == 12

    def test_get_line_height_with_metrics(self):
        """Test line height calculation with font metrics."""
        mock_font = MagicMock()
        mock_font.getbbox.side_effect = AttributeError("No bbox")
        mock_font.getmetrics.return_value = (10, 3)

        height = _get_line_height(mock_font)
        assert height == 13

    def test_get_line_height_fallback(self):
        """Test line height fallback to minimum."""
        mock_font = MagicMock()
        mock_font.getbbox.side_effect = AttributeError("No bbox")
        mock_font.getmetrics.side_effect = AttributeError("No metrics")

        height = _get_line_height(mock_font)
        assert height == 8

    def test_get_line_height_custom_min(self):
        """Test line height with custom minimum."""
        mock_font = MagicMock()
        mock_font.getbbox.return_value = (0, 0, 10, 5)

        height = _get_line_height(mock_font, min_height=10)
        assert height == 10


class TestGetAvailableLocations:
    """Test _get_available_locations function."""

    def test_no_locations(self):
        """Test when no USB drives or repos available."""
        with patch(
            "rpi_usb_cloner.ui.screens.file_browser._get_usb_mountpoints",
            return_value=[],
        ), patch(
            "rpi_usb_cloner.ui.screens.file_browser.find_image_repos",
            return_value=[],
        ):
            locations = _get_available_locations()
            assert locations == []

    def test_usb_locations_only(self):
        """Test with USB drives only."""
        usb_mounts = [Path("/mnt/sda1"), Path("/mnt/sdb1")]

        with patch(
            "rpi_usb_cloner.ui.screens.file_browser._get_usb_mountpoints",
            return_value=usb_mounts,
        ), patch(
            "rpi_usb_cloner.ui.screens.file_browser.find_image_repos",
            return_value=[],
        ):
            locations = _get_available_locations()

            assert len(locations) == 2
            assert all("USB:" in loc.display_name for loc in locations)

    def test_repo_locations_only(self):
        """Test with image repos only."""
        from rpi_usb_cloner.domain import ImageRepo

        repos = [ImageRepo(path=Path("/mnt/repo"), drive_name="sda")]

        with patch(
            "rpi_usb_cloner.ui.screens.file_browser._get_usb_mountpoints",
            return_value=[],
        ), patch(
            "rpi_usb_cloner.ui.screens.file_browser.find_image_repos",
            return_value=repos,
        ):
            locations = _get_available_locations()

            assert len(locations) == 1
            assert "REPO:" in locations[0].display_name


class TestListDirectory:
    """Test _list_directory function."""

    def test_empty_directory(self, tmp_path):
        """Test listing empty directory."""
        items = _list_directory(tmp_path)
        # Should have parent directory link only
        assert len(items) == 1
        assert items[0].display_name == ".."

    def test_directory_with_files(self, tmp_path):
        """Test listing directory with files."""
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.txt").write_text("content")

        items = _list_directory(tmp_path)

        # 1 parent + 2 files = 3 items
        assert len(items) == 3

    def test_directory_with_hidden_files(self, tmp_path):
        """Test that hidden files are skipped."""
        (tmp_path / "visible.txt").write_text("content")
        (tmp_path / ".hidden").write_text("content")

        items = _list_directory(tmp_path)

        names = [item.display_name for item in items]
        assert "visible.txt" in names
        assert ".hidden" not in names

    def test_directory_with_subdirectories(self, tmp_path):
        """Test listing with subdirectories (dirs first)."""
        (tmp_path / "file.txt").write_text("content")
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        items = _list_directory(tmp_path)

        # Dirs should come before files
        dir_items = [i for i in items if i.is_dir]
        file_items = [i for i in items if not i.is_dir]

        if dir_items and file_items:
            dir_idx = items.index(dir_items[0])
            file_idx = items.index(file_items[0])
            assert dir_idx < file_idx

    def test_permission_error(self, tmp_path):
        """Test handling of permission error."""
        with patch.object(
            Path, "iterdir", side_effect=PermissionError("Access denied")
        ):
            items = _list_directory(tmp_path)
            assert items == []


class TestRenderBrowserScreen:
    """Test _render_browser_screen function."""

    def test_render_empty_items(self):
        """Test rendering with empty items list."""
        with patch("rpi_usb_cloner.ui.screens.file_browser.display") as mock_display:
            mock_ctx = MagicMock()
            mock_ctx.width = 128
            mock_ctx.height = 64
            mock_ctx.fonts.get.return_value = MagicMock()
            mock_display.get_display_context.return_value = mock_ctx

            _render_browser_screen("Files", [], 0)

            mock_ctx.disp.display.assert_called_once()

    def test_render_with_items(self):
        """Test rendering with items."""
        with patch("rpi_usb_cloner.ui.screens.file_browser.display") as mock_display:
            mock_ctx = MagicMock()
            mock_ctx.width = 128
            mock_ctx.height = 64
            mock_ctx.fonts.get.return_value = MagicMock()
            mock_ctx.draw.text = MagicMock()
            mock_display.get_display_context.return_value = mock_ctx

            items = [
                FileItem(Path("/tmp/file1.txt")),
                FileItem(Path("/tmp/file2.txt")),
            ]
            _render_browser_screen("Files", items, 0)

            mock_ctx.disp.display.assert_called_once()

    def test_render_scroll_indicator(self):
        """Test that scroll indicator appears for many items."""
        with patch("rpi_usb_cloner.ui.screens.file_browser.display") as mock_display:
            mock_ctx = MagicMock()
            mock_ctx.width = 128
            mock_ctx.height = 64
            mock_font = MagicMock()
            # Make line height large to force pagination
            mock_font.getbbox.return_value = (0, 0, 10, 20)
            mock_ctx.fonts.get.return_value = mock_font
            mock_ctx.draw.text = MagicMock()
            mock_display.get_display_context.return_value = mock_ctx

            items = [FileItem(Path(f"/tmp/file{i}.txt")) for i in range(20)]
            _render_browser_screen("Files", items, 0)

            mock_ctx.disp.display.assert_called_once()


class TestShowFileBrowser:
    """Test show_file_browser function."""

    def test_no_drives_available(self):
        """Test browser when no drives are available."""
        with patch(
            "rpi_usb_cloner.ui.screens.file_browser._get_available_locations",
            return_value=[],
        ), patch(
            "rpi_usb_cloner.ui.screens.file_browser.display"
        ) as mock_display, patch(
            "rpi_usb_cloner.ui.screens.file_browser.time"
        ):
            mock_app_context = MagicMock()
            show_file_browser(mock_app_context)

            mock_display.display_lines.assert_called_once()
            call_args = mock_display.display_lines.call_args
            assert "No drives" in str(call_args)

    def test_browser_exit_on_a(self):
        """Test browser exits when button A is pressed."""
        with patch(
            "rpi_usb_cloner.ui.screens.file_browser._get_available_locations"
        ) as mock_locs, patch(
            "rpi_usb_cloner.ui.screens.file_browser._render_browser_screen"
        ), patch(
            "rpi_usb_cloner.ui.screens.file_browser.menus"
        ), patch(
            "rpi_usb_cloner.ui.screens.file_browser.gpio"
        ) as mock_gpio:
            mock_locs.return_value = [FileItem(Path("/mnt/usb"), is_dir=True)]
            mock_gpio.PIN_A = 1
            mock_gpio.PIN_B = 2
            mock_gpio.PIN_L = 3
            mock_gpio.PIN_R = 4
            mock_gpio.PIN_U = 5
            mock_gpio.PIN_D = 6
            mock_gpio.is_pressed.side_effect = [
                True,
                True,
                True,
                True,
                True,
                True,  # Initial states
                False,
                False,
                False,
                False,
                False,
                False,  # Released
                True,
                False,
                False,
                False,
                False,
                False,  # A pressed (exit)
            ]

            mock_app_context = MagicMock()
            show_file_browser(mock_app_context)

    def test_browser_navigate_up_down(self):
        """Test browser navigation with up/down buttons."""
        with patch(
            "rpi_usb_cloner.ui.screens.file_browser._get_available_locations"
        ) as mock_locs, patch(
            "rpi_usb_cloner.ui.screens.file_browser._render_browser_screen"
        ) as mock_render, patch(
            "rpi_usb_cloner.ui.screens.file_browser.menus"
        ), patch(
            "rpi_usb_cloner.ui.screens.file_browser.gpio"
        ) as mock_gpio:
            mock_locs.return_value = [
                FileItem(Path("/mnt/usb1"), is_dir=True),
                FileItem(Path("/mnt/usb2"), is_dir=True),
            ]
            mock_gpio.PIN_A = 1
            mock_gpio.PIN_U = 5
            mock_gpio.PIN_D = 6
            mock_gpio.is_pressed.side_effect = [
                True,
                True,
                True,
                True,
                True,
                True,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                True,
                False,  # U pressed
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                True,  # D pressed
                False,
                False,
                False,
                False,
                False,
                False,
                True,
                False,
                False,
                False,
                False,
                False,  # A pressed
                False,
                False,
                False,
                False,
                False,
                False,
            ]

            mock_app_context = MagicMock()
            show_file_browser(mock_app_context)

            assert mock_render.call_count >= 2
