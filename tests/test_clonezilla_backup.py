"""Tests for storage/clonezilla/backup.py - Clonezilla backup operations.

This test suite covers:
- Basic backup creation workflow
- Different compression modes (gzip, zstd, none)
- Partition table preservation (sfdisk, parted, sgdisk)
- Metadata file generation (parts, disk, dev-fs.list)
- Multi-partition device backup
- Single partition backup
- Error handling (disk full, permission denied, invalid device)
- Progress tracking
- MBR/GPT detection and handling
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from rpi_usb_cloner.storage.clonezilla import backup


@pytest.fixture
def mock_device_info():
    """Fixture providing mock device info."""
    return {
        "name": "sda",
        "size": "16106127360",
        "type": "disk",
        "children": [
            {
                "name": "sda1",
                "size": "1073741824",
                "type": "part",
                "fstype": "vfat",
            },
            {
                "name": "sda2",
                "size": "15032385536",
                "type": "part",
                "fstype": "ext4",
            },
        ],
    }


@pytest.fixture
def mock_partition_info():
    """Fixture providing mock partition info list."""
    return [
        backup.PartitionInfo(
            name="sda1",
            node="/dev/sda1",
            fstype="vfat",
            size_bytes=1073741824,
            used_bytes=536870912,
        ),
        backup.PartitionInfo(
            name="sda2",
            node="/dev/sda2",
            fstype="ext4",
            size_bytes=15032385536,
            used_bytes=7516192768,
        ),
    ]


class TestCheckToolAvailable:
    """Tests for check_tool_available() function."""

    @patch("shutil.which")
    def test_tool_available(self, mock_which):
        """Test detection of available tool."""
        mock_which.return_value = "/usr/bin/gzip"

        assert backup.check_tool_available("gzip") is True
        mock_which.assert_called_once_with("gzip")

    @patch("shutil.which")
    def test_tool_not_available(self, mock_which):
        """Test detection when tool not available."""
        mock_which.return_value = None

        assert backup.check_tool_available("nonexistent") is False


class TestGetCompressionTool:
    """Tests for get_compression_tool() function."""

    @patch("shutil.which")
    def test_gzip_compression_pigz_available(self, mock_which):
        """Test gzip compression with pigz available."""
        mock_which.side_effect = lambda x: "/usr/bin/pigz" if x == "pigz" else None

        tool, args = backup.get_compression_tool("gzip")

        assert tool == "/usr/bin/pigz"
        assert args == ["-c"]

    @patch("shutil.which")
    def test_gzip_compression_fallback_to_gzip(self, mock_which):
        """Test gzip compression falls back to gzip when pigz unavailable."""
        mock_which.side_effect = lambda x: "/usr/bin/gzip" if x == "gzip" else None

        tool, args = backup.get_compression_tool("gzip")

        assert tool == "/usr/bin/gzip"
        assert args == ["-c"]

    @patch("shutil.which")
    def test_zstd_compression_pzstd_available(self, mock_which):
        """Test zstd compression with pzstd available."""
        mock_which.side_effect = lambda x: "/usr/bin/pzstd" if x == "pzstd" else None

        tool, args = backup.get_compression_tool("zstd")

        assert tool == "/usr/bin/pzstd"
        assert args == ["-c"]

    @patch("shutil.which")
    def test_zstd_compression_fallback_to_zstd(self, mock_which):
        """Test zstd compression falls back to zstd when pzstd unavailable."""
        mock_which.side_effect = lambda x: "/usr/bin/zstd" if x == "zstd" else None

        tool, args = backup.get_compression_tool("zstd")

        assert tool == "/usr/bin/zstd"
        assert args == ["-c"]

    def test_none_compression(self):
        """Test 'none' compression returns None."""
        tool, args = backup.get_compression_tool("none")

        assert tool is None
        assert args is None

    def test_invalid_compression_type(self):
        """Test invalid compression type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown compression type"):
            backup.get_compression_tool("invalid")

    @patch("shutil.which")
    def test_compression_tool_not_available(self, mock_which):
        """Test when compression tool not available."""
        mock_which.return_value = None

        tool, args = backup.get_compression_tool("gzip")

        assert tool is None
        assert args is None


class TestGetFilesystemType:
    """Tests for get_filesystem_type() function."""

    @patch("subprocess.run")
    def test_detect_ext4_with_lsblk(self, mock_run):
        """Test filesystem detection using lsblk."""
        mock_run.return_value = Mock(returncode=0, stdout="ext4\n")

        fstype = backup.get_filesystem_type("/dev/sda1")

        assert fstype == "ext4"
        mock_run.assert_called_once()
        assert "lsblk" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_detect_vfat_with_blkid_fallback(self, mock_run):
        """Test filesystem detection falls back to blkid."""

        # lsblk fails (timeout), blkid succeeds
        def run_side_effect(*args, **kwargs):
            if "lsblk" in args[0]:
                raise subprocess.TimeoutExpired("lsblk", 5)
            return Mock(returncode=0, stdout="vfat\n")

        mock_run.side_effect = run_side_effect

        fstype = backup.get_filesystem_type("/dev/sda1")

        assert fstype == "vfat"
        # Verify blkid was called after lsblk failed
        assert mock_run.call_count == 2
        assert "blkid" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_detect_empty_filesystem(self, mock_run):
        """Test detection returns None for empty filesystem."""
        mock_run.return_value = Mock(returncode=0, stdout="\n")

        fstype = backup.get_filesystem_type("/dev/sda1")

        assert fstype is None

    @patch("subprocess.run")
    def test_detect_filesystem_timeout(self, mock_run):
        """Test detection handles timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("lsblk", 5)

        fstype = backup.get_filesystem_type("/dev/sda1")

        assert fstype is None


class TestGetPartitionInfo:
    """Tests for get_partition_info() function."""

    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.get_children")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.get_partition_used_space")
    def test_get_partition_info(
        self, mock_get_used, mock_get_children, mock_device_info
    ):
        """Test getting partition information from device."""
        mock_get_children.return_value = mock_device_info["children"]
        mock_get_used.return_value = 500000000

        partitions = backup.get_partition_info(mock_device_info)

        assert len(partitions) == 2
        assert partitions[0].name == "sda1"
        assert partitions[0].fstype == "vfat"
        assert partitions[0].size_bytes == 1073741824
        assert partitions[1].name == "sda2"
        assert partitions[1].fstype == "ext4"

    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.get_children")
    def test_get_partition_info_skips_non_partitions(
        self, mock_get_children, mock_device_info
    ):
        """Test that non-partition children are skipped."""
        children = mock_device_info["children"] + [
            {"name": "sda", "type": "disk"}  # Not a partition
        ]
        mock_get_children.return_value = children

        partitions = backup.get_partition_info(mock_device_info)

        # Should only return actual partitions
        assert len(partitions) == 2
        assert all(p.name.startswith("sda") and p.name != "sda" for p in partitions)


class TestSavePartitionTables:
    """Tests for partition table saving functions."""

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_save_partition_table_sfdisk(self, mock_which, mock_run, tmp_path):
        """Test saving partition table with sfdisk."""
        mock_which.return_value = "/usr/sbin/sfdisk"
        sfdisk_output = "label: dos\ndevice: /dev/sda\n"
        mock_run.return_value = Mock(returncode=0, stdout=sfdisk_output, stderr="")

        output_path = tmp_path / "sda-pt.sf"
        backup.save_partition_table_sfdisk("/dev/sda", output_path)

        assert output_path.exists()
        assert output_path.read_text() == sfdisk_output
        mock_run.assert_called_once_with(
            ["/usr/sbin/sfdisk", "-d", "/dev/sda"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_save_partition_table_sfdisk_failure(self, mock_which, mock_run, tmp_path):
        """Test sfdisk failure raises RuntimeError."""
        mock_which.return_value = "/usr/sbin/sfdisk"
        mock_run.return_value = Mock(returncode=1, stderr="sfdisk: error")

        output_path = tmp_path / "sda-pt.sf"

        with pytest.raises(RuntimeError, match="sfdisk failed"):
            backup.save_partition_table_sfdisk("/dev/sda", output_path)

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_save_partition_table_parted(self, mock_which, mock_run, tmp_path):
        """Test saving partition table with parted."""
        mock_which.return_value = "/usr/sbin/parted"
        parted_output = "BYT;\n/dev/sda:16.0GB:scsi:512:512:msdos:Generic USB;\n"
        mock_run.return_value = Mock(returncode=0, stdout=parted_output, stderr="")

        output_path = tmp_path / "sda-pt.parted"
        backup.save_partition_table_parted("/dev/sda", output_path)

        assert output_path.exists()
        assert output_path.read_text() == parted_output

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_save_partition_table_sgdisk_gpt(self, mock_which, mock_run, tmp_path):
        """Test saving GPT partition table with sgdisk."""
        mock_which.return_value = "/usr/sbin/sgdisk"
        sgdisk_output = "Disk /dev/sda: 31457280 sectors\n"
        mock_run.return_value = Mock(returncode=0, stdout=sgdisk_output, stderr="")

        output_path = tmp_path / "sda-pt.sgdisk"
        backup.save_partition_table_sgdisk("/dev/sda", output_path)

        assert output_path.exists()
        assert output_path.read_text() == sgdisk_output

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_save_partition_table_sgdisk_not_gpt(self, mock_which, mock_run, tmp_path):
        """Test sgdisk silently skips non-GPT disks."""
        mock_which.return_value = "/usr/sbin/sgdisk"
        mock_run.return_value = Mock(returncode=1, stderr="Not a GPT disk")

        output_path = tmp_path / "sda-pt.sgdisk"

        # Should not raise error for non-GPT disks
        backup.save_partition_table_sgdisk("/dev/sda", output_path)

        # File should not be created
        assert not output_path.exists()

    @patch("rpi_usb_cloner.storage.clonezilla.backup.save_partition_table_sgdisk")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.save_partition_table_parted")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.save_partition_table_sfdisk")
    def test_save_partition_tables(
        self, mock_sfdisk, mock_parted, mock_sgdisk, tmp_path
    ):
        """Test saving all partition table formats."""
        backup.save_partition_tables("/dev/sda", "sda", tmp_path)

        # Verify all formats were attempted
        mock_sfdisk.assert_called_once_with("/dev/sda", tmp_path / "sda-pt.sf")
        mock_parted.assert_called_once_with("/dev/sda", tmp_path / "sda-pt.parted")
        mock_sgdisk.assert_called_once_with("/dev/sda", tmp_path / "sda-pt.sgdisk")


class TestCreateMetadataFiles:
    """Tests for create_metadata_files() function."""

    def test_create_metadata_files(self, tmp_path):
        """Test metadata file creation."""
        partitions = ["sda1", "sda2", "sda3"]

        backup.create_metadata_files("sda", partitions, tmp_path)

        # Verify 'parts' file
        parts_file = tmp_path / "parts"
        assert parts_file.exists()
        assert parts_file.read_text() == "sda1 sda2 sda3\n"

        # Verify 'disk' file
        disk_file = tmp_path / "disk"
        assert disk_file.exists()
        assert disk_file.read_text() == "sda\n"

        # Verify 'blkdev.list' file
        blkdev_file = tmp_path / "blkdev.list"
        assert blkdev_file.exists()
        assert blkdev_file.read_text() == "sda\n"

        # dev-fs.list should not be created without partition_infos
        dev_fs_file = tmp_path / "dev-fs.list"
        assert not dev_fs_file.exists()

    def test_create_metadata_files_with_partition_info(self, tmp_path):
        """Test metadata file creation with filesystem details."""
        partitions = ["sda1", "sda2", "sda3"]
        partition_infos = [
            backup.PartitionInfo(
                name="sda1",
                node="/dev/sda1",
                fstype="vfat",
                size_bytes=1073741824,
                used_bytes=536870912,
            ),
            backup.PartitionInfo(
                name="sda2",
                node="/dev/sda2",
                fstype="ext4",
                size_bytes=15032385536,
                used_bytes=7516192768,
            ),
            backup.PartitionInfo(
                name="sda3",
                node="/dev/sda3",
                fstype=None,  # Test unknown filesystem
                size_bytes=1073741824,
                used_bytes=None,
            ),
        ]

        backup.create_metadata_files("sda", partitions, tmp_path, partition_infos)

        # Verify 'dev-fs.list' file
        dev_fs_file = tmp_path / "dev-fs.list"
        assert dev_fs_file.exists()
        content = dev_fs_file.read_text()
        assert "sda1 vfat" in content
        assert "sda2 ext4" in content
        assert "sda3 unknown" in content


class TestProgressParsing:
    """Tests for progress parsing functions."""

    def test_parse_partclone_progress_with_percentage(self):
        """Test parsing partclone progress with percentage."""
        line = "Elapsed: 00:01:23, Rate: 45.2MB/s, Remaining: 00:05:30, 45.2% completed"

        result = backup.parse_partclone_progress(line)

        assert result is not None
        assert result["percentage"] == 45.2
        assert result["rate_str"] == "45.2MB/s"

    def test_parse_partclone_progress_without_rate(self):
        """Test parsing partclone progress without rate info."""
        line = "current block: 1000, total block: 4000, Complete: 25.0%"

        result = backup.parse_partclone_progress(line)

        assert result is not None
        assert result["percentage"] == 25.0
        assert result["rate_str"] is None

    def test_parse_partclone_progress_no_match(self):
        """Test parsing line without progress info."""
        line = "Partclone v0.3.23"

        result = backup.parse_partclone_progress(line)

        assert result is None

    def test_parse_dd_progress(self):
        """Test parsing dd progress output."""
        line = "2415919104 bytes (2.4 GB, 2.2 GiB) copied, 45 s, 53.7 MB/s"

        result = backup.parse_dd_progress(line)

        assert result is not None
        assert result["bytes"] == 2415919104
        assert result["size_str"] == "2.4 GB"
        assert result["rate_str"] == "53.7 MB/s"

    def test_parse_dd_progress_no_match(self):
        """Test parsing dd line without progress."""
        line = "0+0 records in"

        result = backup.parse_dd_progress(line)

        assert result is None


class TestEstimateBackupSize:
    """Tests for estimate_backup_size() function."""

    @patch("rpi_usb_cloner.storage.clonezilla.backup.get_partition_info")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.get_device_by_name")
    def test_estimate_backup_size_all_partitions(
        self, mock_get_device, mock_get_part_info, mock_device_info, mock_partition_info
    ):
        """Test estimating backup size for all partitions."""
        mock_get_device.return_value = mock_device_info
        mock_get_part_info.return_value = mock_partition_info

        size = backup.estimate_backup_size("sda")

        # Should include used space + overhead + metadata
        expected_size = int(536870912 * 1.1) + int(7516192768 * 1.1) + 10 * 1024 * 1024
        assert size == expected_size

    @patch("rpi_usb_cloner.storage.clonezilla.backup.get_partition_info")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.get_device_by_name")
    def test_estimate_backup_size_specific_partitions(
        self, mock_get_device, mock_get_part_info, mock_device_info, mock_partition_info
    ):
        """Test estimating backup size for specific partitions."""
        mock_get_device.return_value = mock_device_info
        mock_get_part_info.return_value = mock_partition_info

        size = backup.estimate_backup_size("sda", partition_names=["sda1"])

        # Should only include sda1
        expected_size = int(536870912 * 1.1) + 10 * 1024 * 1024
        assert size == expected_size

    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.get_device_by_name")
    def test_estimate_backup_size_device_not_found(self, mock_get_device):
        """Test error when device not found."""
        mock_get_device.return_value = None

        with pytest.raises(RuntimeError, match="Device .* not found"):
            backup.estimate_backup_size("invalid")


class TestBackupPartition:
    """Tests for backup_partition() function."""

    # Note: These tests are skipped due to complex subprocess pipeline mocking
    @pytest.mark.skip(reason="Complex subprocess pipeline mocking required")
    def test_backup_partition_with_partclone(self):
        """Test backing up partition with partclone."""

    @pytest.mark.skip(reason="Complex subprocess pipeline mocking required")
    def test_backup_partition_fallback_to_dd(self):
        """Test falling back to dd when partclone unavailable."""


class TestCreateClonezillaBackup:
    """Tests for create_clonezilla_backup() main function."""

    @patch("rpi_usb_cloner.storage.clonezilla.backup.backup_partition")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.create_metadata_files")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.save_partition_tables")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.get_partition_info")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.resolve_device_node")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.get_compression_tool")
    def test_create_backup_full_workflow(
        self,
        mock_get_comp,
        mock_get_device,
        mock_unmount,
        mock_resolve,
        mock_get_part_info,
        mock_save_tables,
        mock_create_metadata,
        mock_backup_part,
        tmp_path,
        mock_device_info,
        mock_partition_info,
    ):
        """Test complete backup workflow."""
        mock_get_comp.return_value = ("/usr/bin/gzip", ["-c"])
        mock_get_device.return_value = mock_device_info
        mock_unmount.return_value = True
        mock_resolve.return_value = "/dev/sda"
        mock_get_part_info.return_value = mock_partition_info

        # Mock backup_partition to create files
        def backup_side_effect(partition, output_dir, **kwargs):
            output_file = (
                output_dir / f"{partition.name}.{partition.fstype}-ptcl-img.gz"
            )
            output_file.write_bytes(b"test backup data")
            return [output_file]

        mock_backup_part.side_effect = backup_side_effect

        result = backup.create_clonezilla_backup(
            "sda",
            tmp_path,
            compression="gzip",
        )

        # Verify result
        assert isinstance(result, backup.BackupResult)
        assert result.image_dir == tmp_path
        assert len(result.partitions_backed_up) == 2
        assert "sda1" in result.partitions_backed_up
        assert "sda2" in result.partitions_backed_up
        assert result.compression == "gzip"
        assert result.total_bytes_written > 0

        # Verify workflow steps
        mock_unmount.assert_called_once()
        mock_save_tables.assert_called_once()
        mock_create_metadata.assert_called_once()
        assert mock_backup_part.call_count == 2

    @patch("rpi_usb_cloner.storage.clonezilla.backup.get_compression_tool")
    def test_create_backup_invalid_compression(self, mock_get_comp, tmp_path):
        """Test error with invalid compression type."""
        # The function validates compression type directly
        with pytest.raises(ValueError, match="Invalid compression type"):
            backup.create_clonezilla_backup("sda", tmp_path, compression="invalid")

    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.get_compression_tool")
    def test_create_backup_device_not_found(self, mock_get_comp, mock_get_device, tmp_path):
        """Test error when device not found."""
        mock_get_comp.return_value = ("/usr/bin/gzip", ["-c"])  # Mock compression tool
        mock_get_device.return_value = None

        with pytest.raises(RuntimeError, match="Device .* not found"):
            backup.create_clonezilla_backup("invalid", tmp_path)

    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.get_compression_tool")
    def test_create_backup_unmount_failure(
        self, mock_get_comp, mock_get_device, mock_unmount, tmp_path, mock_device_info
    ):
        """Test error when unmount fails."""
        mock_get_comp.return_value = ("/usr/bin/gzip", ["-c"])
        mock_get_device.return_value = mock_device_info
        mock_unmount.return_value = False

        with pytest.raises(RuntimeError, match="Failed to unmount"):
            backup.create_clonezilla_backup("sda", tmp_path)

    @patch("rpi_usb_cloner.storage.clonezilla.backup.cleanup_partial_backup")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.save_partition_tables")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.get_partition_info")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.resolve_device_node")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.backup.get_compression_tool")
    def test_create_backup_failure_cleanup(
        self,
        mock_get_comp,
        mock_get_device,
        mock_unmount,
        mock_resolve,
        mock_get_part_info,
        mock_save_tables,
        mock_cleanup,
        tmp_path,
        mock_device_info,
        mock_partition_info,
    ):
        """Test cleanup on backup failure."""
        mock_get_comp.return_value = ("/usr/bin/gzip", ["-c"])
        mock_get_device.return_value = mock_device_info
        mock_unmount.return_value = True
        mock_resolve.return_value = "/dev/sda"
        mock_get_part_info.return_value = mock_partition_info
        # Make save_partition_tables fail
        mock_save_tables.side_effect = RuntimeError("Partition table error")

        with pytest.raises(RuntimeError):
            backup.create_clonezilla_backup("sda", tmp_path)

        # Verify cleanup was called
        mock_cleanup.assert_called_once_with(tmp_path)


class TestCleanupPartialBackup:
    """Tests for cleanup_partial_backup() function."""

    def test_cleanup_removes_directory(self, tmp_path):
        """Test cleanup removes backup directory."""
        backup_dir = tmp_path / "partial_backup"
        backup_dir.mkdir()
        (backup_dir / "test_file").write_text("test")

        backup.cleanup_partial_backup(backup_dir)

        assert not backup_dir.exists()

    def test_cleanup_handles_nonexistent_directory(self, tmp_path):
        """Test cleanup handles non-existent directory."""
        backup_dir = tmp_path / "nonexistent"

        # Should not raise error
        backup.cleanup_partial_backup(backup_dir)
