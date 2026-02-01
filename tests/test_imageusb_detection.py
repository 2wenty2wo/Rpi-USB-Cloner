"""Tests for ImageUSB .BIN file detection and validation.

Covers:
- is_imageusb_file function
- validate_imageusb_file function
- get_imageusb_metadata function
- IMAGEUSB_SIGNATURE constant
- IMAGEUSB_HEADER_SIZE constant
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rpi_usb_cloner.storage.imageusb.detection import (
    IMAGEUSB_HEADER_SIZE,
    IMAGEUSB_SIGNATURE,
    get_imageusb_metadata,
    is_imageusb_file,
    validate_imageusb_file,
)


class TestConstants:
    """Test module constants."""

    def test_imageusb_signature(self):
        """Test that signature is correct UTF-16LE 'imageUSB'."""
        expected = "imageUSB".encode("utf-16le")
        assert IMAGEUSB_SIGNATURE == expected
        assert len(IMAGEUSB_SIGNATURE) == 16

    def test_imageusb_header_size(self):
        """Test that header size is 512 bytes."""
        assert IMAGEUSB_HEADER_SIZE == 512


class TestIsImageUSBFile:
    """Test is_imageusb_file function."""

    def test_nonexistent_file(self, tmp_path):
        """Test with non-existent file."""
        result = is_imageusb_file(tmp_path / "nonexistent.bin")
        assert result is False

    def test_directory_not_file(self, tmp_path):
        """Test with directory instead of file."""
        dir_path = tmp_path / "not_a_file"
        dir_path.mkdir()
        result = is_imageusb_file(dir_path)
        assert result is False

    def test_valid_imageusb_file(self, tmp_path):
        """Test with valid ImageUSB signature."""
        bin_file = tmp_path / "valid.bin"
        # Write signature + padding
        bin_file.write_bytes(IMAGEUSB_SIGNATURE + b"\x00" * 100)
        
        result = is_imageusb_file(bin_file)
        assert result is True

    def test_invalid_signature(self, tmp_path):
        """Test with invalid signature."""
        bin_file = tmp_path / "invalid.bin"
        bin_file.write_bytes(b"NOT_IMAGEUSB!!" + b"\x00" * 100)
        
        result = is_imageusb_file(bin_file)
        assert result is False

    def test_empty_file(self, tmp_path):
        """Test with empty file."""
        bin_file = tmp_path / "empty.bin"
        bin_file.write_bytes(b"")
        
        result = is_imageusb_file(bin_file)
        assert result is False

    def test_short_file(self, tmp_path):
        """Test with file shorter than signature."""
        bin_file = tmp_path / "short.bin"
        bin_file.write_bytes(b"short")
        
        result = is_imageusb_file(bin_file)
        assert result is False

    def test_oserror_on_read(self, tmp_path):
        """Test handling of OSError during file read."""
        with pytest.MonkeyPatch().context() as m:
            import rpi_usb_cloner.storage.imageusb.detection as detection_module
            
            def raise_oserror(*args, **kwargs):
                raise OSError("Permission denied")
            
            m.setattr(Path, "open", raise_oserror)
            result = is_imageusb_file(Path("/fake/path.bin"))
            assert result is False


class TestValidateImageUSBFile:
    """Test validate_imageusb_file function."""

    def test_nonexistent_file(self, tmp_path):
        """Test validation of non-existent file."""
        result = validate_imageusb_file(tmp_path / "nonexistent.bin")
        assert result is not None
        assert "does not exist" in result

    def test_directory_not_file(self, tmp_path):
        """Test validation of directory."""
        dir_path = tmp_path / "not_a_file"
        dir_path.mkdir()
        result = validate_imageusb_file(dir_path)
        assert result is not None
        assert "not a file" in result

    def test_file_too_small(self, tmp_path):
        """Test validation of file smaller than header."""
        small_file = tmp_path / "small.bin"
        small_file.write_bytes(IMAGEUSB_SIGNATURE + b"\x00" * 100)
        
        result = validate_imageusb_file(small_file)
        assert result is not None
        assert "too small" in result

    def test_invalid_signature(self, tmp_path):
        """Test validation of file with wrong signature."""
        invalid_file = tmp_path / "invalid.bin"
        invalid_file.write_bytes(b"WRONG_SIGNATURE!" + b"\x00" * 500)
        
        result = validate_imageusb_file(invalid_file)
        assert result is not None
        assert "Invalid ImageUSB signature" in result

    def test_valid_file(self, tmp_path):
        """Test validation of valid ImageUSB file."""
        valid_file = tmp_path / "valid.bin"
        # Signature + padding to > 512 bytes
        content = IMAGEUSB_SIGNATURE + b"\x00" * 510  # Total 526 bytes
        # Add MBR signature at bytes 510-511 (from offset 512)
        mbr_sector = b"\x00" * 510 + b"\x55\xaa"
        valid_file.write_bytes(content + mbr_sector)
        
        result = validate_imageusb_file(valid_file)
        assert result is None

    def test_cannot_read_file_size(self, tmp_path):
        """Test handling of OSError when reading file size."""
        import os
        
        # Create a file then remove read permissions
        test_file = tmp_path / "noread.bin"
        test_file.write_bytes(IMAGEUSB_SIGNATURE + b"\x00" * 600)
        
        # On Windows, we can't easily test permission errors
        # On Unix, we can chmod
        try:
            os.chmod(test_file, 0o000)
            result = validate_imageusb_file(test_file)
            assert result is not None
            assert "Cannot read file size" in result
        finally:
            os.chmod(test_file, 0o644)

    def test_truncated_file(self, tmp_path):
        """Test validation of truncated file (can't read full MBR)."""
        truncated_file = tmp_path / "truncated.bin"
        # Signature + just enough to pass size check but not full MBR
        content = IMAGEUSB_SIGNATURE + b"\x00" * 400  # Only 416 bytes after header
        truncated_file.write_bytes(content)
        
        result = validate_imageusb_file(truncated_file)
        # Should pass validation even if MBR check fails (it's just a warning)
        assert result is None

    def test_error_reading_file(self, tmp_path):
        """Test handling of error during file reading."""
        with pytest.MonkeyPatch().context() as m:
            def raise_oserror(*args, **kwargs):
                raise OSError("Read error")
            
            m.setattr(Path, "open", raise_oserror)
            result = validate_imageusb_file(Path("/fake/path.bin"))
            assert result is not None
            assert "Error reading file" in result


class TestGetImageUSBMetadata:
    """Test get_imageusb_metadata function."""

    def test_metadata_valid_file(self, tmp_path):
        """Test metadata extraction from valid file."""
        bin_file = tmp_path / "test.bin"
        content = IMAGEUSB_SIGNATURE + b"\x00" * 1000
        bin_file.write_bytes(content)
        
        metadata = get_imageusb_metadata(bin_file)
        
        assert metadata["name"] == "test.bin"
        assert metadata["size_bytes"] == 1016
        assert metadata["data_size_bytes"] == 504  # 1016 - 512
        assert metadata["valid"] is True
        assert metadata["error"] is None

    def test_metadata_invalid_file(self, tmp_path):
        """Test metadata extraction from invalid file."""
        bin_file = tmp_path / "invalid.bin"
        bin_file.write_bytes(b"NOT_VALID" + b"\x00" * 600)
        
        metadata = get_imageusb_metadata(bin_file)
        
        assert metadata["name"] == "invalid.bin"
        assert metadata["size_bytes"] == 609
        assert metadata["valid"] is False
        assert metadata["error"] is not None

    def test_metadata_oserror(self, tmp_path):
        """Test metadata extraction with OSError."""
        with pytest.MonkeyPatch().context() as m:
            def raise_oserror(*args, **kwargs):
                raise OSError("Cannot access")
            
            m.setattr(Path, "stat", raise_oserror)
            metadata = get_imageusb_metadata(Path("/fake/test.bin"))
            
            assert metadata["name"] == "test.bin"
            assert metadata["size_bytes"] == 0
            assert metadata["data_size_bytes"] == 0
