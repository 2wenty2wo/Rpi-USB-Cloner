"""Tests for USB-to-USB transfer service (services/transfer.py)."""

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

    def test_find_all_repos_no_exclude(self):
        """Test finding all repos without exclusion."""
        mock_repos = [
            ImageRepo(path=Path("/mnt/sda1"), drive_name="sda1"),
            ImageRepo(path=Path("/mnt/sdb1"), drive_name="sdb1"),
        ]
        
        with patch("rpi_usb_cloner.services.transfer.image_repo.find_image_repos", return_value=mock_repos):
            result = find_destination_repos()
        
        assert len(result) == 2
        assert result[0].drive_name == "sda1"
        assert result[1].drive_name == "sdb1"

    def test_find_repos_with_exclude(self):
        """Test finding repos excluding specific drive."""
        mock_repos = [
            ImageRepo(path=Path("/mnt/sda1"), drive_name="sda1"),
            ImageRepo(path=Path("/mnt/sdb1"), drive_name="sdb1"),
            ImageRepo(path=Path("/mnt/sdc1"), drive_name="sdc1"),
        ]
        
        with patch("rpi_usb_cloner.services.transfer.image_repo.find_image_repos", return_value=mock_repos):
            result = find_destination_repos(exclude_drive="sda1")
        
        assert len(result) == 2
        assert all(repo.drive_name != "sda1" for repo in result)

    def test_find_repos_empty_list(self):
        """Test finding repos when none available."""
        with patch("rpi_usb_cloner.services.transfer.image_repo.find_image_repos", return_value=[]):
            result = find_destination_repos()
        
        assert result == []


class TestEstimateTransferSize:
    """Test transfer size estimation."""

    def test_estimate_with_known_sizes(self):
        """Test estimating size when all images have known sizes."""
        images = [
            DiskImage(name="img1.iso", path=Path("/tmp/img1.iso"), image_type=ImageType.ISO),
            DiskImage(name="img2.iso", path=Path("/tmp/img2.iso"), image_type=ImageType.ISO),
        ]
        
        with patch("rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes") as mock_get_size:
            mock_get_size.side_effect = [1000, 2000]
            result = estimate_transfer_size(images)
        
        assert result == 3000

    def test_estimate_with_unknown_sizes(self):
        """Test estimating size when some sizes are unknown."""
        images = [
            DiskImage(name="img1.iso", path=Path("/tmp/img1.iso"), image_type=ImageType.ISO),
            DiskImage(name="img2.iso", path=Path("/tmp/img2.iso"), image_type=ImageType.ISO),
        ]
        
        with patch("rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes") as mock_get_size:
            mock_get_size.side_effect = [1000, None]
            result = estimate_transfer_size(images)
        
        assert result == 1000

    def test_estimate_empty_list(self):
        """Test estimating size for empty image list."""
        result = estimate_transfer_size([])
        assert result == 0


class TestCopyImagesToRepo:
    """Test copying images to repository."""

    def test_copy_images_success(self, tmp_path):
        """Test successful copy of multiple images."""
        destination = ImageRepo(path=tmp_path, drive_name="sda1")
        images = [
            DiskImage(name="img1.iso", path=Path("/tmp/img1.iso"), image_type=ImageType.ISO),
        ]
        
        with patch("rpi_usb_cloner.services.transfer._copy_single_image") as mock_copy:
            success, failure = copy_images_to_repo(images, destination)
        
        assert success == 1
        assert failure == 0
        mock_copy.assert_called_once()

    def test_copy_images_with_failures(self, tmp_path):
        """Test copy with some failures."""
        destination = ImageRepo(path=tmp_path, drive_name="sda1")
        images = [
            DiskImage(name="img1.iso", path=Path("/tmp/img1.iso"), image_type=ImageType.ISO),
            DiskImage(name="img2.iso", path=Path("/tmp/img2.iso"), image_type=ImageType.ISO),
        ]
        
        with patch("rpi_usb_cloner.services.transfer._copy_single_image") as mock_copy:
            mock_copy.side_effect = [None, Exception("Copy failed")]
            success, failure = copy_images_to_repo(images, destination)
        
        assert success == 1
        assert failure == 1

    def test_copy_destination_not_exist(self):
        """Test copy to non-existent destination."""
        destination = ImageRepo(path=Path("/nonexistent"), drive_name="sda1")
        images = [DiskImage(name="img.iso", path=Path("/tmp/img.iso"), image_type=ImageType.ISO)]
        
        with pytest.raises(OSError, match="Destination path does not exist"):
            copy_images_to_repo(images, destination)

    def test_copy_destination_not_directory(self, tmp_path):
        """Test copy to non-directory path."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")
        destination = ImageRepo(path=file_path, drive_name="sda1")
        images = [DiskImage(name="img.iso", path=Path("/tmp/img.iso"), image_type=ImageType.ISO)]
        
        with pytest.raises(OSError, match="Destination path is not a directory"):
            copy_images_to_repo(images, destination)


class TestCopySingleImage:
    """Test copying single image."""

    def test_copy_clonezilla_directory(self, tmp_path):
        """Test copying Clonezilla directory image."""
        destination = ImageRepo(path=tmp_path, drive_name="sda1")
        image = DiskImage(
            name="backup",
            path=Path("/tmp/backup"),
            image_type=ImageType.CLONEZILLA_DIR,
        )
        
        progress_calls = []
        
        def progress_cb(name, progress):
            progress_calls.append((name, progress))
        
        with patch("rpi_usb_cloner.services.transfer._copy_directory_with_progress") as mock_copy:
            _copy_single_image(image, destination, progress_cb)
        
        mock_copy.assert_called_once()
        assert progress_calls[0] == ("backup", 0.0)
        assert progress_calls[-1] == ("backup", 1.0)

    def test_copy_iso_file(self, tmp_path):
        """Test copying ISO image."""
        destination = ImageRepo(path=tmp_path, drive_name="sda1")
        image = DiskImage(
            name="image.iso",
            path=Path("/tmp/image.iso"),
            image_type=ImageType.ISO,
        )
        
        with patch("rpi_usb_cloner.services.transfer._copy_file_with_progress") as mock_copy:
            _copy_single_image(image, destination)
        
        mock_copy.assert_called_once()

    def test_copy_bin_file(self, tmp_path):
        """Test copying ImageUSB BIN file."""
        destination = ImageRepo(path=tmp_path, drive_name="sda1")
        image = DiskImage(
            name="image.bin",
            path=Path("/tmp/image.bin"),
            image_type=ImageType.IMAGEUSB_BIN,
        )
        
        with patch("rpi_usb_cloner.services.transfer._copy_file_with_progress") as mock_copy:
            _copy_single_image(image, destination)
        
        mock_copy.assert_called_once()

    def test_copy_unsupported_type(self, tmp_path):
        """Test copying unsupported image type."""
        destination = ImageRepo(path=tmp_path, drive_name="sda1")
        
        # Create a mock image type
        mock_image = Mock()
        mock_image.name = "test"
        mock_image.image_type = "UNKNOWN"
        
        with pytest.raises(ValueError, match="Unsupported image type"):
            _copy_single_image(mock_image, destination)


class TestCopyFileWithProgress:
    """Test file copying with progress tracking."""

    def test_copy_file_with_progress(self, tmp_path):
        """Test copying file with progress callback."""
        src = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        src.write_text("A" * 1000)
        
        progress_calls = []
        
        def progress_cb(name, progress):
            progress_calls.append(progress)
        
        _copy_file_with_progress(src, dest, "test.txt", progress_cb)
        
        assert dest.exists()
        assert dest.read_text() == src.read_text()
        assert len(progress_calls) > 0
        assert progress_calls[-1] == 1.0

    def test_copy_file_without_progress(self, tmp_path):
        """Test copying file without progress callback."""
        src = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        src.write_text("test content")
        
        _copy_file_with_progress(src, dest, "test.txt", None)
        
        assert dest.exists()
        assert dest.read_text() == "test content"

    def test_copy_overwrite_existing(self, tmp_path):
        """Test that existing files are overwritten."""
        src = tmp_path / "source.txt"
        dest = tmp_path / "dest.txt"
        src.write_text("new content")
        dest.write_text("old content")
        
        with patch("rpi_usb_cloner.services.transfer.log"):
            _copy_file_with_progress(src, dest, "test.txt", None)
        
        assert dest.read_text() == "new content"

    def test_copy_empty_file(self, tmp_path):
        """Test copying empty file."""
        src = tmp_path / "empty.txt"
        dest = tmp_path / "dest.txt"
        src.write_text("")
        
        _copy_file_with_progress(src, dest, "test.txt", None)
        
        assert dest.exists()
        assert dest.read_bytes() == b""


class TestCopyDirectoryWithProgress:
    """Test directory copying with progress tracking."""

    def test_copy_directory_with_files(self, tmp_path):
        """Test copying directory with multiple files."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "file1.txt").write_text("content1")
        (src / "file2.txt").write_text("content2")
        
        dest = tmp_path / "dest"
        
        progress_calls = []
        
        def progress_cb(name, progress):
            progress_calls.append(progress)
        
        _copy_directory_with_progress(src, dest, "backup", progress_cb)
        
        assert (dest / "file1.txt").exists()
        assert (dest / "file2.txt").exists()
        assert (dest / "file1.txt").read_text() == "content1"

    def test_copy_empty_directory(self, tmp_path):
        """Test copying empty directory."""
        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"
        
        _copy_directory_with_progress(src, dest, "backup", None)
        
        assert dest.exists()

    def test_copy_directory_with_subdirs(self, tmp_path):
        """Test copying directory with subdirectories."""
        src = tmp_path / "source"
        src.mkdir()
        subdir = src / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("nested content")
        
        dest = tmp_path / "dest"
        
        _copy_directory_with_progress(src, dest, "backup", None)
        
        assert (dest / "subdir" / "file.txt").exists()
        assert (dest / "subdir" / "file.txt").read_text() == "nested content"
