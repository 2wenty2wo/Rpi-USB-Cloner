"""
Additional tests for storage/image_repo.py module to improve coverage.

Covers:
- _is_temp_clonezilla_path function
- get_image_size_bytes function edge cases
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rpi_usb_cloner.storage.image_repo import (
    _is_temp_clonezilla_path,
    get_image_size_bytes,
)


class TestIsTempClonezillaPath:
    """Test _is_temp_clonezilla_path function."""

    def test_hidden_file(self):
        """Test hidden files are identified as temp."""
        assert _is_temp_clonezilla_path(Path(".hidden")) is True
        assert _is_temp_clonezilla_path(Path("/path/.hidden")) is True

    def test_temp_extensions(self):
        """Test files with temp extensions."""
        assert _is_temp_clonezilla_path(Path("file.tmp")) is True
        assert _is_temp_clonezilla_path(Path("file.part")) is True
        assert _is_temp_clonezilla_path(Path("file.partial")) is True
        assert _is_temp_clonezilla_path(Path("file.swp")) is True
        assert _is_temp_clonezilla_path(Path("file.swx")) is True

    def test_temp_directories(self):
        """Test paths with temp directory names."""
        assert _is_temp_clonezilla_path(Path("/tmp/file")) is True
        assert _is_temp_clonezilla_path(Path("/temp/file")) is True
        assert _is_temp_clonezilla_path(Path("/path/tmp/file")) is True

    def test_normal_paths(self):
        """Test normal paths are not temp."""
        assert _is_temp_clonezilla_path(Path("normal.file")) is False
        assert _is_temp_clonezilla_path(Path("/path/to/file.txt")) is False
        assert _is_temp_clonezilla_path(Path("image.iso")) is False


class TestGetImageSizeBytes:
    """Test get_image_size_bytes function."""

    def test_existing_size(self):
        """Test when size_bytes is already set."""
        from rpi_usb_cloner.domain import DiskImage, ImageType
        
        image = DiskImage(
            name="test.iso",
            path=Path("/tmp/test.iso"),
            image_type=ImageType.ISO,
            size_bytes=1024,
        )
        
        result = get_image_size_bytes(image)
        assert result == 1024

    def test_non_clonezilla_no_size(self):
        """Test when not Clonezilla and no size_bytes."""
        from rpi_usb_cloner.domain import DiskImage, ImageType
        
        image = DiskImage(
            name="test.iso",
            path=Path("/tmp/test.iso"),
            image_type=ImageType.ISO,
            size_bytes=None,
        )
        
        result = get_image_size_bytes(image)
        assert result is None

    def test_clonezilla_with_size(self):
        """Test Clonezilla image with pre-set size."""
        from rpi_usb_cloner.domain import DiskImage, ImageType
        
        image = DiskImage(
            name="backup",
            path=Path("/tmp/backup"),
            image_type=ImageType.CLONEZILLA_DIR,
            size_bytes=5000000000,
        )
        
        result = get_image_size_bytes(image)
        # Should return the pre-set size, not calculate
        assert result == 5000000000
