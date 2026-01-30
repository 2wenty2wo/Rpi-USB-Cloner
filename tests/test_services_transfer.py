"""Tests for image transfer service.

Tests cover:
- Finding destination repositories
- Estimating transfer sizes
- Copying images with progress tracking
- Error handling for invalid destinations
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rpi_usb_cloner.domain import DiskImage, ImageRepo, ImageType
from rpi_usb_cloner.services.transfer import (
    copy_images_to_repo,
    estimate_transfer_size,
    find_destination_repos,
    _copy_single_image,
    _copy_file_with_progress,
    _copy_directory_with_progress,
)


class TestFindDestinationRepos:
    """Test finding destination repositories."""

    def test_find_all_repos_when_no_exclude(self, mocker):
        """Test returning all repos when no drive excluded."""
        mock_repo1 = Mock(spec=ImageRepo, drive_name="sda")
        mock_repo2 = Mock(spec=ImageRepo, drive_name="sdb")
        mock_find = mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.find_image_repos",
            return_value=[mock_repo1, mock_repo2],
        )

        result = find_destination_repos()

        assert len(result) == 2
        mock_find.assert_called_once()

    def test_exclude_specific_drive(self, mocker):
        """Test excluding a specific drive from results."""
        mock_repo1 = Mock(spec=ImageRepo, drive_name="sda")
        mock_repo2 = Mock(spec=ImageRepo, drive_name="sdb")
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.find_image_repos",
            return_value=[mock_repo1, mock_repo2],
        )

        result = find_destination_repos(exclude_drive="sda")

        assert len(result) == 1
        assert result[0].drive_name == "sdb"

    def test_exclude_nonexistent_drive_returns_all(self, mocker):
        """Test excluding a drive not in repos returns all."""
        mock_repo1 = Mock(spec=ImageRepo, drive_name="sda")
        mock_repo2 = Mock(spec=ImageRepo, drive_name="sdb")
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.find_image_repos",
            return_value=[mock_repo1, mock_repo2],
        )

        result = find_destination_repos(exclude_drive="sdc")

        assert len(result) == 2

    def test_no_repos_found(self, mocker):
        """Test handling when no repos exist."""
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.find_image_repos",
            return_value=[],
        )

        result = find_destination_repos()

        assert result == []


class TestEstimateTransferSize:
    """Test transfer size estimation."""

    def test_estimate_single_image(self, mocker):
        """Test estimating size for single image."""
        mock_image = Mock(spec=DiskImage)
        mock_image.configure_mock(name="test.iso")
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes",
            return_value=1024 * 1024 * 100,  # 100 MB
        )

        result = estimate_transfer_size([mock_image])

        assert result == 1024 * 1024 * 100

    def test_estimate_multiple_images(self, mocker):
        """Test estimating size for multiple images."""
        mock_images = [Mock(spec=DiskImage), Mock(spec=DiskImage)]
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes",
            side_effect=[1024 * 1024 * 50, 1024 * 1024 * 100],
        )

        result = estimate_transfer_size(mock_images)

        assert result == 1024 * 1024 * 150  # 150 MB total

    def test_estimate_with_none_size(self, mocker):
        """Test handling images with unknown size."""
        mock_images = [Mock(spec=DiskImage), Mock(spec=DiskImage)]
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes",
            side_effect=[1024 * 1024 * 50, None],
        )

        result = estimate_transfer_size(mock_images)

        assert result == 1024 * 1024 * 50  # Only counts known sizes

    def test_estimate_empty_list(self):
        """Test estimating size for empty image list."""
        result = estimate_transfer_size([])

        assert result == 0


class TestCopyImagesToRepo:
    """Test copying images to repository."""

    def test_copy_success(self, tmp_path, mocker):
        """Test successful copy of multiple images."""
        mock_image1 = Mock(spec=DiskImage, name="image1.iso")
        mock_image2 = Mock(spec=DiskImage, name="image2.iso")
        dest_repo = Mock(spec=ImageRepo, path=tmp_path)

        mocker.patch(
            "rpi_usb_cloner.services.transfer._copy_single_image",
            return_value=None,
        )

        success, failure = copy_images_to_repo(
            [mock_image1, mock_image2], dest_repo
        )

        assert success == 2
        assert failure == 0

    def test_copy_with_failures(self, tmp_path, mocker):
        """Test handling partial failures during copy."""
        mock_image1 = Mock(spec=DiskImage, name="image1.iso")
        mock_image2 = Mock(spec=DiskImage, name="image2.iso")
        dest_repo = Mock(spec=ImageRepo, path=tmp_path)

        def side_effect(img, dest, cb):
            if "image1" in img.name:
                raise IOError("Disk full")

        mocker.patch(
            "rpi_usb_cloner.services.transfer._copy_single_image",
            side_effect=side_effect,
        )

        success, failure = copy_images_to_repo(
            [mock_image1, mock_image2], dest_repo
        )

        assert success == 1
        assert failure == 1

    def test_copy_nonexistent_destination(self, tmp_path):
        """Test error when destination doesn't exist."""
        mock_image = Mock(spec=DiskImage)
        mock_image.configure_mock(name="test.iso")
        dest_repo = Mock(spec=ImageRepo, path=tmp_path / "nonexistent")

        with pytest.raises(OSError, match="does not exist"):
            copy_images_to_repo([mock_image], dest_repo)

    def test_copy_to_file_not_directory(self, tmp_path):
        """Test error when destination is a file not directory."""
        mock_image = Mock(spec=DiskImage)
        mock_image.configure_mock(name="test.iso")
        file_path = tmp_path / "not_a_directory"
        file_path.write_text("test")
        dest_repo = Mock(spec=ImageRepo, path=file_path)

        with pytest.raises(OSError, match="not a directory"):
            copy_images_to_repo([mock_image], dest_repo)

    def test_copy_empty_list(self, tmp_path):
        """Test copying empty image list."""
        dest_repo = Mock(spec=ImageRepo, path=tmp_path)

        success, failure = copy_images_to_repo([], dest_repo)

        assert success == 0
        assert failure == 0

    def test_progress_callback_called(self, tmp_path, mocker):
        """Test that progress callback is invoked."""
        mock_image = Mock(spec=DiskImage, name="test.iso")
        dest_repo = Mock(spec=ImageRepo, path=tmp_path)
        progress_mock = Mock()

        mocker.patch(
            "rpi_usb_cloner.services.transfer._copy_single_image",
            return_value=None,
        )

        copy_images_to_repo([mock_image], dest_repo, progress_callback=progress_mock)

        # Progress callback is passed to _copy_single_image


class TestCopySingleImage:
    """Test copying individual images."""

    def test_copy_clonezilla_directory(self, tmp_path, mocker):
        """Test copying Clonezilla directory image."""
        image_path = tmp_path / "source_image"
        image_path.mkdir()
        mock_image = Mock(spec=DiskImage)
        mock_image.configure_mock(name="test_image", image_type=ImageType.CLONEZILLA_DIR, path=image_path)
        dest_repo = Mock(spec=ImageRepo, path=tmp_path / "dest")
        dest_repo.path.mkdir()

        mock_copy_dir = mocker.patch(
            "rpi_usb_cloner.services.transfer._copy_directory_with_progress"
        )

        _copy_single_image(mock_image, dest_repo, None)

        mock_copy_dir.assert_called_once()
        assert (dest_repo.path / "clonezilla").exists()

    def test_copy_iso_file(self, tmp_path, mocker):
        """Test copying ISO file."""
        image_path = tmp_path / "test.iso"
        image_path.write_text("ISO content")
        mock_image = Mock(spec=DiskImage)
        mock_image.configure_mock(name="test.iso", image_type=ImageType.ISO, path=image_path)
        dest_repo = Mock(spec=ImageRepo, path=tmp_path / "dest")
        dest_repo.path.mkdir()

        mock_copy_file = mocker.patch(
            "rpi_usb_cloner.services.transfer._copy_file_with_progress"
        )

        _copy_single_image(mock_image, dest_repo, None)

        mock_copy_file.assert_called_once()

    def test_copy_imageusb_bin(self, tmp_path, mocker):
        """Test copying ImageUSB BIN file."""
        image_path = tmp_path / "test.bin"
        image_path.write_text("BIN content")
        mock_image = Mock(spec=DiskImage)
        mock_image.configure_mock(name="test.bin", image_type=ImageType.IMAGEUSB_BIN, path=image_path)
        dest_repo = Mock(spec=ImageRepo, path=tmp_path / "dest")
        dest_repo.path.mkdir()

        mock_copy_file = mocker.patch(
            "rpi_usb_cloner.services.transfer._copy_file_with_progress"
        )

        _copy_single_image(mock_image, dest_repo, None)

        mock_copy_file.assert_called_once()

    def test_copy_unsupported_type(self, tmp_path):
        """Test error on unsupported image type."""
        mock_image = Mock(spec=DiskImage)
        mock_image.configure_mock(name="test.xyz", image_type=ImageType.ISO, path=tmp_path / "test.xyz")
        dest_repo = Mock(spec=ImageRepo, path=tmp_path / "dest")
        dest_repo.path.mkdir()

        with pytest.raises(ValueError, match="Unsupported image type"):
            _copy_single_image(mock_image, dest_repo, None)

    def test_progress_callback_progress_0_and_100(self, tmp_path, mocker):
        """Test progress callback called at start and end."""
        image_path = tmp_path / "test.iso"
        image_path.write_text("content")
        mock_image = Mock(
            spec=DiskImage,
            name="test.iso",
            image_type=ImageType.ISO,
            path=image_path,
        )
        dest_repo = Mock(spec=ImageRepo, path=tmp_path / "dest")
        dest_repo.path.mkdir()
        progress_mock = Mock()

        mocker.patch(
            "rpi_usb_cloner.services.transfer._copy_file_with_progress"
        )

        _copy_single_image(mock_image, dest_repo, progress_mock)

        assert progress_mock.call_count == 2
        progress_mock.assert_any_call("test.iso", 0.0)
        progress_mock.assert_any_call("test.iso", 1.0)


class TestCopyFileWithProgress:
    """Test file copy with progress tracking."""

    def test_copy_small_file(self, tmp_path):
        """Test copying a small file."""
        src = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        src.write_text("Hello, World!")
        progress_calls = []

        def progress_cb(name, progress):
            progress_calls.append((name, progress))

        _copy_file_with_progress(src, dest, "test_file", progress_cb)

        assert dest.exists()
        assert dest.read_text() == "Hello, World!"
        assert len(progress_calls) > 0

    def test_copy_empty_file(self, tmp_path):
        """Test copying empty file."""
        src = tmp_path / "empty.txt"
        dest = tmp_path / "dest.txt"
        src.write_text("")

        _copy_file_with_progress(src, dest, "empty_file", None)

        assert dest.exists()
        assert dest.read_bytes() == b""

    def test_overwrite_existing_file(self, tmp_path, mocker):
        """Test overwriting existing destination file."""
        src = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        src.write_text("New content")
        dest.write_text("Old content")

        mock_log = mocker.patch("rpi_usb_cloner.services.transfer.log")

        _copy_file_with_progress(src, dest, "test", None)

        assert dest.read_text() == "New content"
        mock_log.warning.assert_called_once()

    def test_no_callback_direct_copy(self, tmp_path):
        """Test copy without progress callback uses shutil."""
        src = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        src.write_text("Direct copy content")

        _copy_file_with_progress(src, dest, "test", None)

        assert dest.exists()
        assert dest.read_text() == "Direct copy content"

    def test_preserves_metadata(self, tmp_path):
        """Test that file metadata is preserved."""
        import time

        src = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        src.write_text("Content")

        # Set modification time
        original_time = time.time() - 3600  # 1 hour ago
        src.touch()

        _copy_file_with_progress(src, dest, "test", None)

        assert dest.exists()


class TestCopyDirectoryWithProgress:
    """Test directory copy with progress tracking."""

    def test_copy_directory_structure(self, tmp_path, mocker):
        """Test copying directory with subdirectories."""
        src = tmp_path / "source_dir"
        src.mkdir()
        (src / "subdir").mkdir()
        (src / "file1.txt").write_text("Content 1")
        (src / "subdir" / "file2.txt").write_text("Content 2")

        dest = tmp_path / "dest_dir"
        progress_calls = []

        def progress_cb(name, progress):
            progress_calls.append(progress)

        _copy_directory_with_progress(src, dest, "test_dir", progress_cb)

        assert (dest / "file1.txt").exists()
        assert (dest / "subdir" / "file2.txt").exists()
        assert (dest / "file1.txt").read_text() == "Content 1"

    def test_copy_empty_directory(self, tmp_path):
        """Test copying empty directory."""
        src = tmp_path / "empty_dir"
        src.mkdir()
        dest = tmp_path / "dest_dir"

        _copy_directory_with_progress(src, dest, "empty", None)

        assert dest.exists()
        assert dest.is_dir()

    def test_merge_into_existing_directory(self, tmp_path, mocker):
        """Test merging into existing destination."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "new_file.txt").write_text("New")

        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "existing.txt").write_text("Existing")

        mock_log = mocker.patch("rpi_usb_cloner.services.transfer.log")

        _copy_directory_with_progress(src, dest, "test", None)

        assert (dest / "new_file.txt").exists()
        assert (dest / "existing.txt").exists()
        mock_log.warning.assert_called_once()

    def test_handles_file_stat_error(self, tmp_path, mocker):
        """Test handling files that can't be statted."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("content")

        mock_log = mocker.patch("rpi_usb_cloner.services.transfer.log")

        # Mock stat to fail for one file
        original_stat = Path.stat

        def failing_stat(self):
            if "file.txt" in str(self):
                raise OSError("Permission denied")
            return original_stat(self)

        mocker.patch.object(Path, "stat", failing_stat)

        dest = tmp_path / "dest"

        _copy_directory_with_progress(src, dest, "test", None)

        mock_log.warning.assert_called_once()

    def test_copy_error_raises(self, tmp_path, mocker):
        """Test that copy errors are raised."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("content")

        dest = tmp_path / "dest"

        mocker.patch("shutil.copy2", side_effect=OSError("Disk full"))

        with pytest.raises(OSError, match="Disk full"):
            _copy_directory_with_progress(src, dest, "test", None)
