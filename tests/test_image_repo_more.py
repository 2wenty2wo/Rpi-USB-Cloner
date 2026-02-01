"""Additional tests for storage/image_repo.py to improve coverage.

Covers:
- _iter_partitions function
- _resolve_mountpoint function
- find_image_repos function
- list_clonezilla_images function
- _iter_clonezilla_image_dirs function
- _sum_tree_bytes function
- get_repo_usage function
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rpi_usb_cloner.domain import DiskImage, ImageRepo, ImageType
from rpi_usb_cloner.storage import image_repo


# Skip symlink tests on Windows (requires admin privileges)
skip_windows_symlink = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Symlinks require admin privileges on Windows",
)


class TestIterPartitions:
    """Test _iter_partitions function."""

    def test_iterates_partitions(self):
        """Test iterating over device partitions."""
        device = {
            "name": "sda",
            "children": [
                {"name": "sda1", "type": "part"},
                {"name": "sda2", "type": "part"},
            ],
        }
        partitions = list(image_repo._iter_partitions(device))
        assert len(partitions) == 2
        assert partitions[0]["name"] == "sda2"  # Stack is LIFO
        assert partitions[1]["name"] == "sda1"

    def test_skips_non_partitions(self):
        """Test skipping non-partition children."""
        device = {
            "name": "sda",
            "children": [
                {"name": "sda1", "type": "part"},
                {"name": "sda2", "type": "disk"},  # Not a partition
            ],
        }
        partitions = list(image_repo._iter_partitions(device))
        assert len(partitions) == 1
        assert partitions[0]["name"] == "sda1"

    def test_nested_children(self):
        """Test handling nested children."""
        device = {
            "name": "sda",
            "children": [
                {
                    "name": "sda1",
                    "type": "part",
                    "children": [
                        {"name": "sda1p1", "type": "part"},
                    ],
                },
            ],
        }
        partitions = list(image_repo._iter_partitions(device))
        assert len(partitions) == 2


class TestResolveMountpoint:
    """Test _resolve_mountpoint function."""

    def test_existing_mountpoint(self):
        """Test partition with existing mountpoint."""
        partition = {"name": "sda1", "mountpoint": "/mnt/usb"}
        result = image_repo._resolve_mountpoint(partition)
        assert result == Path("/mnt/usb")

    def test_no_name_returns_none(self):
        """Test partition with no name returns None."""
        partition = {"mountpoint": None}
        result = image_repo._resolve_mountpoint(partition)
        assert result is None

    def test_mount_failure_returns_none(self, mocker):
        """Test that mount failure returns None."""
        partition = {"name": "sda1", "mountpoint": None}
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.mount.mount_partition",
            side_effect=RuntimeError("Mount failed"),
        )
        result = image_repo._resolve_mountpoint(partition)
        assert result is None


class TestFindImageRepos:
    """Test find_image_repos function."""

    def test_finds_repos_with_flag_file(self, mocker, tmp_path):
        """Test finding repos with flag file."""
        # Create a mock flag file
        flag_path = tmp_path / ".rpi-usb-cloner-image-repo"
        flag_path.touch()

        device = {
            "name": "sda",
            "children": [{"name": "sda1", "type": "part", "mountpoint": str(tmp_path)}],
        }

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[device],
        )

        repos = image_repo.find_image_repos()
        assert len(repos) == 1
        assert repos[0].path == tmp_path
        assert repos[0].drive_name == "sda"

    def test_skips_without_flag_file(self, mocker, tmp_path):
        """Test skipping partitions without flag file."""
        device = {
            "name": "sda",
            "children": [{"name": "sda1", "type": "part", "mountpoint": str(tmp_path)}],
        }

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[device],
        )

        repos = image_repo.find_image_repos()
        assert len(repos) == 0

    def test_skips_duplicate_mountpoints(self, mocker, tmp_path):
        """Test skipping duplicate mountpoints."""
        flag_path = tmp_path / ".rpi-usb-cloner-image-repo"
        flag_path.touch()

        # Two devices with same mountpoint (shouldn't happen but test safety)
        device1 = {
            "name": "sda",
            "children": [{"name": "sda1", "type": "part", "mountpoint": str(tmp_path)}],
        }
        device2 = {
            "name": "sdb",
            "children": [{"name": "sdb1", "type": "part", "mountpoint": str(tmp_path)}],
        }

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[device1, device2],
        )

        repos = image_repo.find_image_repos()
        assert len(repos) == 1  # Only one unique mountpoint

    def test_handles_oserror_on_flag_check(self, mocker, tmp_path):
        """Test handling OSError when checking flag file."""
        device = {
            "name": "sda",
            "children": [{"name": "sda1", "type": "part", "mountpoint": str(tmp_path)}],
        }

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[device],
        )
        # Mock Path.exists to raise OSError
        mocker.patch.object(Path, "exists", side_effect=OSError("Permission denied"))

        repos = image_repo.find_image_repos()
        assert len(repos) == 0


class TestListClonezillaImages:
    """Test list_clonezilla_images function."""

    def test_finds_clonezilla_dirs(self, mocker, tmp_path):
        """Test finding Clonezilla image directories."""
        # Create mock clonezilla dir
        clonezilla_dir = tmp_path / "clonezilla" / "backup1"
        clonezilla_dir.mkdir(parents=True)

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[clonezilla_dir],
        )

        images = image_repo.list_clonezilla_images(tmp_path)
        assert len(images) == 1
        assert images[0].name == "backup1"
        assert images[0].image_type == ImageType.CLONEZILLA_DIR

    def test_finds_iso_files(self, mocker, tmp_path):
        """Test finding ISO files."""
        iso_file = tmp_path / "image.iso"
        iso_file.write_bytes(b"fake iso content")

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )

        images = image_repo.list_clonezilla_images(tmp_path)
        assert len(images) == 1
        assert images[0].name == "image.iso"
        assert images[0].image_type == ImageType.ISO

    def test_finds_imageusb_files(self, mocker, tmp_path):
        """Test finding ImageUSB .BIN files."""
        bin_file = tmp_path / "image.bin"
        bin_file.write_bytes(b"IMGUSB" + b"\x00" * 506)

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.imageusb.is_imageusb_file",
            return_value=True,
        )

        images = image_repo.list_clonezilla_images(tmp_path)
        assert len(images) == 1
        assert images[0].name == "image.bin"
        assert images[0].image_type == ImageType.IMAGEUSB_BIN

    def test_skips_duplicate_images(self, mocker, tmp_path):
        """Test skipping duplicate images."""
        clonezilla_dir = tmp_path / "backup"
        clonezilla_dir.mkdir()

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[clonezilla_dir, clonezilla_dir],  # Duplicate
        )

        images = image_repo.list_clonezilla_images(tmp_path)
        assert len(images) == 1  # Only one unique

    def test_sorts_by_name(self, mocker, tmp_path):
        """Test that images are sorted by name."""
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )

        # Create ISO files
        (tmp_path / "zebra.iso").touch()
        (tmp_path / "alpha.iso").touch()
        (tmp_path / "beta.iso").touch()

        images = image_repo.list_clonezilla_images(tmp_path)
        names = [img.name for img in images]
        assert names == ["alpha.iso", "beta.iso", "zebra.iso"]


class TestSumTreeBytes:
    """Test _sum_tree_bytes function."""

    def test_sums_file_sizes(self, tmp_path, mocker):
        """Test summing file sizes in directory tree."""
        # Create test files
        (tmp_path / "file1.txt").write_text("a" * 100)
        (tmp_path / "file2.txt").write_text("b" * 200)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("c" * 300)

        # Mock _is_temp_clonezilla_path to return False for all files
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo._is_temp_clonezilla_path",
            return_value=False,
        )

        result = image_repo._sum_tree_bytes(tmp_path)
        assert result == 600

    def test_skips_temp_files(self, tmp_path):
        """Test skipping temporary files."""
        (tmp_path / "normal.txt").write_text("a" * 100)
        (tmp_path / ".hidden.tmp").write_text("b" * 200)  # Hidden temp file
        (tmp_path / "file.swp").write_text("c" * 300)  # Swap file

        result = image_repo._sum_tree_bytes(tmp_path)
        # Only normal.txt should be counted
        assert result == 100

    @skip_windows_symlink
    def test_skips_symlinks(self, tmp_path):
        """Test skipping symbolic links."""
        (tmp_path / "real.txt").write_text("a" * 100)
        (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")

        result = image_repo._sum_tree_bytes(tmp_path)
        assert result == 100

    def test_handles_oserror(self, tmp_path, mocker):
        """Test handling OSError during tree walk."""
        mocker.patch.object(Path, "rglob", side_effect=OSError("Permission denied"))
        result = image_repo._sum_tree_bytes(tmp_path)
        assert result == 0

    def test_handles_file_stat_error(self, tmp_path, mocker):
        """Test handling stat error on individual file."""
        (tmp_path / "file.txt").write_text("content")
        mocker.patch.object(Path, "stat", side_effect=OSError("Stat failed"))
        result = image_repo._sum_tree_bytes(tmp_path)
        assert result == 0


class TestGetRepoUsage:
    """Test get_repo_usage function."""

    @pytest.mark.skipif(
        not hasattr(__import__("os"), "statvfs"),
        reason="statvfs not available on Windows",
    )
    def test_calculates_usage(self, mocker, tmp_path):
        """Test calculating repository usage statistics."""
        repo = ImageRepo(path=tmp_path, drive_name="sda")

        # Mock statvfs
        mock_stat = MagicMock()
        mock_stat.f_frsize = 4096
        mock_stat.f_blocks = 1000
        mock_stat.f_bavail = 500
        mocker.patch("os.statvfs", return_value=mock_stat)

        # Mock image discovery
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo._iter_clonezilla_image_dirs",
            return_value=[],
        )
        mocker.patch.object(Path, "glob", return_value=[])

        usage = image_repo.get_repo_usage(repo)

        assert usage["total_bytes"] == 4096000
        assert usage["free_bytes"] == 2048000
        assert usage["used_bytes"] == 2048000
        assert "type_bytes" in usage

    @pytest.mark.skipif(
        not hasattr(__import__("os"), "statvfs"),
        reason="statvfs not available on Windows",
    )
    def test_handles_statvfs_error(self, mocker, tmp_path):
        """Test handling statvfs error."""
        repo = ImageRepo(path=tmp_path, drive_name="sda")
        mocker.patch("os.statvfs", side_effect=OSError("Device not found"))

        usage = image_repo.get_repo_usage(repo)

        assert usage["total_bytes"] == 0
        assert usage["used_bytes"] == 0
        assert usage["free_bytes"] == 0


class TestIterClonezillaImageDirs:
    """Test _iter_clonezilla_image_dirs function."""

    def test_yields_unique_dirs(self, mocker, tmp_path):
        """Test yielding unique image directories."""
        dir1 = tmp_path / "backup1"
        dir2 = tmp_path / "backup2"

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[dir1, dir2],
        )

        dirs = list(image_repo._iter_clonezilla_image_dirs(tmp_path))
        assert len(dirs) == 2
        assert dir1 in dirs
        assert dir2 in dirs

    def test_skips_duplicates(self, mocker, tmp_path):
        """Test skipping duplicate directories."""
        dir1 = tmp_path / "backup1"

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[dir1, dir1],  # Duplicate
        )

        dirs = list(image_repo._iter_clonezilla_image_dirs(tmp_path))
        assert len(dirs) == 1
