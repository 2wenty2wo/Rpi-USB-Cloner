"""Tests for storage/image_repo.py module.

This module tests image repository discovery and management functions.
"""

from pathlib import Path
from unittest.mock import patch

from rpi_usb_cloner.domain import DiskImage, ImageRepo, ImageType


class TestIterPartitions:
    """Tests for _iter_partitions helper function."""

    def test_iter_partitions_with_children(self):
        """Test iterating partitions from a device with children."""
        from rpi_usb_cloner.storage.image_repo import _iter_partitions

        device = {
            "name": "sda",
            "type": "disk",
            "children": [
                {"name": "sda1", "type": "part"},
                {"name": "sda2", "type": "part"},
            ],
        }

        partitions = list(_iter_partitions(device))
        assert len(partitions) == 2
        # Order is not guaranteed (stack-based iteration)
        partition_names = {p["name"] for p in partitions}
        assert partition_names == {"sda1", "sda2"}

    def test_iter_partitions_with_nested_children(self, mocker):
        """Test iterating partitions with nested children (LVM, etc.)."""
        from rpi_usb_cloner.storage.image_repo import _iter_partitions

        # Mock devices.get_children to return different children
        mock_get_children = mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.get_children"
        )

        device = {"name": "sda", "type": "disk"}

        # First call returns disk children, subsequent calls return empty
        mock_get_children.side_effect = [
            [{"name": "sda1", "type": "part"}, {"name": "sda2", "type": "lvm"}],
            [],  # sda1 has no children
            [{"name": "sda2p1", "type": "part"}],  # sda2 (lvm) has partition
            [],  # sda2p1 has no children
        ]

        partitions = list(_iter_partitions(device))
        # Should only return type="part"
        partition_names = [p["name"] for p in partitions]
        assert "sda1" in partition_names
        assert "sda2p1" in partition_names
        assert "sda2" not in partition_names  # type=lvm, not part

    def test_iter_partitions_no_children(self, mocker):
        """Test iterating partitions with no children."""
        from rpi_usb_cloner.storage.image_repo import _iter_partitions

        mock_get_children = mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.get_children"
        )
        mock_get_children.return_value = []

        device = {"name": "sda", "type": "disk"}
        partitions = list(_iter_partitions(device))
        assert len(partitions) == 0


class TestResolvesMountpoint:
    """Tests for _resolve_mountpoint helper function."""

    def test_resolve_mountpoint_already_mounted(self):
        """Test resolving mountpoint for already mounted partition."""
        from rpi_usb_cloner.storage.image_repo import _resolve_mountpoint

        partition = {"name": "sda1", "mountpoint": "/media/usb"}
        result = _resolve_mountpoint(partition)
        assert result == Path("/media/usb")

    def test_resolve_mountpoint_no_name(self):
        """Test resolving mountpoint with no partition name."""
        from rpi_usb_cloner.storage.image_repo import _resolve_mountpoint

        partition = {"mountpoint": None, "name": None}
        result = _resolve_mountpoint(partition)
        assert result is None

    def test_resolve_mountpoint_mount_fails_value_error(self, mocker):
        """Test resolving mountpoint when mount fails with ValueError."""
        from rpi_usb_cloner.storage.image_repo import _resolve_mountpoint

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.mount.mount_partition",
            side_effect=ValueError("Mount failed"),
        )

        partition = {"name": "sda1", "mountpoint": None}
        result = _resolve_mountpoint(partition)
        assert result is None

    def test_resolve_mountpoint_mount_fails_runtime_error(self, mocker):
        """Test resolving mountpoint when mount fails with RuntimeError."""
        from rpi_usb_cloner.storage.image_repo import _resolve_mountpoint

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.mount.mount_partition",
            side_effect=RuntimeError("Mount failed"),
        )

        partition = {"name": "sda1", "mountpoint": None}
        result = _resolve_mountpoint(partition)
        assert result is None

    def test_resolve_mountpoint_after_mount(self, mocker):
        """Test resolving mountpoint after successful mount."""
        from rpi_usb_cloner.storage.image_repo import _resolve_mountpoint

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.mount.mount_partition",
            return_value=None,
        )

        # Mock list_usb_disks to return the newly mounted partition
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[
                {
                    "name": "sda",
                    "type": "disk",
                    "children": [
                        {"name": "sda1", "type": "part", "mountpoint": "/media/usb"}
                    ],
                }
            ],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.get_children",
            return_value=[{"name": "sda1", "type": "part", "mountpoint": "/media/usb"}],
        )

        partition = {"name": "sda1", "mountpoint": None}
        result = _resolve_mountpoint(partition)
        assert result == Path("/media/usb")

    def test_resolve_mountpoint_partition_not_found_after_mount(self, mocker):
        """Test resolving mountpoint when partition not found after mount."""
        from rpi_usb_cloner.storage.image_repo import _resolve_mountpoint

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.mount.mount_partition",
            return_value=None,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[],
        )

        partition = {"name": "sda1", "mountpoint": None}
        result = _resolve_mountpoint(partition)
        assert result is None


class TestFindImageRepos:
    """Tests for find_image_repos function."""

    def test_find_image_repos_no_devices(self, mocker):
        """Test finding repos with no USB devices."""
        from rpi_usb_cloner.storage.image_repo import find_image_repos

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[],
        )

        repos = find_image_repos()
        assert repos == []

    def test_find_image_repos_with_flag_file(self, mocker, tmp_path):
        """Test finding repos with flag file present."""
        from rpi_usb_cloner.storage.image_repo import (
            REPO_FLAG_FILENAME,
            find_image_repos,
        )

        # Create flag file
        (tmp_path / REPO_FLAG_FILENAME).touch()

        partition = {"name": "sda1", "type": "part", "mountpoint": str(tmp_path)}

        # Mock device iteration
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[{"name": "sda", "type": "disk"}],
        )
        # Return partition for disk, then empty list for partition (prevents infinite loop)
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.get_children",
            side_effect=[[partition], []],
        )

        repos = find_image_repos()
        assert len(repos) == 1
        assert repos[0].path == tmp_path
        assert repos[0].drive_name == "sda"

    def test_find_image_repos_no_flag_file(self, mocker, tmp_path):
        """Test finding repos without flag file."""
        from rpi_usb_cloner.storage.image_repo import find_image_repos

        # No flag file created
        partition = {"name": "sda1", "type": "part", "mountpoint": str(tmp_path)}

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[{"name": "sda", "type": "disk"}],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.get_children",
            side_effect=[[partition], []],
        )

        repos = find_image_repos()
        assert repos == []

    def test_find_image_repos_custom_flag_filename(self, mocker, tmp_path):
        """Test finding repos with custom flag filename."""
        from rpi_usb_cloner.storage.image_repo import find_image_repos

        custom_flag = ".my-custom-flag"
        (tmp_path / custom_flag).touch()
        partition = {"name": "sda1", "type": "part", "mountpoint": str(tmp_path)}

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[{"name": "sda", "type": "disk"}],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.get_children",
            side_effect=[[partition], []],
        )

        repos = find_image_repos(flag_filename=custom_flag)
        assert len(repos) == 1

    def test_find_image_repos_deduplicates(self, mocker, tmp_path):
        """Test that duplicate mountpoints are not returned."""
        from rpi_usb_cloner.storage.image_repo import (
            REPO_FLAG_FILENAME,
            find_image_repos,
        )

        (tmp_path / REPO_FLAG_FILENAME).touch()
        partition = {"name": "sda1", "type": "part", "mountpoint": str(tmp_path)}

        # Two devices with same mountpoint (shouldn't happen, but test dedup)
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[
                {"name": "sda", "type": "disk"},
                {"name": "sdb", "type": "disk"},
            ],
        )
        # Both return same mountpoint - use side_effect for multiple calls
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.get_children",
            side_effect=[[partition], [], [partition], []],
        )

        repos = find_image_repos()
        # Should only return one repo despite two devices pointing to same mount
        assert len(repos) == 1

    def test_find_image_repos_oserror_on_flag_check(self, mocker, tmp_path):
        """Test handling OSError when checking flag file."""
        from rpi_usb_cloner.storage.image_repo import find_image_repos

        partition = {"name": "sda1", "type": "part", "mountpoint": str(tmp_path)}

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.list_usb_disks",
            return_value=[{"name": "sda", "type": "disk"}],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.devices.get_children",
            side_effect=[[partition], []],
        )

        # Mock Path.exists to raise OSError
        with patch.object(Path, "exists", side_effect=OSError("Permission denied")):
            repos = find_image_repos()
            assert repos == []


class TestListClonezillaImages:
    """Tests for list_clonezilla_images function."""

    def test_list_clonezilla_images_empty_repo(self, mocker, tmp_path):
        """Test listing images in empty repository."""
        from rpi_usb_cloner.storage.image_repo import list_clonezilla_images

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )

        images = list_clonezilla_images(tmp_path)
        assert images == []

    def test_list_clonezilla_images_with_clonezilla_dirs(self, mocker, tmp_path):
        """Test listing Clonezilla image directories."""
        from rpi_usb_cloner.storage.image_repo import list_clonezilla_images

        # Create image directories
        img1 = tmp_path / "clonezilla" / "image1"
        img2 = tmp_path / "clonezilla" / "image2"
        img1.mkdir(parents=True)
        img2.mkdir(parents=True)

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            side_effect=lambda path: [img1, img2] if "clonezilla" in str(path) else [],
        )

        images = list_clonezilla_images(tmp_path)
        assert len(images) == 2
        assert all(img.image_type == ImageType.CLONEZILLA_DIR for img in images)
        names = [img.name for img in images]
        assert "image1" in names
        assert "image2" in names

    def test_list_clonezilla_images_with_iso_files(self, mocker, tmp_path):
        """Test listing ISO files in repository."""
        from rpi_usb_cloner.storage.image_repo import list_clonezilla_images

        # Create ISO files
        iso1 = tmp_path / "ubuntu.iso"
        iso2 = tmp_path / "debian.iso"
        iso1.write_bytes(b"x" * 1000)
        iso2.write_bytes(b"y" * 2000)

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )

        images = list_clonezilla_images(tmp_path)
        iso_images = [img for img in images if img.image_type == ImageType.ISO]
        assert len(iso_images) == 2
        assert iso_images[0].name == "debian.iso"  # Sorted by name
        assert iso_images[1].name == "ubuntu.iso"
        assert iso_images[0].size_bytes == 2000
        assert iso_images[1].size_bytes == 1000

    def test_list_clonezilla_images_with_imageusb_bin(self, mocker, tmp_path):
        """Test listing ImageUSB .BIN files in repository."""
        from rpi_usb_cloner.storage.image_repo import list_clonezilla_images

        # Create .BIN file
        bin_file = tmp_path / "backup.bin"
        bin_file.write_bytes(b"z" * 500)

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.imageusb.is_imageusb_file",
            return_value=True,
        )

        images = list_clonezilla_images(tmp_path)
        bin_images = [img for img in images if img.image_type == ImageType.IMAGEUSB_BIN]
        assert len(bin_images) == 1
        assert bin_images[0].name == "backup.bin"
        assert bin_images[0].size_bytes == 500

    def test_list_clonezilla_images_non_imageusb_bin_skipped(self, mocker, tmp_path):
        """Test that non-ImageUSB .BIN files are skipped."""
        from rpi_usb_cloner.storage.image_repo import list_clonezilla_images

        # Create .BIN file that's not ImageUSB format
        bin_file = tmp_path / "random.bin"
        bin_file.write_bytes(b"random data")

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.imageusb.is_imageusb_file",
            return_value=False,
        )

        images = list_clonezilla_images(tmp_path)
        bin_images = [img for img in images if img.image_type == ImageType.IMAGEUSB_BIN]
        assert len(bin_images) == 0

    def test_list_clonezilla_images_deduplicates(self, mocker, tmp_path):
        """Test that duplicate images are not returned."""
        from rpi_usb_cloner.storage.image_repo import list_clonezilla_images

        img = tmp_path / "image1"
        img.mkdir()

        # Return same image from multiple candidate dirs
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[img],
        )

        images = list_clonezilla_images(tmp_path)
        assert len(images) == 1

    def test_list_clonezilla_images_sorted_by_name(self, mocker, tmp_path):
        """Test that images are sorted alphabetically by name."""
        from rpi_usb_cloner.storage.image_repo import list_clonezilla_images

        # Create images in non-alphabetical order
        img_c = tmp_path / "charlie"
        img_a = tmp_path / "alpha"
        img_b = tmp_path / "bravo"
        img_c.mkdir()
        img_a.mkdir()
        img_b.mkdir()

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            side_effect=lambda path: [img_c, img_a, img_b] if path == tmp_path else [],
        )

        images = list_clonezilla_images(tmp_path)
        assert [img.name for img in images] == ["alpha", "bravo", "charlie"]

    def test_list_clonezilla_images_iso_with_size(self, mocker, tmp_path):
        """Test listing ISO files records their size."""
        from rpi_usb_cloner.storage.image_repo import list_clonezilla_images

        iso_file = tmp_path / "test.iso"
        iso_file.write_bytes(b"data" * 100)  # 400 bytes

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )

        images = list_clonezilla_images(tmp_path)
        iso_images = [img for img in images if img.image_type == ImageType.ISO]
        assert len(iso_images) == 1
        assert iso_images[0].name == "test.iso"
        assert iso_images[0].size_bytes == 400


class TestIsTempClonezillaPath:
    """Tests for _is_temp_clonezilla_path helper function."""

    def test_temp_path_dot_prefix(self):
        """Test detecting dotfile/hidden paths."""
        from rpi_usb_cloner.storage.image_repo import _is_temp_clonezilla_path

        assert _is_temp_clonezilla_path(Path(".hidden")) is True
        assert _is_temp_clonezilla_path(Path(".DS_Store")) is True

    def test_temp_path_tmp_suffix(self):
        """Test detecting .tmp suffix."""
        from rpi_usb_cloner.storage.image_repo import _is_temp_clonezilla_path

        assert _is_temp_clonezilla_path(Path("file.tmp")) is True
        assert _is_temp_clonezilla_path(Path("file.TMP")) is True

    def test_temp_path_part_suffix(self):
        """Test detecting .part suffix."""
        from rpi_usb_cloner.storage.image_repo import _is_temp_clonezilla_path

        assert _is_temp_clonezilla_path(Path("download.part")) is True
        assert _is_temp_clonezilla_path(Path("download.PART")) is True

    def test_temp_path_partial_suffix(self):
        """Test detecting .partial suffix."""
        from rpi_usb_cloner.storage.image_repo import _is_temp_clonezilla_path

        assert _is_temp_clonezilla_path(Path("file.partial")) is True

    def test_temp_path_swp_suffix(self):
        """Test detecting .swp/.swx suffix (vim)."""
        from rpi_usb_cloner.storage.image_repo import _is_temp_clonezilla_path

        assert _is_temp_clonezilla_path(Path("file.swp")) is True
        assert _is_temp_clonezilla_path(Path("file.swx")) is True

    def test_temp_path_tmp_in_path(self):
        """Test detecting tmp/temp in path parts."""
        from rpi_usb_cloner.storage.image_repo import _is_temp_clonezilla_path

        assert _is_temp_clonezilla_path(Path("/tmp/file.txt")) is True
        assert _is_temp_clonezilla_path(Path("/var/temp/file.txt")) is True
        assert _is_temp_clonezilla_path(Path("/data/TMP/file.txt")) is True

    def test_normal_path_not_temp(self):
        """Test normal paths are not detected as temp."""
        from rpi_usb_cloner.storage.image_repo import _is_temp_clonezilla_path

        assert _is_temp_clonezilla_path(Path("normal_file.txt")) is False
        assert _is_temp_clonezilla_path(Path("/data/image.gz")) is False
        assert (
            _is_temp_clonezilla_path(Path("template.doc")) is False
        )  # 'temp' substring


class TestSumTreeBytes:
    """Tests for _sum_tree_bytes helper function.

    Note: These tests mock _is_temp_clonezilla_path because tmp_path contains
    '/tmp/' in its path, which would be detected as a temp directory.
    """

    def test_sum_tree_bytes_single_file(self, mocker, tmp_path):
        """Test summing single file."""
        from rpi_usb_cloner.storage.image_repo import _sum_tree_bytes

        # Mock to only check file-level temp patterns, not parent path
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo._is_temp_clonezilla_path",
            side_effect=lambda p: p.name.startswith(".")
            or p.suffix in {".tmp", ".part"},
        )

        (tmp_path / "file.txt").write_bytes(b"x" * 100)
        assert _sum_tree_bytes(tmp_path) == 100

    def test_sum_tree_bytes_multiple_files(self, mocker, tmp_path):
        """Test summing multiple files."""
        from rpi_usb_cloner.storage.image_repo import _sum_tree_bytes

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo._is_temp_clonezilla_path",
            side_effect=lambda p: p.name.startswith(".")
            or p.suffix in {".tmp", ".part"},
        )

        (tmp_path / "file1.txt").write_bytes(b"a" * 100)
        (tmp_path / "file2.txt").write_bytes(b"b" * 200)
        assert _sum_tree_bytes(tmp_path) == 300

    def test_sum_tree_bytes_nested_dirs(self, mocker, tmp_path):
        """Test summing files in nested directories."""
        from rpi_usb_cloner.storage.image_repo import _sum_tree_bytes

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo._is_temp_clonezilla_path",
            side_effect=lambda p: p.name.startswith(".")
            or p.suffix in {".tmp", ".part"},
        )

        (tmp_path / "dir1").mkdir()
        (tmp_path / "dir1" / "file.txt").write_bytes(b"x" * 50)
        (tmp_path / "dir2" / "subdir").mkdir(parents=True)
        (tmp_path / "dir2" / "subdir" / "file.txt").write_bytes(b"y" * 75)
        assert _sum_tree_bytes(tmp_path) == 125

    def test_sum_tree_bytes_skips_temp_files(self, mocker, tmp_path):
        """Test that temp files are skipped."""
        from rpi_usb_cloner.storage.image_repo import _sum_tree_bytes

        # Mock that detects temp files by name only
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo._is_temp_clonezilla_path",
            side_effect=lambda p: p.name.startswith(".")
            or p.suffix in {".tmp", ".part"},
        )

        (tmp_path / "normal.txt").write_bytes(b"x" * 100)
        (tmp_path / ".hidden").write_bytes(b"y" * 200)
        (tmp_path / "file.tmp").write_bytes(b"z" * 300)
        # Only normal.txt should be counted
        assert _sum_tree_bytes(tmp_path) == 100

    def test_sum_tree_bytes_empty_dir(self, tmp_path):
        """Test summing empty directory."""
        from rpi_usb_cloner.storage.image_repo import _sum_tree_bytes

        # Empty dir returns 0 regardless of temp path check
        assert _sum_tree_bytes(tmp_path) == 0

    def test_sum_tree_bytes_nonexistent_dir(self, tmp_path):
        """Test summing non-existent directory."""
        from rpi_usb_cloner.storage.image_repo import _sum_tree_bytes

        nonexistent = tmp_path / "does_not_exist"
        assert _sum_tree_bytes(nonexistent) == 0

    def test_sum_tree_bytes_skips_symlinks(self, mocker, tmp_path):
        """Test that symlinks are skipped."""
        from rpi_usb_cloner.storage.image_repo import _sum_tree_bytes

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo._is_temp_clonezilla_path",
            return_value=False,
        )

        (tmp_path / "real_file.txt").write_bytes(b"x" * 100)
        (tmp_path / "symlink.txt").symlink_to(tmp_path / "real_file.txt")
        # Only real_file.txt should be counted (symlink points to same data)
        assert _sum_tree_bytes(tmp_path) == 100


class TestGetImageSizeBytes:
    """Tests for get_image_size_bytes function."""

    def test_get_image_size_bytes_with_size(self):
        """Test returning pre-computed size."""
        from rpi_usb_cloner.storage.image_repo import get_image_size_bytes

        image = DiskImage(
            name="test.iso",
            path=Path("/test.iso"),
            image_type=ImageType.ISO,
            size_bytes=1000,
        )
        assert get_image_size_bytes(image) == 1000

    def test_get_image_size_bytes_clonezilla_dir(self, mocker, tmp_path):
        """Test computing size for Clonezilla directory."""
        from rpi_usb_cloner.storage.image_repo import get_image_size_bytes

        # Mock to avoid /tmp/ being detected as temp path
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo._is_temp_clonezilla_path",
            return_value=False,
        )

        # Create test files
        (tmp_path / "file1.txt").write_bytes(b"x" * 100)
        (tmp_path / "file2.txt").write_bytes(b"y" * 200)

        image = DiskImage(
            name="test_image",
            path=tmp_path,
            image_type=ImageType.CLONEZILLA_DIR,
            size_bytes=None,
        )
        assert get_image_size_bytes(image) == 300

    def test_get_image_size_bytes_iso_no_size(self):
        """Test ISO without pre-computed size returns None."""
        from rpi_usb_cloner.storage.image_repo import get_image_size_bytes

        image = DiskImage(
            name="test.iso",
            path=Path("/test.iso"),
            image_type=ImageType.ISO,
            size_bytes=None,
        )
        assert get_image_size_bytes(image) is None


class TestGetRepoSpaceBytes:
    """Tests for _get_repo_space_bytes helper function."""

    def test_get_repo_space_bytes_success(self, mocker, tmp_path):
        """Test getting repository space statistics."""
        from rpi_usb_cloner.storage.image_repo import _get_repo_space_bytes

        # Use the actual tmp_path which exists
        total, used, free = _get_repo_space_bytes(tmp_path)
        assert total > 0
        assert used >= 0
        assert free >= 0
        assert used + free <= total  # May not equal due to reserved blocks

    def test_get_repo_space_bytes_nonexistent(self):
        """Test getting space for non-existent path."""
        from rpi_usb_cloner.storage.image_repo import _get_repo_space_bytes

        nonexistent = Path("/nonexistent/path/does/not/exist")
        total, used, free = _get_repo_space_bytes(nonexistent)
        assert total == 0
        assert used == 0
        assert free == 0


class TestGetRepoUsage:
    """Tests for get_repo_usage function."""

    def test_get_repo_usage_empty_repo(self, mocker, tmp_path):
        """Test usage stats for empty repository."""
        from rpi_usb_cloner.storage.image_repo import get_repo_usage

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )

        repo = ImageRepo(path=tmp_path, drive_name="sda")
        usage = get_repo_usage(repo)

        assert "total_bytes" in usage
        assert "used_bytes" in usage
        assert "free_bytes" in usage
        assert "type_bytes" in usage
        assert usage["type_bytes"]["clonezilla"] == 0
        assert usage["type_bytes"]["iso"] == 0
        assert usage["type_bytes"]["imageusb"] == 0

    def test_get_repo_usage_with_iso_files(self, mocker, tmp_path):
        """Test usage stats with ISO files."""
        from rpi_usb_cloner.storage.image_repo import get_repo_usage

        # Create ISO files
        (tmp_path / "test.iso").write_bytes(b"x" * 1000)

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )

        repo = ImageRepo(path=tmp_path, drive_name="sda")
        usage = get_repo_usage(repo)

        assert usage["type_bytes"]["iso"] == 1000

    def test_get_repo_usage_with_imageusb_files(self, mocker, tmp_path):
        """Test usage stats with ImageUSB files."""
        from rpi_usb_cloner.storage.image_repo import get_repo_usage

        # Create .bin file
        (tmp_path / "backup.bin").write_bytes(b"y" * 500)

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.imageusb.is_imageusb_file",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.get_imageusb_metadata",
            return_value={"data_size_bytes": 500},
        )

        repo = ImageRepo(path=tmp_path, drive_name="sda")
        usage = get_repo_usage(repo)

        assert usage["type_bytes"]["imageusb"] == 500

    def test_get_repo_usage_calculates_other(self, mocker, tmp_path):
        """Test that 'other' is calculated from remaining used space."""
        from rpi_usb_cloner.storage.image_repo import get_repo_usage

        # Create a file that's not an image type
        (tmp_path / "random.txt").write_bytes(b"z" * 100)

        mocker.patch(
            "rpi_usb_cloner.storage.image_repo.clonezilla.list_clonezilla_image_dirs",
            return_value=[],
        )

        repo = ImageRepo(path=tmp_path, drive_name="sda")
        usage = get_repo_usage(repo)

        # 'other' should account for the random.txt file and any system overhead
        assert usage["type_bytes"]["other"] >= 0
