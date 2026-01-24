"""
Tests for rpi_usb_cloner.storage.clone module.

This test suite covers:
- Clone mode normalization and validation
- Device node resolution
- Partition table copying (GPT and MBR)
- Progress display formatting
- ETA calculation
- Filesystem type formatting
- Partition naming
"""

from unittest.mock import Mock

import pytest

from rpi_usb_cloner.storage import clone


class TestNormalizeCloneMode:
    """Tests for normalize_clone_mode() function."""

    def test_smart_mode(self):
        assert clone.normalize_clone_mode("smart") == "smart"

    def test_exact_mode(self):
        assert clone.normalize_clone_mode("exact") == "exact"

    def test_verify_mode(self):
        assert clone.normalize_clone_mode("verify") == "verify"

    def test_raw_mode_alias(self):
        """Test that 'raw' is normalized to 'exact'."""
        assert clone.normalize_clone_mode("raw") == "exact"

    def test_uppercase_mode(self):
        assert clone.normalize_clone_mode("SMART") == "smart"
        assert clone.normalize_clone_mode("EXACT") == "exact"

    def test_none_defaults_to_smart(self):
        assert clone.normalize_clone_mode(None) == "smart"

    def test_empty_string_defaults_to_smart(self):
        assert clone.normalize_clone_mode("") == "smart"

    def test_invalid_mode_defaults_to_smart(self):
        assert clone.normalize_clone_mode("invalid") == "smart"
        assert clone.normalize_clone_mode("quick") == "smart"


class TestResolveDeviceNode:
    """Tests for resolve_device_node() function."""

    def test_device_dict(self):
        device = {"name": "sda"}
        assert clone.resolve_device_node(device) == "/dev/sda"

    def test_string_without_dev_prefix(self):
        assert clone.resolve_device_node("sda") == "/dev/sda"

    def test_string_with_dev_prefix(self):
        assert clone.resolve_device_node("/dev/sda") == "/dev/sda"

    def test_partition_device(self):
        device = {"name": "sda1"}
        assert clone.resolve_device_node(device) == "/dev/sda1"


class TestFormatEta:
    """Tests for format_eta() function."""

    def test_seconds_only(self):
        assert clone.format_eta(45) == "00:45"

    def test_minutes_and_seconds(self):
        assert clone.format_eta(185) == "03:05"

    def test_hours_minutes_seconds(self):
        assert clone.format_eta(3661) == "1:01:01"

    def test_zero_seconds(self):
        assert clone.format_eta(0) == "00:00"

    def test_none_returns_none(self):
        assert clone.format_eta(None) is None

    def test_negative_returns_none(self):
        assert clone.format_eta(-10) is None

    def test_float_rounds_down(self):
        assert clone.format_eta(90.9) == "01:30"

    def test_large_hours(self):
        # 25 hours, 30 minutes, 15 seconds
        assert clone.format_eta(91815) == "25:30:15"


class TestFormatFilesystemType:
    """Tests for format_filesystem_type() function."""

    def test_vfat_to_fat32(self):
        assert clone.format_filesystem_type("vfat") == "FAT32"

    def test_ext4(self):
        assert clone.format_filesystem_type("ext4") == "ext4"

    def test_ntfs(self):
        assert clone.format_filesystem_type("ntfs") == "NTFS"

    def test_exfat(self):
        assert clone.format_filesystem_type("exfat") == "exFAT"

    def test_btrfs(self):
        assert clone.format_filesystem_type("btrfs") == "Btrfs"

    def test_case_insensitive(self):
        assert clone.format_filesystem_type("VFAT") == "FAT32"
        assert clone.format_filesystem_type("Ext4") == "ext4"

    def test_none_returns_unknown(self):
        assert clone.format_filesystem_type(None) == "unknown"

    def test_empty_string_returns_unknown(self):
        assert clone.format_filesystem_type("") == "unknown"

    def test_unknown_filesystem(self):
        assert clone.format_filesystem_type("zfs") == "zfs"


class TestGetPartitionDisplayName:
    """Tests for get_partition_display_name() function."""

    def test_with_partlabel(self):
        part = {"partlabel": "EFI System", "label": "ESP", "name": "sda1"}
        assert clone.get_partition_display_name(part) == "EFI System"

    def test_with_label_no_partlabel(self):
        part = {"label": "USB_DRIVE", "name": "sda1"}
        assert clone.get_partition_display_name(part) == "USB_DRIVE"

    def test_with_name_only(self):
        part = {"name": "sda1"}
        assert clone.get_partition_display_name(part) == "sda1"

    def test_empty_dict(self):
        assert clone.get_partition_display_name({}) == "partition"

    def test_strips_whitespace(self):
        part = {"label": "  USB  "}
        assert clone.get_partition_display_name(part) == "USB"


class TestGetPartitionNumber:
    """Tests for get_partition_number() function."""

    def test_simple_partition(self):
        assert clone.get_partition_number("sda1") == 1
        assert clone.get_partition_number("sda2") == 2

    def test_nvme_partition(self):
        """NVMe devices use 'p' prefix (e.g., nvme0n1p1)."""
        assert clone.get_partition_number("nvme0n1p1") == 1
        assert clone.get_partition_number("nvme0n1p2") == 2

    def test_mmc_partition(self):
        """MMC devices use 'p' prefix (e.g., mmcblk0p1)."""
        assert clone.get_partition_number("mmcblk0p1") == 1

    def test_no_number(self):
        assert clone.get_partition_number("sda") is None

    def test_none(self):
        assert clone.get_partition_number(None) is None

    def test_empty_string(self):
        assert clone.get_partition_number("") is None


class TestFormatProgressLines:
    """Tests for format_progress_lines() function."""

    def test_basic_progress(self):
        lines = clone.format_progress_lines(
            title="CLONING",
            device="sda",
            mode="smart",
            bytes_copied=1024**3,  # 1GB
            total_bytes=2 * 1024**3,  # 2GB
            rate=50 * 1024**2,  # 50MB/s
            eta="00:20",
        )

        assert "CLONING" in lines
        assert "sda" in lines
        assert "Mode smart" in lines
        assert any("1.0GB" in line for line in lines)
        assert any("50.0%" in line for line in lines)

    def test_without_eta(self):
        lines = clone.format_progress_lines(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=1024**2,
            total_bytes=None,
            rate=10 * 1024**2,
            eta=None,
        )

        assert "CLONING" in lines
        assert any("MB/s" in line for line in lines)

    def test_no_bytes_copied(self):
        lines = clone.format_progress_lines(
            title="WORKING",
            device=None,
            mode=None,
            bytes_copied=None,
            total_bytes=None,
            rate=None,
            eta=None,
        )

        assert "WORKING" in lines
        assert "Working..." in lines

    def test_max_six_lines(self):
        """Ensure output is limited to 6 lines for display."""
        lines = clone.format_progress_lines(
            title="A",
            device="B",
            mode="C",
            bytes_copied=100,
            total_bytes=1000,
            rate=50,
            eta="01:00",
        )

        assert len(lines) <= 6


class TestFormatProgressDisplay:
    """Tests for format_progress_display() function."""

    def test_with_spinner(self):
        lines = clone.format_progress_display(
            title="CLONING",
            device="sda",
            mode="smart",
            bytes_copied=1024**3,
            total_bytes=2 * 1024**3,
            percent=None,
            rate=50 * 1024**2,
            eta="00:20",
            spinner="|",
        )

        assert any("|" in line for line in lines)

    def test_with_subtitle(self):
        lines = clone.format_progress_display(
            title="CLONING",
            device=None,
            mode=None,
            bytes_copied=100,
            total_bytes=1000,
            percent=10.0,
            rate=None,
            eta=None,
            subtitle="Partition 1 of 3",
        )

        assert "Partition 1 of 3" in lines

    def test_percent_without_bytes(self):
        """Test display with percentage but no byte count."""
        lines = clone.format_progress_display(
            title="WORKING",
            device=None,
            mode=None,
            bytes_copied=None,
            total_bytes=None,
            percent=50.0,
            rate=None,
            eta=None,
        )

        # Should show "Working..." when no bytes copied
        assert "Working..." in lines


class TestCopyPartitionTable:
    """Tests for copy_partition_table() function."""

    @pytest.mark.unit
    def test_mbr_partition_table(self, mocker):
        """Test copying MBR/DOS partition table."""
        mock_which = mocker.patch("shutil.which")
        mock_which.return_value = "/usr/sbin/sfdisk"

        sfdisk_output = """label: dos
label-id: 0x12345678
device: /dev/sda
unit: sectors

/dev/sda1 : start=2048, size=1048576, type=c, bootable
/dev/sda2 : start=1050624, size=29360128, type=83
"""

        mock_run = mocker.patch(
            "rpi_usb_cloner.storage.clone.operations.run_checked_command"
        )
        mock_run.side_effect = [sfdisk_output, None]  # dump, then write

        src = {"name": "sda"}
        dst = {"name": "sdb"}

        clone.copy_partition_table(src, dst)

        # Verify sfdisk dump was called
        assert mock_run.call_count == 2
        dump_call = mock_run.call_args_list[0]
        assert "sfdisk" in dump_call[0][0][0]
        assert "--dump" in dump_call[0][0]

    @pytest.mark.unit
    def test_gpt_partition_table(self, mocker):
        """Test copying GPT partition table."""
        mock_which = mocker.patch("shutil.which")

        def which_side_effect(cmd):
            if cmd == "sfdisk":
                return "/usr/sbin/sfdisk"
            if cmd == "sgdisk":
                return "/usr/sbin/sgdisk"
            return None

        mock_which.side_effect = which_side_effect

        sfdisk_output = """label: gpt
label-id: ABCD-1234
device: /dev/sda
unit: sectors
"""

        mock_run = mocker.patch(
            "rpi_usb_cloner.storage.clone.operations.run_checked_command"
        )
        mock_run.side_effect = [sfdisk_output, None]  # dump, then sgdisk

        src = {"name": "sda"}
        dst = {"name": "sdb"}

        clone.copy_partition_table(src, dst)

        # Verify sgdisk was called
        assert mock_run.call_count == 2
        sgdisk_call = mock_run.call_args_list[1]
        assert "sgdisk" in sgdisk_call[0][0][0]
        assert "--replicate=/dev/sdb" in sgdisk_call[0][0]

    @pytest.mark.unit
    def test_missing_sfdisk(self, mocker):
        """Test error when sfdisk is not found."""
        mock_which = mocker.patch("shutil.which")
        mock_which.return_value = None

        src = {"name": "sda"}
        dst = {"name": "sdb"}

        with pytest.raises(RuntimeError, match="sfdisk not found"):
            clone.copy_partition_table(src, dst)

    @pytest.mark.unit
    def test_missing_sgdisk_for_gpt(self, mocker):
        """Test error when sgdisk is not found for GPT."""
        mock_which = mocker.patch("shutil.which")

        def which_side_effect(cmd):
            return "/usr/sbin/sfdisk" if cmd == "sfdisk" else None

        mock_which.side_effect = which_side_effect

        sfdisk_output = "label: gpt\n"

        mock_run = mocker.patch(
            "rpi_usb_cloner.storage.clone.operations.run_checked_command"
        )
        mock_run.return_value = sfdisk_output

        src = {"name": "sda"}
        dst = {"name": "sdb"}

        with pytest.raises(RuntimeError, match="sgdisk not found"):
            clone.copy_partition_table(src, dst)

    @pytest.mark.unit
    def test_no_label_detected(self, mocker):
        """Test error when partition table label cannot be detected."""
        mock_which = mocker.patch("shutil.which")
        mock_which.return_value = "/usr/sbin/sfdisk"

        sfdisk_output = "device: /dev/sda\nunit: sectors\n"  # No label line

        mock_run = mocker.patch(
            "rpi_usb_cloner.storage.clone.operations.run_checked_command"
        )
        mock_run.return_value = sfdisk_output

        src = {"name": "sda"}
        dst = {"name": "sdb"}

        with pytest.raises(
            RuntimeError, match="Unable to detect partition table label"
        ):
            clone.copy_partition_table(src, dst)

    @pytest.mark.unit
    def test_unsupported_label(self, mocker):
        """Test error with unsupported partition table type."""
        mock_which = mocker.patch("shutil.which")
        mock_which.return_value = "/usr/sbin/sfdisk"

        sfdisk_output = "label: aix\n"  # Unsupported

        mock_run = mocker.patch(
            "rpi_usb_cloner.storage.clone.operations.run_checked_command"
        )
        mock_run.return_value = sfdisk_output

        src = {"name": "sda"}
        dst = {"name": "sdb"}

        with pytest.raises(RuntimeError, match="Unsupported partition table label"):
            clone.copy_partition_table(src, dst)


class TestRunCheckedCommand:
    """Tests for run_checked_command() helper."""

    def test_successful_command(self, mocker):
        """Test successful command execution."""
        mock_run = mocker.patch("subprocess.run")
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "success output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        output = clone.run_checked_command(["echo", "test"])

        assert output == "success output"

    def test_failed_command_raises(self, mocker):
        """Test that failed command raises RuntimeError."""
        mock_run = mocker.patch("subprocess.run")
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message"
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="Command failed"):
            clone.run_checked_command(["false"])

    def test_command_with_input(self, mocker):
        """Test command with stdin input."""
        mock_run = mocker.patch("subprocess.run")
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        clone.run_checked_command(["cat"], input_text="test input")

        call_args = mock_run.call_args
        assert call_args[1]["input"] == "test input"


class TestConfigureCloneHelpers:
    """Tests for configure_clone_helpers() function."""

    def test_configure_logger(self):
        """Test configuring debug logger."""
        mock_logger = Mock()

        clone.configure_clone_helpers(log_debug=mock_logger)

        assert clone._log_debug == mock_logger

    def test_none_logger(self):
        """Test configuring with None."""
        clone.configure_clone_helpers(log_debug=None)

        # Should be set but not raise on use
        clone.log_debug("test message")


class TestLogDebug:
    """Tests for log_debug() wrapper function."""

    def test_logs_when_configured(self):
        """Test that log_debug calls configured logger."""
        mock_logger = Mock()
        clone.configure_clone_helpers(log_debug=mock_logger)

        clone.log_debug("test message")

        mock_logger.assert_called_once_with("test message")

    def test_no_error_when_not_configured(self):
        """Test that log_debug doesn't error when no logger configured."""
        clone.configure_clone_helpers(log_debug=None)

        # Should not raise
        clone.log_debug("test message")
