"""Tests for Clonezilla image discovery and parsing."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rpi_usb_cloner.storage.clonezilla.image_discovery import (
    build_partition_restore_op,
    find_image_repository,
    find_partition_table,
    get_mountpoint,
    get_partclone_tool,
    is_clonezilla_image_dir,
    list_clonezilla_image_dirs,
    load_image,
    parse_clonezilla_image,
)
from rpi_usb_cloner.storage.clonezilla.models import ClonezillaImage, PartitionRestoreOp


class TestGetMountpoint:
    def test_get_mountpoint_from_device(self):
        """Test getting mountpoint directly from device."""
        device = {"mountpoint": "/mnt/usb"}
        assert get_mountpoint(device) == "/mnt/usb"

    def test_get_mountpoint_from_children(self):
        """Test getting mountpoint from device children."""
        device = {
            "mountpoint": None,
            "children": [
                {"name": "sda1", "mountpoint": "/mnt/data"}
            ]
        }
        with patch("rpi_usb_cloner.storage.devices.get_children") as mock_get_children:
            mock_get_children.return_value = [{"mountpoint": "/mnt/data"}]
            assert get_mountpoint(device) == "/mnt/data"

    def test_get_mountpoint_none(self):
        """Test when no mountpoint is available."""
        device = {"mountpoint": None, "children": []}
        with patch("rpi_usb_cloner.storage.devices.get_children") as mock_get_children:
            mock_get_children.return_value = []
            assert get_mountpoint(device) is None

    def test_get_mountpoint_multiple_children(self):
        """Test getting mountpoint from first mounted child."""
        device = {"mountpoint": None}
        with patch("rpi_usb_cloner.storage.devices.get_children") as mock_get_children:
            mock_get_children.return_value = [
                {"mountpoint": None},
                {"mountpoint": "/mnt/first"},
                {"mountpoint": "/mnt/second"}
            ]
            assert get_mountpoint(device) == "/mnt/first"


class TestFindPartitionTable:
    def test_find_partition_table_sf(self, tmp_path):
        """Test finding partition table with .sf suffix."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        pt_file = image_dir / "sda-pt.sf"
        pt_file.touch()

        result = find_partition_table(image_dir)
        assert result == pt_file

    def test_find_partition_table_sgdisk(self, tmp_path):
        """Test finding partition table with .sgdisk suffix."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        pt_file = image_dir / "sda-pt.sgdisk"
        pt_file.touch()

        result = find_partition_table(image_dir)
        assert result == pt_file

    def test_find_partition_table_parted(self, tmp_path):
        """Test finding partition table with .parted suffix."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        pt_file = image_dir / "sda-pt.parted"
        pt_file.touch()

        result = find_partition_table(image_dir)
        assert result == pt_file

    def test_find_partition_table_priority(self, tmp_path):
        """Test that .sf has priority over other formats."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "sda-pt.sf").touch()
        (image_dir / "sda-pt.sgdisk").touch()
        (image_dir / "sda-pt.parted").touch()

        result = find_partition_table(image_dir)
        assert result.name == "sda-pt.sf"

    def test_find_partition_table_none(self, tmp_path):
        """Test when no partition table exists."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()

        result = find_partition_table(image_dir)
        assert result is None


class TestIsClonezillaImageDir:
    def test_is_clonezilla_image_dir_with_parts_and_table(self, tmp_path):
        """Test directory with parts file and partition table."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("sda1 sda2")
        (image_dir / "sda-pt.parted").touch()

        assert is_clonezilla_image_dir(image_dir) is True

    def test_is_clonezilla_image_dir_with_parts_and_ptcl_img(self, tmp_path):
        """Test directory with parts file and partclone images."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("sda1")
        (image_dir / "sda1.ext4-ptcl-img.aa").touch()

        assert is_clonezilla_image_dir(image_dir) is True

    def test_is_clonezilla_image_dir_with_parts_and_dd_img(self, tmp_path):
        """Test directory with parts file and dd images."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("sda1")
        (image_dir / "sda1.dd-img").touch()

        assert is_clonezilla_image_dir(image_dir) is True

    def test_is_clonezilla_image_dir_no_parts(self, tmp_path):
        """Test directory without parts file."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "sda-pt.parted").touch()

        assert is_clonezilla_image_dir(image_dir) is False

    def test_is_clonezilla_image_dir_parts_only(self, tmp_path):
        """Test directory with only parts file."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("sda1")

        assert is_clonezilla_image_dir(image_dir) is False

    def test_is_clonezilla_image_dir_not_a_directory(self, tmp_path):
        """Test with a file instead of directory."""
        not_a_dir = tmp_path / "file.txt"
        not_a_dir.touch()

        assert is_clonezilla_image_dir(not_a_dir) is False


class TestFindImageRepository:
    def test_find_image_repository_in_clonezilla_dir(self, tmp_path):
        """Test finding repository in /clonezilla directory."""
        mount = tmp_path / "mount"
        clonezilla_dir = mount / "clonezilla"
        image_dir = clonezilla_dir / "image1"
        image_dir.mkdir(parents=True)
        (image_dir / "parts").write_text("sda1")
        (image_dir / "sda-pt.parted").touch()

        device = {"mountpoint": str(mount)}
        result = find_image_repository(device)
        assert result == clonezilla_dir

    def test_find_image_repository_in_images_dir(self, tmp_path):
        """Test finding repository in /images directory."""
        mount = tmp_path / "mount"
        images_dir = mount / "images"
        image_dir = images_dir / "image1"
        image_dir.mkdir(parents=True)
        (image_dir / "parts").write_text("sda1")
        (image_dir / "sda-pt.parted").touch()

        device = {"mountpoint": str(mount)}
        result = find_image_repository(device)
        assert result == images_dir

    def test_find_image_repository_in_root(self, tmp_path):
        """Test finding repository in mount root."""
        mount = tmp_path / "mount"
        image_dir = mount / "image1"
        image_dir.mkdir(parents=True)
        (image_dir / "parts").write_text("sda1")
        (image_dir / "sda-pt.parted").touch()

        device = {"mountpoint": str(mount)}
        result = find_image_repository(device)
        assert result == mount

    def test_find_image_repository_no_mountpoint(self):
        """Test when device has no mountpoint."""
        device = {"mountpoint": None}
        result = find_image_repository(device)
        assert result is None

    def test_find_image_repository_not_found(self, tmp_path):
        """Test when no repository is found."""
        mount = tmp_path / "mount"
        mount.mkdir()

        device = {"mountpoint": str(mount)}
        result = find_image_repository(device)
        assert result is None


class TestListClonezillaImageDirs:
    def test_list_image_dirs_multiple(self, tmp_path):
        """Test listing multiple image directories."""
        repo = tmp_path / "repo"
        repo.mkdir()

        for i in range(3):
            image_dir = repo / f"image{i}"
            image_dir.mkdir()
            (image_dir / "parts").write_text("sda1")
            (image_dir / "sda-pt.parted").touch()

        result = list_clonezilla_image_dirs(repo)
        assert len(result) == 3
        assert all(is_clonezilla_image_dir(d) for d in result)

    def test_list_image_dirs_sorted(self, tmp_path):
        """Test that directories are sorted by name."""
        repo = tmp_path / "repo"
        repo.mkdir()

        for name in ["zebra", "apple", "banana"]:
            image_dir = repo / name
            image_dir.mkdir()
            (image_dir / "parts").write_text("sda1")
            (image_dir / "sda-pt.parted").touch()

        result = list_clonezilla_image_dirs(repo)
        assert [d.name for d in result] == ["apple", "banana", "zebra"]

    def test_list_image_dirs_excludes_non_images(self, tmp_path):
        """Test that non-image directories are excluded."""
        repo = tmp_path / "repo"
        repo.mkdir()

        # Valid image
        image_dir = repo / "valid"
        image_dir.mkdir()
        (image_dir / "parts").write_text("sda1")
        (image_dir / "sda-pt.parted").touch()

        # Invalid directory
        invalid_dir = repo / "invalid"
        invalid_dir.mkdir()

        result = list_clonezilla_image_dirs(repo)
        assert len(result) == 1
        assert result[0].name == "valid"

    def test_list_image_dirs_empty_repo(self, tmp_path):
        """Test empty repository."""
        repo = tmp_path / "repo"
        repo.mkdir()

        result = list_clonezilla_image_dirs(repo)
        assert result == []

    def test_list_image_dirs_not_a_directory(self, tmp_path):
        """Test with non-directory path."""
        not_a_dir = tmp_path / "file.txt"
        not_a_dir.touch()

        result = list_clonezilla_image_dirs(not_a_dir)
        assert result == []


class TestLoadImage:
    def test_load_image_complete(self, tmp_path):
        """Test loading a complete image with all metadata."""
        image_dir = tmp_path / "test-image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("sda1 sda2 sda3")
        pt_file = image_dir / "sda-pt.parted"
        pt_file.touch()

        result = load_image(image_dir)

        assert isinstance(result, ClonezillaImage)
        assert result.name == "test-image"
        assert result.path == image_dir
        assert result.parts == ["sda1", "sda2", "sda3"]
        assert result.partition_table == pt_file

    def test_load_image_without_partition_table(self, tmp_path):
        """Test loading image without partition table."""
        image_dir = tmp_path / "simple-image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("sda1")

        result = load_image(image_dir)

        assert result.name == "simple-image"
        assert result.parts == ["sda1"]
        assert result.partition_table is None

    def test_load_image_parts_with_whitespace(self, tmp_path):
        """Test loading parts file with extra whitespace."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("  sda1  \n  sda2  \n\n  sda3  ")

        result = load_image(image_dir)
        assert result.parts == ["sda1", "sda2", "sda3"]

    def test_load_image_not_a_directory(self, tmp_path):
        """Test loading from non-directory path."""
        not_a_dir = tmp_path / "file.txt"
        not_a_dir.touch()

        with pytest.raises(RuntimeError, match="Image folder not found"):
            load_image(not_a_dir)

    def test_load_image_missing_parts_file(self, tmp_path):
        """Test loading image without parts file."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()

        with pytest.raises(RuntimeError, match="Clonezilla parts file missing"):
            load_image(image_dir)

    def test_load_image_empty_parts_file(self, tmp_path):
        """Test loading image with empty parts file."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("")

        with pytest.raises(RuntimeError, match="Clonezilla parts list empty"):
            load_image(image_dir)

    def test_load_image_parts_only_whitespace(self, tmp_path):
        """Test loading image with parts file containing only whitespace."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("   \n  \n  ")

        with pytest.raises(RuntimeError, match="Clonezilla parts list empty"):
            load_image(image_dir)


class TestGetPartcloneTool:
    @patch("shutil.which")
    def test_get_partclone_tool_ext4(self, mock_which):
        """Test finding partclone.ext4 tool."""
        mock_which.return_value = "/usr/sbin/partclone.ext4"
        result = get_partclone_tool("ext4")
        assert result == "/usr/sbin/partclone.ext4"
        mock_which.assert_called_once_with("partclone.ext4")

    @patch("shutil.which")
    def test_get_partclone_tool_ntfs(self, mock_which):
        """Test finding partclone.ntfs tool."""
        mock_which.return_value = "/usr/sbin/partclone.ntfs"
        result = get_partclone_tool("ntfs")
        assert result == "/usr/sbin/partclone.ntfs"
        mock_which.assert_called_once_with("partclone.ntfs")

    @patch("shutil.which")
    def test_get_partclone_tool_vfat(self, mock_which):
        """Test that vfat maps to partclone.fat."""
        mock_which.return_value = "/usr/sbin/partclone.fat"
        result = get_partclone_tool("vfat")
        assert result == "/usr/sbin/partclone.fat"
        mock_which.assert_called_once_with("partclone.fat")

    @patch("shutil.which")
    def test_get_partclone_tool_fat32(self, mock_which):
        """Test that fat32 maps to partclone.fat."""
        mock_which.return_value = "/usr/sbin/partclone.fat"
        result = get_partclone_tool("fat32")
        assert result == "/usr/sbin/partclone.fat"
        mock_which.assert_called_once_with("partclone.fat")

    @patch("shutil.which")
    def test_get_partclone_tool_unsupported_fstype(self, mock_which):
        """Test unsupported filesystem type."""
        result = get_partclone_tool("unsupported")
        assert result is None
        mock_which.assert_not_called()

    @patch("shutil.which")
    @patch("pathlib.Path.is_file")
    @patch("os.access")
    def test_get_partclone_tool_fallback_path(self, mock_access, mock_is_file, mock_which):
        """Test fallback to standard paths when which fails."""
        mock_which.return_value = None
        mock_is_file.return_value = True
        mock_access.return_value = True

        result = get_partclone_tool("ext4")
        assert result == "/usr/sbin/partclone.ext4"

    @patch("shutil.which")
    def test_get_partclone_tool_not_found(self, mock_which):
        """Test when tool is not found."""
        mock_which.return_value = None

        with patch("pathlib.Path.is_file") as mock_is_file:
            mock_is_file.return_value = False
            result = get_partclone_tool("ext4")
            assert result is None


class TestBuildPartitionRestoreOp:
    def test_build_partition_restore_op_partclone_compressed(self, tmp_path):
        """Test building restore op for compressed partclone image."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "sda1.ext4-ptcl-img.gz.aa").touch()

        result = build_partition_restore_op(image_dir, "sda1")

        assert isinstance(result, PartitionRestoreOp)
        assert result.partition == "sda1"
        assert result.tool == "partclone"
        assert result.fstype == "ext4"
        assert result.compressed is True
        assert len(result.image_files) == 1

    def test_build_partition_restore_op_dd(self, tmp_path):
        """Test building restore op for dd image."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "sda1.dd-dd-img.aa").touch()

        result = build_partition_restore_op(image_dir, "sda1")

        assert result.partition == "sda1"
        assert result.tool == "dd"
        assert result.fstype is None
        assert result.compressed is False

    def test_build_partition_restore_op_no_files(self, tmp_path):
        """Test when no image files are found."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()

        result = build_partition_restore_op(image_dir, "sda1")
        assert result is None

    def test_build_partition_restore_op_invalid_naming(self, tmp_path):
        """Test when files exist but don't match naming convention."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        # Create a file that matches the glob pattern for has_partition_image_files
        # but not find_image_files patterns
        (image_dir / "backup-sda1.unknown-img").touch()

        # This should raise an error since has_partition_image_files detects
        # a file but build_partition_restore_op can't parse it
        with pytest.raises(RuntimeError, match="does not match partclone/dd naming convention"):
            build_partition_restore_op(image_dir, "sda1")

    @patch("rpi_usb_cloner.storage.clonezilla.image_discovery.get_partclone_tool")
    def test_build_partition_restore_op_prefers_partclone(self, mock_get_tool, tmp_path):
        """Test that partclone is preferred over dd when both exist."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "sda1.ext4-ptcl-img.aa").touch()
        (image_dir / "sda1.dd-dd-img.aa").touch()

        mock_get_tool.return_value = "/usr/sbin/partclone.ext4"

        result = build_partition_restore_op(image_dir, "sda1")

        assert result.tool == "partclone"
        assert result.fstype == "ext4"


class TestParseClonezillaImage:
    def test_parse_clonezilla_image_simple(self, tmp_path):
        """Test parsing a simple Clonezilla image."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("sda1")
        (image_dir / "sda-pt.parted").write_text("partition table")
        (image_dir / "sda1.ext4-ptcl-img.aa").touch()

        with patch("rpi_usb_cloner.storage.clonezilla.partition_table.collect_disk_layout_ops") as mock_collect:
            mock_collect.return_value = []

            result = parse_clonezilla_image(image_dir)

            assert result.image_dir == image_dir
            assert result.parts == ["sda1"]
            assert len(result.partition_ops) == 1
            assert result.partition_ops[0].partition == "sda1"

    def test_parse_clonezilla_image_not_a_directory(self, tmp_path):
        """Test parsing non-directory path."""
        not_a_dir = tmp_path / "file.txt"
        not_a_dir.touch()

        with pytest.raises(RuntimeError, match="Image folder not found"):
            parse_clonezilla_image(not_a_dir)

    def test_parse_clonezilla_image_missing_parts(self, tmp_path):
        """Test parsing image without parts file."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()

        with pytest.raises(RuntimeError, match="Clonezilla parts file missing"):
            parse_clonezilla_image(image_dir)

    def test_parse_clonezilla_image_empty_parts(self, tmp_path):
        """Test parsing image with empty parts file."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("")

        with pytest.raises(RuntimeError, match="Clonezilla parts list empty"):
            parse_clonezilla_image(image_dir)

    def test_parse_clonezilla_image_missing_partition_data(self, tmp_path):
        """Test parsing when partition data is missing."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("sda1")
        # No image files created

        with patch("rpi_usb_cloner.storage.clonezilla.partition_table.collect_disk_layout_ops") as mock_collect:
            mock_collect.return_value = []

            with pytest.raises(RuntimeError, match="Image data missing for sda1"):
                parse_clonezilla_image(image_dir)

    def test_parse_clonezilla_image_multiple_partitions(self, tmp_path):
        """Test parsing image with multiple partitions."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "parts").write_text("sda1 sda2 sda3")
        (image_dir / "sda-pt.parted").touch()
        (image_dir / "sda1.ext4-ptcl-img.aa").touch()
        (image_dir / "sda2.ntfs-ptcl-img.aa").touch()
        (image_dir / "sda3.dd-dd-img.aa").touch()

        with patch("rpi_usb_cloner.storage.clonezilla.partition_table.collect_disk_layout_ops") as mock_collect:
            mock_collect.return_value = []

            result = parse_clonezilla_image(image_dir)

            assert len(result.parts) == 3
            assert len(result.partition_ops) == 3
            assert result.partition_ops[0].fstype == "ext4"
            assert result.partition_ops[1].fstype == "ntfs"
            assert result.partition_ops[2].tool == "dd"
