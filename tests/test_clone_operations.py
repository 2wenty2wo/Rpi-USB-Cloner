"""Tests for core cloning operations."""
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from rpi_usb_cloner.storage.clone.operations import (
    clone_dd,
    clone_device,
    clone_device_smart,
    clone_partclone,
    copy_partition_table,
)


class TestCopyPartitionTable:
    """Tests for copy_partition_table function."""

    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_command")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_copy_gpt_partition_table(self, mock_which, mock_run):
        """Test copying GPT partition table."""
        def which_side_effect(cmd):
            if cmd == "sfdisk":
                return "/usr/bin/sfdisk"
            if cmd == "sgdisk":
                return "/usr/bin/sgdisk"
            return None

        mock_which.side_effect = which_side_effect

        # sfdisk --dump output with GPT label
        sfdisk_output = """label: gpt
label-id: 12345678
device: /dev/sda
unit: sectors
"""
        mock_run.side_effect = [sfdisk_output, None]

        source = {"name": "sda"}
        target = {"name": "sdb"}

        copy_partition_table(source, target)

        # Verify sgdisk was called for GPT
        calls = mock_run.call_args_list
        assert len(calls) == 2
        assert "sgdisk" in calls[1][0][0][0]
        assert "--replicate=/dev/sdb" in calls[1][0][0]
        assert "--randomize-guids" in calls[1][0][0]

    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_command")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_copy_mbr_partition_table(self, mock_which, mock_run):
        """Test copying MBR/DOS partition table."""
        mock_which.return_value = "/usr/bin/sfdisk"

        # sfdisk --dump output with DOS label
        sfdisk_output = """label: dos
label-id: 0x12345678
device: /dev/sda
unit: sectors
"""
        mock_run.side_effect = [sfdisk_output, None]

        source = {"name": "sda"}
        target = {"name": "sdb"}

        copy_partition_table(source, target)

        # Verify sfdisk was called with input
        calls = mock_run.call_args_list
        assert len(calls) == 2
        assert calls[1][0][0] == ["/usr/bin/sfdisk", "/dev/sdb"]
        assert calls[1][1]["input_text"] == sfdisk_output

    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_command")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_copy_msdos_label(self, mock_which, mock_run):
        """Test copying partition table with 'msdos' label."""
        mock_which.return_value = "/usr/bin/sfdisk"

        sfdisk_output = "label: msdos\ndevice: /dev/sda\n"
        mock_run.side_effect = [sfdisk_output, None]

        copy_partition_table({"name": "sda"}, {"name": "sdb"})

        # Should be treated as DOS/MBR
        calls = mock_run.call_args_list
        assert len(calls) == 2

    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_copy_partition_table_no_sfdisk(self, mock_which):
        """Test error when sfdisk is not found."""
        mock_which.return_value = None

        with pytest.raises(RuntimeError, match="sfdisk not found"):
            copy_partition_table({"name": "sda"}, {"name": "sdb"})

    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_command")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_copy_partition_table_no_sgdisk_for_gpt(self, mock_which, mock_run):
        """Test error when sgdisk is not found for GPT."""
        def which_side_effect(cmd):
            if cmd == "sfdisk":
                return "/usr/bin/sfdisk"
            return None  # sgdisk not found

        mock_which.side_effect = which_side_effect
        mock_run.return_value = "label: gpt\ndevice: /dev/sda\n"

        with pytest.raises(RuntimeError, match="sgdisk not found"):
            copy_partition_table({"name": "sda"}, {"name": "sdb"})

    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_command")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_copy_partition_table_no_label(self, mock_which, mock_run):
        """Test error when partition table label cannot be detected."""
        mock_which.return_value = "/usr/bin/sfdisk"
        mock_run.return_value = "device: /dev/sda\nunit: sectors\n"  # No label line

        with pytest.raises(RuntimeError, match="Unable to detect partition table label"):
            copy_partition_table({"name": "sda"}, {"name": "sdb"})

    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_command")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_copy_partition_table_unsupported_label(self, mock_which, mock_run):
        """Test error with unsupported partition table type."""
        mock_which.return_value = "/usr/bin/sfdisk"
        mock_run.return_value = "label: sun\ndevice: /dev/sda\n"  # Sun label

        with pytest.raises(RuntimeError, match="Unsupported partition table label"):
            copy_partition_table({"name": "sda"}, {"name": "sdb"})

    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_command")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_copy_partition_table_with_string_paths(self, mock_which, mock_run):
        """Test copying partition table with string device paths."""
        mock_which.return_value = "/usr/bin/sfdisk"
        mock_run.side_effect = ["label: dos\n", None]

        copy_partition_table("/dev/sda", "/dev/sdb")

        # Should work with string paths
        calls = mock_run.call_args_list
        assert len(calls) == 2


class TestCloneDd:
    """Tests for clone_dd function."""

    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_with_streaming_progress")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_clone_dd_success(self, mock_which, mock_run):
        """Test successful dd cloning."""
        mock_which.return_value = "/usr/bin/dd"
        mock_run.return_value = Mock()

        source = {"name": "sda"}
        target = {"name": "sdb"}

        clone_dd(source, target, total_bytes=100000000)

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "/usr/bin/dd" in call_args[0][0]
        assert "if=/dev/sda" in call_args[0][0]
        assert "of=/dev/sdb" in call_args[0][0]
        assert "bs=4M" in call_args[0][0]
        assert "status=progress" in call_args[0][0]
        assert "conv=fsync" in call_args[0][0]

    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_clone_dd_no_dd(self, mock_which):
        """Test error when dd is not found."""
        mock_which.return_value = None

        with pytest.raises(RuntimeError, match="dd not found"):
            clone_dd({"name": "sda"}, {"name": "sdb"})

    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_with_streaming_progress")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_clone_dd_with_title_and_subtitle(self, mock_which, mock_run):
        """Test dd cloning with custom title and subtitle."""
        mock_which.return_value = "/usr/bin/dd"
        mock_run.return_value = Mock()

        clone_dd("/dev/sda", "/dev/sdb", title="TEST CLONE", subtitle="Custom subtitle")

        call_args = mock_run.call_args
        assert call_args[1]["title"] == "TEST CLONE"
        assert call_args[1]["subtitle"] == "Custom subtitle"


class TestClonePartclone:
    """Tests for clone_partclone function."""

    @pytest.fixture
    def mock_devices_with_partitions(self):
        """Create mock devices with partitions."""
        source = {
            "name": "sda",
            "size": 32000000000,
        }
        target = {
            "name": "sdb",
            "size": 32000000000,
        }
        source_parts = [
            {"name": "sda1", "type": "part", "fstype": "ext4", "size": 10000000000},
            {"name": "sda2", "type": "part", "fstype": "vfat", "size": 5000000000},
        ]
        target_parts = [
            {"name": "sdb1", "type": "part", "fstype": "", "size": 10000000000},
            {"name": "sdb2", "type": "part", "fstype": "", "size": 5000000000},
        ]
        return source, target, source_parts, target_parts

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_with_streaming_progress")
    @patch("rpi_usb_cloner.storage.clone.operations.get_children")
    @patch("rpi_usb_cloner.storage.clone.operations.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    @patch("builtins.open", new_callable=MagicMock)
    def test_clone_partclone_ext4(self, mock_open, mock_which, mock_get_device, mock_get_children, mock_run, mock_display, mock_devices_with_partitions):
        """Test partclone with ext4 filesystem."""
        source, target, source_parts, target_parts = mock_devices_with_partitions

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]
        mock_which.return_value = "/usr/bin/partclone.ext4"
        mock_run.return_value = Mock()

        clone_partclone(source, target)

        # Should call partclone for both partitions
        assert mock_run.call_count == 2

        # Check first partition (ext4)
        first_call = mock_run.call_args_list[0]
        assert "partclone.ext4" in first_call[0][0][0]
        assert "-s" in first_call[0][0]
        assert "/dev/sda1" in first_call[0][0]

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_with_streaming_progress")
    @patch("rpi_usb_cloner.storage.clone.operations.get_children")
    @patch("rpi_usb_cloner.storage.clone.operations.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    @patch("builtins.open", new_callable=MagicMock)
    def test_clone_partclone_vfat(self, mock_open, mock_which, mock_get_device, mock_get_children, mock_run, mock_display, mock_devices_with_partitions):
        """Test partclone with FAT filesystem."""
        source, target, source_parts, target_parts = mock_devices_with_partitions

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]

        def which_side_effect(tool):
            if tool == "partclone.ext4":
                return "/usr/bin/partclone.ext4"
            if tool == "partclone.fat":
                return "/usr/bin/partclone.fat"
            return None

        mock_which.side_effect = which_side_effect
        mock_run.return_value = Mock()

        clone_partclone(source, target)

        # Check second partition (vfat -> partclone.fat)
        second_call = mock_run.call_args_list[1]
        assert "partclone.fat" in second_call[0][0][0]

    @patch("rpi_usb_cloner.storage.clone.operations.clone_dd")
    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.get_children")
    @patch("rpi_usb_cloner.storage.clone.operations.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    def test_clone_partclone_unsupported_fs_falls_back_to_dd(self, mock_which, mock_get_device, mock_get_children, mock_display, mock_dd):
        """Test partclone falls back to dd for unsupported filesystems."""
        source = {"name": "sda", "size": 32000000000}
        target = {"name": "sdb", "size": 32000000000}
        source_parts = [
            {"name": "sda1", "type": "part", "fstype": "zfs", "size": 10000000000},
        ]
        target_parts = [
            {"name": "sdb1", "type": "part", "size": 10000000000},
        ]

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]
        mock_which.return_value = None  # No partclone tool available

        clone_partclone(source, target)

        # Should fall back to dd
        mock_dd.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.operations.clone_dd")
    @patch("rpi_usb_cloner.storage.clone.operations.get_children")
    @patch("rpi_usb_cloner.storage.clone.operations.get_device_by_name")
    def test_clone_partclone_no_partitions(self, mock_get_device, mock_get_children, mock_dd):
        """Test partclone falls back to dd when no partitions exist."""
        source = {"name": "sda", "size": 32000000000}
        target = {"name": "sdb", "size": 32000000000}

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [[], []]  # No partitions

        clone_partclone(source, target)

        # Should fall back to whole-device dd
        mock_dd.assert_called_once_with("/dev/sda", "/dev/sdb", total_bytes=32000000000)

    @patch("rpi_usb_cloner.storage.clone.operations.clone_dd")
    @patch("rpi_usb_cloner.storage.clone.operations.get_device_by_name")
    def test_clone_partclone_device_not_found(self, mock_get_device, mock_dd):
        """Test partclone falls back to dd when device info not available."""
        mock_get_device.return_value = None

        clone_partclone("/dev/sda", "/dev/sdb")

        # Should fall back to dd
        mock_dd.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.get_children")
    @patch("rpi_usb_cloner.storage.clone.operations.get_device_by_name")
    def test_clone_partclone_missing_target_partition(self, mock_get_device, mock_get_children, mock_display):
        """Test error when target partition is missing."""
        source = {"name": "sda", "size": 32000000000}
        target = {"name": "sdb", "size": 32000000000}
        source_parts = [
            {"name": "sda1", "type": "part", "fstype": "ext4", "size": 10000000000},
            {"name": "sda2", "type": "part", "fstype": "ext4", "size": 20000000000},
        ]
        target_parts = [
            {"name": "sdb1", "type": "part", "size": 10000000000},
            # Missing sdb2
        ]

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]

        with pytest.raises(RuntimeError, match="Unable to map"):
            clone_partclone(source, target)


class TestCloneDeviceSmart:
    """Tests for clone_device_smart function."""

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_partclone")
    @patch("rpi_usb_cloner.storage.clone.operations.copy_partition_table")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    def test_clone_device_smart_success(self, mock_unmount, mock_copy_table, mock_clone_partclone, mock_display):
        """Test successful smart clone."""
        source = {"name": "sda", "size": 32000000000}
        target = {"name": "sdb", "size": 32000000000}

        result = clone_device_smart(source, target)

        assert result is True
        mock_unmount.assert_called_once_with(target)
        mock_copy_table.assert_called_once()
        mock_clone_partclone.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.copy_partition_table")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    def test_clone_device_smart_partition_table_failure(self, mock_unmount, mock_copy_table, mock_display):
        """Test smart clone fails when partition table copy fails."""
        source = {"name": "sda", "size": 32000000000}
        target = {"name": "sdb", "size": 32000000000}

        mock_copy_table.side_effect = RuntimeError("Partition table error")

        result = clone_device_smart(source, target)

        assert result is False
        # Should display error
        error_calls = [c for c in mock_display.call_args_list if "FAILED" in str(c)]
        assert len(error_calls) > 0

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_partclone")
    @patch("rpi_usb_cloner.storage.clone.operations.copy_partition_table")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    def test_clone_device_smart_partclone_failure(self, mock_unmount, mock_copy_table, mock_clone_partclone, mock_display):
        """Test smart clone fails when partclone fails."""
        source = {"name": "sda", "size": 32000000000}
        target = {"name": "sdb", "size": 32000000000}

        mock_clone_partclone.side_effect = RuntimeError("Partclone error")

        result = clone_device_smart(source, target)

        assert result is False


class TestCloneDevice:
    """Tests for clone_device function."""

    @patch("rpi_usb_cloner.storage.clone.operations.clone_device_smart")
    def test_clone_device_smart_mode(self, mock_smart):
        """Test clone_device with smart mode."""
        mock_smart.return_value = True

        source = {"name": "sda", "size": 32000000000}
        target = {"name": "sdb", "size": 32000000000}

        result = clone_device(source, target, mode="smart")

        assert result is True
        mock_smart.assert_called_once_with(source, target)

    @patch("rpi_usb_cloner.storage.clone.operations.clone_device_smart")
    @patch("rpi_usb_cloner.storage.clone.operations.verify_clone")
    def test_clone_device_verify_mode(self, mock_verify, mock_smart):
        """Test clone_device with verify mode."""
        mock_smart.return_value = True
        mock_verify.return_value = True

        source = {"name": "sda", "size": 32000000000}
        target = {"name": "sdb", "size": 32000000000}

        result = clone_device(source, target, mode="verify")

        assert result is True
        mock_smart.assert_called_once()
        mock_verify.assert_called_once_with(source, target)

    @patch("rpi_usb_cloner.storage.clone.operations.clone_device_smart")
    @patch("rpi_usb_cloner.storage.clone.operations.verify_clone")
    def test_clone_device_verify_mode_verification_fails(self, mock_verify, mock_smart):
        """Test verify mode returns False when verification fails."""
        mock_smart.return_value = True
        mock_verify.return_value = False

        result = clone_device({"name": "sda"}, {"name": "sdb"}, mode="verify")

        assert result is False

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_dd")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    def test_clone_device_exact_mode(self, mock_unmount, mock_dd, mock_display):
        """Test clone_device with exact/raw mode."""
        source = {"name": "sda", "size": 32000000000}
        target = {"name": "sdb", "size": 32000000000}

        result = clone_device(source, target, mode="exact")

        assert result is True
        mock_unmount.assert_called_once_with(target)
        mock_dd.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_dd")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    def test_clone_device_raw_mode_alias(self, mock_unmount, mock_dd, mock_display):
        """Test clone_device with 'raw' mode (alias for exact)."""
        source = {"name": "sda", "size": 32000000000}
        target = {"name": "sdb", "size": 32000000000}

        result = clone_device(source, target, mode="raw")

        assert result is True
        mock_dd.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.operations.clone_device_smart")
    def test_clone_device_none_mode_defaults_to_smart(self, mock_smart):
        """Test None mode defaults to smart."""
        mock_smart.return_value = True

        result = clone_device({"name": "sda"}, {"name": "sdb"}, mode=None)

        assert result is True
        mock_smart.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.operations.clone_device_smart")
    def test_clone_device_env_var_mode(self, mock_smart):
        """Test clone mode from environment variable."""
        mock_smart.return_value = True

        with patch.dict("os.environ", {"CLONE_MODE": "smart"}):
            result = clone_device({"name": "sda"}, {"name": "sdb"})

        assert result is True

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_dd")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    def test_clone_device_exact_mode_failure(self, mock_unmount, mock_dd, mock_display):
        """Test exact mode handles dd failure."""
        mock_dd.side_effect = RuntimeError("dd failed")

        source = {"name": "sda", "size": 32000000000}
        target = {"name": "sdb", "size": 32000000000}

        result = clone_device(source, target, mode="exact")

        assert result is False
        # Should display error
        error_calls = [c for c in mock_display.call_args_list if "FAILED" in str(c)]
        assert len(error_calls) > 0

    @patch("rpi_usb_cloner.storage.clone.operations.clone_device_smart")
    def test_clone_device_smart_mode_failure(self, mock_smart):
        """Test smart mode returns False on failure."""
        mock_smart.return_value = False

        result = clone_device({"name": "sda"}, {"name": "sdb"}, mode="smart")

        assert result is False
