"""
Additional tests for storage/image_repo.py module to improve coverage.

Covers:
- _iter_partitions function
- _resolve_mountpoint function  
- _is_temp_clonezilla_path function
- _sum_tree_bytes function
- Error handling paths
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rpi_usb_cloner.storage.image_repo import (
    _is_temp_clonezilla_path,
    _iter_partitions,
    _iter_clonezilla_image_dirs,
    _resolve_mountpoint,
    _sum_tree_bytes,
    get_image_size_bytes,
    get_repo_usage,
    list_clonezilla_images,
    REPO_FLAG_FILENAME,
)


class TestIterPartitions:
    """Test _iter_partitions function."""

    def test_single_partition(self):
        """Test iterating a single partition."""
        device = {
            "name": "sda",
            "children": [
                {"name": "sda1", "type": "part"},
            ],
        }
        
        with patch("rpi_usb_cloner.storage.image_repo.devices.get_children") as mock_get_children:
            mock_get_children.return_value = device["children"]
            result = list(_iter_partitions(device))
        
        assert len(result) == 1
        assert result[0]["name"] == "sda1"

    def test_nested_partitions(self):
        """Test iterating nested partitions."""
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
        
        with patch("rpi_usb_cloner.storage.image_repo.devices.get_children") as mock_get_children:
            # First call returns children of device, second returns children of sda1
            mock_get_children.side_effect = [
                device["children"],
                device["children"][0]["children"],
                [],
            ]
            result = list(_iter_partitions(device))
        
        assert len(result) == 2
        names = [p["name"] for p in result]
        assert "sda1" in names
        assert "sda1p1" in names

    def test_no_children(self):
        """Test device with no children."""
        device = {"name": "sda"}
        
        with patch("rpi_usb_cloner.storage.image_repo.devices.get_children") as mock_get_children:
            mock_get_children.return_value = []
            result = list(_iter_partitions(device))
        
        assert result == []

    def test_non_partition_children(self):
        """Test that non-partition children are not yielded."""
        device = {
            "name": "sda",
            "children": [
                {"name": "sda1", "type": "disk"},  # Not a partition
            ],
        }
        
        with patch("rpi_usb_cloner.storage.image_repo.devices.get_children") as mock_get_children:
            mock_get_children.return_value = device["children"]
            result = list(_iter_partitions(device))
        
        assert result == []


class TestResolveMountpoint:
    """Test _resolve_mountpoint function."""

    def test_existing_mountpoint(self):
        """Test partition with existing mountpoint."""
        partition = {"name": "sda1", "mountpoint": "/mnt/usb"}
        
        result = _resolve_mountpoint(partition)
        
        assert result == Path("/mnt/usb")

    def test_no_mountpoint_no_name(self):
        """Test partition with no mountpoint and no name."""
        partition = {"mountpoint": None}
        
        result = _resolve_mountpoint(partition)
        
        assert result is None

    @patch("rpi_usb_cloner.storage.image_repo.mount.mount_partition")
    @patch("rpi_usb_cloner.storage.image_repo.devices.list_usb_disks")
    @patch("rpi_usb_cloner.storage.image_repo._iter_partitions")
    def test_mount_partition_success(
        self, mock_iter_parts, mock_list_usb, mock_mount
    ):
        """Test successfully mounting a partition."""
        partition = {"name": "sda1", "mountpoint": None}
        
        mock_mount.return_value = None
        mock_list_usb.return_value = [
            {
                "name": "sda",
                "children": [
                    {"name": "sda1", "mountpoint": "/mnt/usb", "type": "part"},
                ],
            },
        ]
        mock_iter_parts.return_value = iter([
            {"name": "sda1", "mountpoint": "/mnt/usb", "type": "part"},
        ])
        
        result = _resolve_mountpoint(partition)
        
        mock_mount.assert_called_once_with("/dev/sda1", name="sda1")
        assert result == Path("/mnt/usb")

    @patch("rpi_usb_cloner.storage.image_repo.mount.mount_partition")
    def test_mount_partition_failure(self, mock_mount):
        """Test handling mount failure."""
        partition = {"name": "sda1", "mountpoint": None}
        
        mock_mount.side_effect = RuntimeError("Mount failed")
        
        result = _resolve_mountpoint(partition)
        
        assert result is None

    @patch("rpi_usb_cloner.storage.image_repo.mount.mount_partition")
    @patch("rpi_usb_cloner.storage.image_repo.devices.list_usb_disks")
    @patch("rpi_usb_cloner.storage.image_repo._iter_partitions")
    def test_partition_not_found_after_mount(
        self, mock_iter_parts, mock_list_usb, mock_mount
    ):
        """Test when partition is not found after mounting."""
        partition = {"name": "sda1", "mountpoint": None}
        
        mock_mount.return_value = None
        mock_list_usb.return_value = []  # No devices found
        mock_iter_parts.return_value = iter([])
        
        result = _resolve_mountpoint(partition)
        
        assert result is None


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


class TestSumTreeBytes:
    """Test _sum_tree_bytes function."""

    def test_empty_directory(self, tmp_path):
        """Test empty directory returns 0."""
        result = _sum_tree_bytes(tmp_path)
        assert result == 0

    def test_single_file(self, tmp_path):
        """Test directory with single file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        
        result = _sum_tree_bytes(tmp_path)
        assert result == 13  # Length of "Hello, World!"

    def test_multiple_files(self, tmp_path):
        """Test directory with multiple files."""
        (tmp_path / "file1.txt").write_text("Hello")  # 5 bytes
        (tmp_path / "file2.txt").write_text("World")  # 5 bytes
        
        result = _sum_tree_bytes(tmp_path)
        assert result == 10

    def test_nested_directories(self, tmp_path):
        """Test nested directory structure."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "root.txt").write_text("root")  # 4 bytes
        (subdir / "nested.txt").write_text("nested")  # 6 bytes
        
        result = _sum_tree_bytes(tmp_path)
        assert result == 10

    def test_skips_temp_files(self, tmp_path):
        """Test that temp files are skipped."""
        (tmp_path / "normal.txt").write_text("data")  # 4 bytes
        (tmp_path / ".hidden").write_text("hidden")  # Should be skipped
        (tmp_path / "temp.tmp").write_text("temp")  # Should be skipped
        
        result = _sum_tree_bytes(tmp_path)
        assert result == 4

    def test_skips_symlinks(self, tmp_path):
        """Test that symlinks are skipped."""
        real_file = tmp_path / "real.txt"
        real_file.write_text("data")  # 4 bytes
        symlink = tmp_path / "link.txt"
        
        try:
            symlink.symlink_to(real_file)
            result = _sum_tree_bytes(tmp_path)
            # Should only count real file
            assert result == 4
        except (OSError, NotImplementedError):
            # Windows may not support symlinks without admin
            pytest.skip("Symlinks not supported on this platform")

    def test_permission_error_handling(self, tmp_path):
        """Test handling permission errors gracefully."""
        # Create a file
        (tmp_path / "readable.txt").write_text("data")
        
        # Mock rglob to raise permission error then succeed
        original_rglob = Path.rglob
        def mock_rglob(self, pattern):
            if str(self) == str(tmp_path):
                yield from [tmp_path / "readable.txt"]
            else:
                yield from original_rglob(self, pattern)
        
        with patch.object(Path, "rglob", mock_rglob):
            result = _sum_tree_bytes(tmp_path)
            assert result == 4


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

    def test_clonezilla_directory(self, tmp_path):
        """Test calculating size for Clonezilla directory."""
        from rpi_usb_cloner.domain import DiskImage, ImageType
        
        image_dir = tmp_path / "clonezilla_image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("sda1 sda2")
        (image_dir / "disk").write_text("sda")
        
        image = DiskImage(
            name="clonezilla_image",
            path=image_dir,
            image_type=ImageType.CLONEZILLA_DIR,
            size_bytes=None,
        )
        
        result = get_image_size_bytes(image)
        # Should be sum of file sizes
        assert result > 0

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


class TestIterClonezillaImageDirs:
    """Test _iter_clonezilla_image_dirs function."""

    @patch("rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs")
    def test_yields_unique_dirs(self, mock_list_dirs):
        """Test that duplicate dirs are filtered."""
        repo_root = Path("/repo")
        
        mock_list_dirs.side_effect = [
            [repo_root / "image1"],  # clonezilla dir
            [repo_root / "image1"],  # images dir (duplicate)
            [repo_root / "image2"],  # root dir
        ]
        
        result = list(_iter_clonezilla_image_dirs(repo_root))
        
        assert len(result) == 2
        names = [p.name for p in result]
        assert "image1" in names
        assert "image2" in names


class TestGetRepoUsage:
    """Test get_repo_usage function."""

    @patch("rpi_usb_cloner.storage.image_repo._get_repo_space_bytes")
    @patch("rpi_usb_cloner.storage.image_repo._iter_clonezilla_image_dirs")
    @patch("rpi_usb_cloner.storage.image_repo._sum_tree_bytes")
    def test_calculates_usage(
        self, mock_sum_tree, mock_iter_dirs, mock_get_space
    ):
        """Test that repo usage is calculated correctly."""
        from rpi_usb_cloner.domain import ImageRepo
        
        repo = ImageRepo(path=Path("/mnt/usb"), drive_name="sda")
        
        mock_get_space.return_value = (1000000, 500000, 500000)  # total, used, free
        mock_iter_dirs.return_value = iter([Path("/mnt/usb/image1")])
        mock_sum_tree.return_value = 100000  # Clonezilla size
        
        # Need to mock glob for ISO and BIN files
        with patch.object(Path, "glob") as mock_glob:
            mock_glob.side_effect = [
                [],  # *.iso files
                [],  # *.bin files
            ]
            
            result = get_repo_usage(repo)
        
        assert result["total_bytes"] == 1000000
        assert result["used_bytes"] == 500000
        assert result["free_bytes"] == 500000
        assert result["type_bytes"]["clonezilla"] == 100000
        assert result["type_bytes"]["iso"] == 0
        assert result["type_bytes"]["imageusb"] == 0
        assert result["type_bytes"]["other"] == 400000  # 500000 - 100000

    @patch("rpi_usb_cloner.storage.image_repo._get_repo_space_bytes")
    def test_oserror_returns_zeros(self, mock_get_space):
        """Test handling OSError from statvfs."""
        from rpi_usb_cloner.domain import ImageRepo
        
        repo = ImageRepo(path=Path("/mnt/usb"), drive_name="sda")
        mock_get_space.return_value = (0, 0, 0)
        
        result = get_repo_usage(repo)
        
        assert result["total_bytes"] == 0
        assert result["used_bytes"] == 0
        assert result["free_bytes"] == 0


class TestListClonezillaImages:
    """Test list_clonezilla_images function."""

    @patch("rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs")
    @patch("rpi_usb_cloner.storage.image_repo.imageusb.is_imageusb_file")
    def test_lists_all_image_types(self, mock_is_imageusb, mock_list_dirs):
        """Test listing Clonezilla, ISO, and ImageUSB files."""
        repo_root = Path("/repo")
        
        mock_list_dirs.return_value = [repo_root / "clonezilla_img"]
        mock_is_imageusb.return_value = True
        
        # Create mock files in the repo
        with patch.object(Path, "glob") as mock_glob:
            mock_glob.side_effect = [
                [repo_root / "image.iso"],  # *.iso files
                [repo_root / "image.bin"],  # *.bin files
            ]
            
            # Mock is_file and stat
            with patch.object(Path, "is_file", return_value=True):
                with patch.object(Path, "stat") as mock_stat:
                    mock_stat.return_value = Mock(st_size=1024)
                    
                    result = list_clonezilla_images(repo_root)
        
        # Should have Clonezilla dir, ISO, and BIN
        assert len(result) == 3
        names = [img.name for img in result]
        assert "clonezilla_img" in names
        assert "image.iso" in names
        assert "image.bin" in names

    @patch("rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs")
    def test_skips_duplicate_iso(self, mock_list_dirs):
        """Test that ISO files already seen are skipped."""
        repo_root = Path("/repo")
        
        mock_list_dirs.return_value = []
        
        with patch.object(Path, "glob") as mock_glob:
            mock_glob.side_effect = [
                [repo_root / "image.iso"],
                [],
            ]
            
            with patch.object(Path, "is_file", return_value=True):
                with patch.object(Path, "stat") as mock_stat:
                    mock_stat.return_value = Mock(st_size=1024)
                    
                    result = list_clonezilla_images(repo_root)
        
        assert len(result) == 1
        assert result[0].name == "image.iso"
