"""Tests for services/transfer.py module.

This module tests image transfer functionality for USB-to-USB transfers.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from rpi_usb_cloner.domain import DiskImage, ImageRepo, ImageType
from rpi_usb_cloner.services import transfer


class TestFindDestinationRepos:
    """Tests for find_destination_repos function."""

    def test_find_destination_repos_no_exclude(self, mocker):
        """Test finding all repos when no exclusion."""
        mock_repos = [
            ImageRepo(path=Path("/media/repo1"), drive_name="sda"),
            ImageRepo(path=Path("/media/repo2"), drive_name="sdb"),
        ]
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.find_image_repos",
            return_value=mock_repos,
        )

        result = transfer.find_destination_repos()
        assert result == mock_repos

    def test_find_destination_repos_exclude_one(self, mocker):
        """Test finding repos excluding specific drive."""
        mock_repos = [
            ImageRepo(path=Path("/media/repo1"), drive_name="sda"),
            ImageRepo(path=Path("/media/repo2"), drive_name="sdb"),
            ImageRepo(path=Path("/media/repo3"), drive_name="sdc"),
        ]
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.find_image_repos",
            return_value=mock_repos,
        )

        result = transfer.find_destination_repos(exclude_drive="sdb")
        assert len(result) == 2
        assert all(r.drive_name != "sdb" for r in result)
        drive_names = {r.drive_name for r in result}
        assert drive_names == {"sda", "sdc"}

    def test_find_destination_repos_exclude_not_found(self, mocker):
        """Test excluding drive that doesn't exist returns all."""
        mock_repos = [
            ImageRepo(path=Path("/media/repo1"), drive_name="sda"),
            ImageRepo(path=Path("/media/repo2"), drive_name="sdb"),
        ]
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.find_image_repos",
            return_value=mock_repos,
        )

        result = transfer.find_destination_repos(exclude_drive="sdz")
        assert result == mock_repos


class TestEstimateTransferSize:
    """Tests for estimate_transfer_size function."""

    def test_estimate_transfer_size_single_image(self, mocker):
        """Test estimating size for single image."""
        images = [
            DiskImage(
                name="test.iso",
                path=Path("/test.iso"),
                image_type=ImageType.ISO,
                size_bytes=1000000,
            )
        ]
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes",
            return_value=1000000,
        )

        result = transfer.estimate_transfer_size(images)
        assert result == 1000000

    def test_estimate_transfer_size_multiple_images(self, mocker):
        """Test estimating size for multiple images."""
        images = [
            DiskImage(
                name="image1",
                path=Path("/image1"),
                image_type=ImageType.CLONEZILLA_DIR,
                size_bytes=None,
            ),
            DiskImage(
                name="test.iso",
                path=Path("/test.iso"),
                image_type=ImageType.ISO,
                size_bytes=2000000,
            ),
        ]
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes",
            side_effect=[500000, 2000000],
        )

        result = transfer.estimate_transfer_size(images)
        assert result == 2500000

    def test_estimate_transfer_size_no_size(self, mocker):
        """Test estimating size when size cannot be determined."""
        images = [
            DiskImage(
                name="unknown",
                path=Path("/unknown"),
                image_type=ImageType.ISO,
                size_bytes=None,
            )
        ]
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes",
            return_value=None,
        )

        result = transfer.estimate_transfer_size(images)
        assert result == 0


class TestCopyImagesToRepo:
    """Tests for copy_images_to_repo function."""

    def test_copy_images_destination_not_exists(self):
        """Test error when destination path doesn't exist."""
        dest = ImageRepo(path=Path("/nonexistent"), drive_name="sda")
        images = []

        with pytest.raises(OSError, match="does not exist"):
            transfer.copy_images_to_repo(images, dest)

    def test_copy_images_destination_not_dir(self, tmp_path):
        """Test error when destination is not a directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")
        dest = ImageRepo(path=file_path, drive_name="sda")
        images = []

        with pytest.raises(OSError, match="not a directory"):
            transfer.copy_images_to_repo(images, dest)

    def test_copy_images_single_iso_success(self, tmp_path, mocker):
        """Test copying single ISO file successfully."""
        # Create source ISO
        src_iso = tmp_path / "source" / "test.iso"
        src_iso.parent.mkdir()
        src_iso.write_bytes(b"x" * 1000)

        # Create destination repo
        dest_path = tmp_path / "dest"
        dest_path.mkdir()
        dest = ImageRepo(path=dest_path, drive_name="sdb")

        # Mock get_image_size_bytes
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes",
            return_value=1000,
        )

        images = [
            DiskImage(
                name="test.iso",
                path=src_iso,
                image_type=ImageType.ISO,
                size_bytes=1000,
            )
        ]

        success, failure = transfer.copy_images_to_repo(images, dest)

        assert success == 1
        assert failure == 0
        assert (dest_path / "test.iso").exists()
        assert (dest_path / "test.iso").read_bytes() == b"x" * 1000

    def test_copy_images_multiple_success(self, tmp_path, mocker):
        """Test copying multiple images successfully."""
        # Create source files
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        iso1 = src_dir / "image1.iso"
        iso2 = src_dir / "image2.iso"
        iso1.write_bytes(b"a" * 500)
        iso2.write_bytes(b"b" * 700)

        # Create destination repo
        dest_path = tmp_path / "dest"
        dest_path.mkdir()
        dest = ImageRepo(path=dest_path, drive_name="sdb")

        # Mock get_image_size_bytes
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes",
            side_effect=[500, 700],
        )

        images = [
            DiskImage(
                name="image1.iso",
                path=iso1,
                image_type=ImageType.ISO,
                size_bytes=500,
            ),
            DiskImage(
                name="image2.iso",
                path=iso2,
                image_type=ImageType.ISO,
                size_bytes=700,
            ),
        ]

        success, failure = transfer.copy_images_to_repo(images, dest)

        assert success == 2
        assert failure == 0
        assert (dest_path / "image1.iso").exists()
        assert (dest_path / "image2.iso").exists()

    def test_copy_images_with_progress_callback(self, tmp_path, mocker):
        """Test progress callback is called during copy."""
        # Create source ISO
        src_iso = tmp_path / "source" / "test.iso"
        src_iso.parent.mkdir()
        src_iso.write_bytes(b"x" * 1000)

        # Create destination repo
        dest_path = tmp_path / "dest"
        dest_path.mkdir()
        dest = ImageRepo(path=dest_path, drive_name="sdb")

        # Mock get_image_size_bytes
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes",
            return_value=1000,
        )

        images = [
            DiskImage(
                name="test.iso",
                path=src_iso,
                image_type=ImageType.ISO,
                size_bytes=1000,
            )
        ]

        progress_callback = Mock()
        success, failure = transfer.copy_images_to_repo(
            images, dest, progress_callback=progress_callback
        )

        assert success == 1
        assert failure == 0

        # Verify callback was called at least twice (start and end)
        assert progress_callback.call_count >= 2

        # Check first and last calls
        first_call = progress_callback.call_args_list[0]
        last_call = progress_callback.call_args_list[-1]

        assert first_call[0][0] == "test.iso"  # image name
        assert first_call[0][1] == 0.0  # start progress

        assert last_call[0][0] == "test.iso"
        assert last_call[0][1] == 1.0  # end progress

    def test_copy_images_clonezilla_dir(self, tmp_path, mocker):
        """Test copying Clonezilla directory image."""
        # Create source Clonezilla dir
        src_dir = tmp_path / "source" / "my-image"
        src_dir.mkdir(parents=True)
        (src_dir / "file1.gz").write_bytes(b"x" * 500)
        (src_dir / "file2.gz").write_bytes(b"y" * 300)

        # Create destination repo
        dest_path = tmp_path / "dest"
        dest_path.mkdir()
        dest = ImageRepo(path=dest_path, drive_name="sdb")

        # Mock is_temp_clonezilla_path
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo._is_temp_clonezilla_path",
            return_value=False,
        )

        images = [
            DiskImage(
                name="my-image",
                path=src_dir,
                image_type=ImageType.CLONEZILLA_DIR,
                size_bytes=None,
            )
        ]

        success, failure = transfer.copy_images_to_repo(images, dest)

        assert success == 1
        assert failure == 0

        # Should be copied to clonezilla/ subdirectory
        dest_image = dest_path / "clonezilla" / "my-image"
        assert dest_image.exists()
        assert (dest_image / "file1.gz").exists()
        assert (dest_image / "file2.gz").exists()

    def test_copy_images_partial_failure(self, tmp_path, mocker):
        """Test partial failure when some images fail to copy."""
        # Create one valid source
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        valid_iso = src_dir / "valid.iso"
        valid_iso.write_bytes(b"x" * 500)

        # Create destination repo
        dest_path = tmp_path / "dest"
        dest_path.mkdir()
        dest = ImageRepo(path=dest_path, drive_name="sdb")

        # Mock get_image_size_bytes
        mocker.patch(
            "rpi_usb_cloner.services.transfer.image_repo.get_image_size_bytes",
            return_value=500,
        )

        images = [
            DiskImage(
                name="valid.iso",
                path=valid_iso,
                image_type=ImageType.ISO,
                size_bytes=500,
            ),
            DiskImage(
                name="missing.iso",
                path=Path("/nonexistent/missing.iso"),
                image_type=ImageType.ISO,
                size_bytes=500,
            ),
        ]

        success, failure = transfer.copy_images_to_repo(images, dest)

        assert success == 1
        assert failure == 1
        assert (dest_path / "valid.iso").exists()
        assert not (dest_path / "missing.iso").exists()
