"""Tests for storage/format.py - USB drive formatting operations.

This test suite covers:
- Quick format for all supported filesystems (vfat, ext4, exfat, ntfs)
- Full format mode with bad block checking
- Partition table creation (MBR)
- Filesystem label creation
- Progress callback invocation
- Validation (system devices, unmounted devices)
- Error handling (mkfs failures, parted failures, device busy)
- Unmount operations before formatting
"""

import subprocess
from unittest.mock import Mock, patch

from rpi_usb_cloner.storage import format as format_module


class TestValidateDevicePath:
    """Tests for _validate_device_path() function."""

    def test_valid_dev_path(self):
        """Test that /dev/ paths are accepted."""
        assert format_module._validate_device_path("/dev/sda") is True
        assert format_module._validate_device_path("/dev/sdb1") is True

    def test_invalid_path_without_dev(self):
        """Test that non-/dev/ paths are rejected."""
        assert format_module._validate_device_path("/tmp/fake") is False
        assert format_module._validate_device_path("sda") is False
        assert format_module._validate_device_path("/etc/passwd") is False


class TestCreatePartitionTable:
    """Tests for _create_partition_table() function."""

    @patch("rpi_usb_cloner.storage.format.run_command")
    def test_create_mbr_partition_table_success(self, mock_run):
        """Test successful MBR partition table creation."""
        mock_run.return_value = Mock(returncode=0, stderr="", stdout="")

        result = format_module._create_partition_table("/dev/sda")

        assert result is True
        mock_run.assert_called_with(
            ["parted", "-s", "/dev/sda", "mklabel", "msdos"],
            check=False,
            log_command=False,
        )

    @patch("rpi_usb_cloner.storage.format.run_command")
    def test_create_partition_table_failure(self, mock_run):
        """Test partition table creation failure."""
        mock_run.return_value = Mock(returncode=1, stderr="parted: Error", stdout="")

        result = format_module._create_partition_table("/dev/sda")

        assert result is False

    @patch("rpi_usb_cloner.storage.format.log.error")
    @patch("rpi_usb_cloner.storage.format.run_command")
    def test_create_partition_table_logs_error(self, mock_run, mock_log):
        """Test that partition table errors are logged via loguru."""
        mock_run.return_value = Mock(returncode=1, stderr="Device busy", stdout="")

        format_module._create_partition_table("/dev/sda")

        # Verify error was logged via loguru at ERROR level
        assert any("parted failed" in str(call) for call in mock_log.call_args_list)


class TestCreatePartition:
    """Tests for _create_partition() function."""

    @patch("rpi_usb_cloner.storage.format.os.path.exists")
    @patch("rpi_usb_cloner.storage.format.shutil.which")
    @patch("rpi_usb_cloner.storage.format.time.sleep")
    @patch("rpi_usb_cloner.storage.format.run_command")
    def test_create_partition_success(
        self, mock_run, mock_sleep, mock_which, mock_exists
    ):
        """Test successful partition creation."""
        mock_run.return_value = Mock(returncode=0)
        mock_which.return_value = "/usr/bin/sync"  # Pretend all commands exist
        mock_exists.return_value = True  # Partition appears immediately

        result = format_module._create_partition("/dev/sda")

        assert result is True
        # Verify the parted mkpart command was called first
        assert mock_run.call_args_list[0] == (
            (["parted", "-s", "/dev/sda", "mkpart", "primary", "1MiB", "100%"],),
        )

    @patch("rpi_usb_cloner.storage.format.time.sleep")
    @patch("rpi_usb_cloner.storage.format.run_command")
    def test_create_partition_failure(self, mock_run, mock_sleep):
        """Test partition creation failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "parted", stderr="Invalid geometry"
        )

        result = format_module._create_partition("/dev/sda")

        assert result is False


class TestFormatFilesystem:
    """Tests for _format_filesystem() function."""

    @patch("rpi_usb_cloner.storage.format._unmount_partition_aggressive")
    @patch("rpi_usb_cloner.storage.format._ensure_partition_unmounted")
    @patch("rpi_usb_cloner.storage.format.subprocess.Popen")
    def test_format_ext4_quick_mode(
        self, mock_popen, mock_unmount_check, mock_unmount_partition
    ):
        """Test quick ext4 format."""
        mock_unmount_check.return_value = True
        mock_unmount_partition.return_value = True
        mock_proc = Mock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.stderr = Mock()
        mock_popen.return_value = mock_proc

        result = format_module._format_filesystem(
            "/dev/sda1", "ext4", "quick", label="TEST", progress_callback=None
        )

        assert result is True
        # Verify mkfs.ext4 was called with correct flags
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "mkfs.ext4"
        assert "-F" in cmd  # Force flag
        assert "-c" not in cmd  # No bad block check in quick mode
        assert "-L" in cmd
        assert "TEST" in cmd

    @patch("rpi_usb_cloner.storage.format._unmount_partition_aggressive")
    @patch("rpi_usb_cloner.storage.format._ensure_partition_unmounted")
    @patch("rpi_usb_cloner.storage.format.subprocess.Popen")
    def test_format_ext4_full_mode(
        self, mock_popen, mock_unmount_check, mock_unmount_partition
    ):
        """Test full ext4 format with bad block checking."""
        mock_unmount_check.return_value = True
        mock_unmount_partition.return_value = True
        mock_proc = Mock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.stderr = Mock()
        mock_popen.return_value = mock_proc

        result = format_module._format_filesystem(
            "/dev/sda1", "ext4", "full", label=None, progress_callback=None
        )

        assert result is True
        # Verify -c flag for bad block checking
        cmd = mock_popen.call_args[0][0]
        assert "-c" in cmd

    @patch("rpi_usb_cloner.storage.format._unmount_partition_aggressive")
    @patch("rpi_usb_cloner.storage.format._ensure_partition_unmounted")
    @patch("rpi_usb_cloner.storage.format.subprocess.Popen")
    def test_format_vfat_with_label(
        self, mock_popen, mock_unmount_check, mock_unmount_partition
    ):
        """Test FAT32 format with label."""
        mock_unmount_check.return_value = True
        mock_unmount_partition.return_value = True
        mock_proc = Mock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.stderr = Mock()
        mock_popen.return_value = mock_proc

        result = format_module._format_filesystem(
            "/dev/sda1", "vfat", "quick", label="USB_DRIVE", progress_callback=None
        )

        assert result is True
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "mkfs.vfat"
        assert "-F" in cmd
        assert "32" in cmd  # FAT32
        assert "-n" in cmd
        assert "USB_DRIVE" in cmd

    @patch("rpi_usb_cloner.storage.format._unmount_partition_aggressive")
    @patch("rpi_usb_cloner.storage.format._ensure_partition_unmounted")
    @patch("rpi_usb_cloner.storage.format.subprocess.Popen")
    def test_format_exfat_with_label(
        self, mock_popen, mock_unmount_check, mock_unmount_partition
    ):
        """Test exFAT format with label."""
        mock_unmount_check.return_value = True
        mock_unmount_partition.return_value = True
        mock_proc = Mock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.stderr = Mock()
        mock_popen.return_value = mock_proc

        result = format_module._format_filesystem(
            "/dev/sda1", "exfat", "quick", label="BACKUP", progress_callback=None
        )

        assert result is True
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "mkfs.exfat"
        assert "-n" in cmd
        assert "BACKUP" in cmd

    @patch("rpi_usb_cloner.storage.format._unmount_partition_aggressive")
    @patch("rpi_usb_cloner.storage.format._ensure_partition_unmounted")
    @patch("rpi_usb_cloner.storage.format.subprocess.Popen")
    def test_format_ntfs_quick_mode(
        self, mock_popen, mock_unmount_check, mock_unmount_partition
    ):
        """Test quick NTFS format."""
        mock_unmount_check.return_value = True
        mock_unmount_partition.return_value = True
        mock_proc = Mock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.stderr = Mock()
        mock_popen.return_value = mock_proc

        result = format_module._format_filesystem(
            "/dev/sda1", "ntfs", "quick", label="NTFS_DRIVE", progress_callback=None
        )

        assert result is True
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "mkfs.ntfs"
        assert "-f" in cmd  # Fast format flag
        assert "-L" in cmd
        assert "NTFS_DRIVE" in cmd

    @patch("rpi_usb_cloner.storage.format._unmount_partition_aggressive")
    @patch("rpi_usb_cloner.storage.format._ensure_partition_unmounted")
    @patch("rpi_usb_cloner.storage.format.subprocess.Popen")
    def test_format_ntfs_full_mode(
        self, mock_popen, mock_unmount_check, mock_unmount_partition
    ):
        """Test full NTFS format (no fast flag)."""
        mock_unmount_check.return_value = True
        mock_unmount_partition.return_value = True
        mock_proc = Mock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.stderr = Mock()
        mock_popen.return_value = mock_proc

        result = format_module._format_filesystem(
            "/dev/sda1", "ntfs", "full", label=None, progress_callback=None
        )

        assert result is True
        cmd = mock_popen.call_args[0][0]
        assert "-f" not in cmd  # No fast flag in full mode

    def test_format_unsupported_filesystem(self):
        """Test error handling for unsupported filesystem."""
        result = format_module._format_filesystem(
            "/dev/sda1", "btrfs", "quick", label=None, progress_callback=None
        )

        assert result is False

    @patch("rpi_usb_cloner.storage.format._ensure_partition_unmounted")
    @patch("rpi_usb_cloner.storage.format.subprocess.Popen")
    def test_format_aborts_when_mounted(self, mock_popen, mock_unmount_check):
        """Test format aborts when partition remains mounted."""
        mock_unmount_check.return_value = False

        result = format_module._format_filesystem(
            "/dev/sda1", "ext4", "quick", label=None, progress_callback=None
        )

        assert result is False
        mock_popen.assert_not_called()

    @patch("rpi_usb_cloner.storage.format._unmount_partition_aggressive")
    @patch("rpi_usb_cloner.storage.format._ensure_partition_unmounted")
    @patch("rpi_usb_cloner.storage.format.subprocess.Popen")
    def test_format_with_progress_callback(
        self, mock_popen, mock_unmount_check, mock_unmount_partition
    ):
        """Test that progress callback is invoked."""
        mock_unmount_check.return_value = True
        mock_unmount_partition.return_value = True
        mock_proc = Mock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.stderr = Mock()
        mock_popen.return_value = mock_proc

        progress_calls = []

        def progress_callback(lines, ratio):
            progress_calls.append((lines, ratio))

        result = format_module._format_filesystem(
            "/dev/sda1",
            "vfat",
            "quick",
            label=None,
            progress_callback=progress_callback,
        )

        assert result is True
        # Verify progress callback was called
        assert len(progress_calls) >= 2  # Start and complete
        assert progress_calls[-1][1] == 1.0  # Final progress is 100%

    @patch("rpi_usb_cloner.storage.format._unmount_partition_aggressive")
    @patch("rpi_usb_cloner.storage.format._ensure_partition_unmounted")
    @patch("rpi_usb_cloner.storage.format.time.sleep")
    @patch("rpi_usb_cloner.storage.format.select.select")
    @patch("rpi_usb_cloner.storage.format.subprocess.Popen")
    def test_format_ext4_progress_parsing(
        self,
        mock_popen,
        mock_select,
        mock_sleep,
        mock_unmount_check,
        mock_unmount_partition,
    ):
        """Test ext4 progress parsing from stderr."""
        mock_unmount_check.return_value = True
        mock_unmount_partition.return_value = True
        mock_proc = Mock()
        mock_proc.stderr = Mock()

        # Simulate progress output
        progress_lines = [
            "Creating filesystem\n",
            "Writing inode tables: 25%\n",
            "Writing inode tables: 50%\n",
            "Writing inode tables: 100%\n",
        ]
        mock_proc.stderr.readline.side_effect = progress_lines + [""]
        mock_proc.poll.side_effect = [None, None, None, 0]
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        # select returns readable when stderr has data
        mock_select.return_value = ([mock_proc.stderr], [], [])

        progress_calls = []

        def progress_callback(lines, ratio):
            progress_calls.append((lines, ratio))

        result = format_module._format_filesystem(
            "/dev/sda1",
            "ext4",
            "quick",
            label=None,
            progress_callback=progress_callback,
        )

        assert result is True
        # Verify progress was tracked
        assert len(progress_calls) > 0

    @patch("rpi_usb_cloner.storage.format._unmount_partition_aggressive")
    @patch("rpi_usb_cloner.storage.format._ensure_partition_unmounted")
    @patch("rpi_usb_cloner.storage.format.subprocess.Popen")
    def test_format_failure_nonzero_return(
        self, mock_popen, mock_unmount_check, mock_unmount_partition
    ):
        """Test format failure with non-zero return code."""
        mock_unmount_check.return_value = True
        mock_unmount_partition.return_value = True
        mock_proc = Mock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 1  # Non-zero return code
        mock_proc.stderr = Mock()
        mock_proc.stderr.read.return_value = "mkfs failed"
        mock_popen.return_value = mock_proc

        result = format_module._format_filesystem(
            "/dev/sda1", "vfat", "quick", label=None, progress_callback=None
        )

        assert result is False

    @patch("rpi_usb_cloner.storage.format._unmount_partition_aggressive")
    @patch("rpi_usb_cloner.storage.format._ensure_partition_unmounted")
    @patch("rpi_usb_cloner.storage.format.subprocess.Popen")
    def test_format_exception_handling(
        self, mock_popen, mock_unmount_check, mock_unmount_partition
    ):
        """Test exception handling during format."""
        mock_unmount_check.return_value = True
        mock_unmount_partition.return_value = True
        mock_popen.side_effect = FileNotFoundError("mkfs missing")

        result = format_module._format_filesystem(
            "/dev/sda1", "vfat", "quick", label=None, progress_callback=None
        )

        assert result is False


class TestFormatDevice:
    """Tests for format_device() main function."""

    @patch("rpi_usb_cloner.storage.format._get_live_partition_mountpoint")
    @patch("rpi_usb_cloner.storage.format.os.path.exists")
    @patch("rpi_usb_cloner.storage.format._format_filesystem")
    @patch("rpi_usb_cloner.storage.format._create_partition")
    @patch("rpi_usb_cloner.storage.format._create_partition_table")
    @patch("rpi_usb_cloner.storage.format.unmount_device")
    def test_format_device_full_workflow(
        self,
        mock_unmount,
        mock_create_table,
        mock_create_part,
        mock_format_fs,
        mock_exists,
        mock_live_mountpoint,
    ):
        """Test complete format workflow."""
        device = {"name": "sda", "size": "16106127360"}

        mock_unmount.return_value = True
        mock_create_table.return_value = True
        mock_create_part.return_value = True
        mock_format_fs.return_value = True
        mock_exists.return_value = True  # Partition exists
        mock_live_mountpoint.return_value = None

        result = format_module.format_device(device, "ext4", "quick", label="TEST")

        assert result is True

        # Verify workflow steps
        mock_unmount.assert_called_once()
        mock_create_table.assert_called_once_with("/dev/sda")
        mock_create_part.assert_called_once_with("/dev/sda")
        mock_format_fs.assert_called_once()

    @patch("rpi_usb_cloner.storage.format.unmount_device")
    def test_format_device_unmount_returns_false(self, mock_unmount):
        """Test format aborted when unmount returns False."""
        device = {"name": "sda", "size": "16106127360"}
        mock_unmount.return_value = False

        result = format_module.format_device(device, "ext4", "quick")

        assert result is False

    def test_format_device_no_name_field(self):
        """Test format failure when device has no name."""
        device = {"size": "1000000"}  # Missing 'name' field

        result = format_module.format_device(device, "ext4", "quick")

        assert result is False

    @patch("rpi_usb_cloner.storage.format.unmount_device")
    def test_format_device_unmount_failure(self, mock_unmount):
        """Test format aborted when unmount fails."""
        device = {"name": "sda", "size": "16106127360"}
        mock_unmount.return_value = False

        result = format_module.format_device(device, "ext4", "quick")

        assert result is False

    @patch("rpi_usb_cloner.storage.format._create_partition_table")
    @patch("rpi_usb_cloner.storage.format.unmount_device")
    def test_format_device_partition_table_fails(
        self,
        mock_unmount,
        mock_create_table,
    ):
        """Test format aborted when partition table creation fails."""
        device = {"name": "sda", "size": "16106127360"}

        mock_unmount.return_value = True
        mock_create_table.return_value = False

        result = format_module.format_device(device, "ext4", "quick")

        assert result is False

    @patch("rpi_usb_cloner.storage.format._create_partition")
    @patch("rpi_usb_cloner.storage.format._create_partition_table")
    @patch("rpi_usb_cloner.storage.format.unmount_device")
    def test_format_device_create_partition_failure(
        self,
        mock_unmount,
        mock_create_table,
        mock_create_part,
    ):
        """Test format aborted when partition creation fails."""
        device = {"name": "sda", "size": "16106127360"}

        mock_unmount.return_value = True
        mock_create_table.return_value = True
        mock_create_part.return_value = False

        result = format_module.format_device(device, "ext4", "quick")

        assert result is False

    @patch("rpi_usb_cloner.storage.format.os.path.exists")
    @patch("rpi_usb_cloner.storage.format._format_filesystem")
    @patch("rpi_usb_cloner.storage.format._create_partition")
    @patch("rpi_usb_cloner.storage.format._create_partition_table")
    @patch("rpi_usb_cloner.storage.format.unmount_device")
    def test_format_device_format_filesystem_failure(
        self,
        mock_unmount,
        mock_create_table,
        mock_create_part,
        mock_format_fs,
        mock_exists,
    ):
        """Test format failure when filesystem creation fails."""
        device = {"name": "sda", "size": "16106127360"}

        mock_unmount.return_value = True
        mock_create_table.return_value = True
        mock_create_part.return_value = True
        mock_format_fs.return_value = False
        mock_exists.return_value = True  # Partition exists

        result = format_module.format_device(device, "ext4", "quick")

        assert result is False

    @patch("rpi_usb_cloner.storage.format._get_live_partition_mountpoint")
    @patch("rpi_usb_cloner.storage.format.os.path.exists")
    @patch("rpi_usb_cloner.storage.format._format_filesystem")
    @patch("rpi_usb_cloner.storage.format._create_partition")
    @patch("rpi_usb_cloner.storage.format._create_partition_table")
    @patch("rpi_usb_cloner.storage.format.unmount_device")
    def test_format_device_with_progress_callback(
        self,
        mock_unmount,
        mock_create_table,
        mock_create_part,
        mock_format_fs,
        mock_exists,
        mock_live_mountpoint,
    ):
        """Test that progress callback is passed through."""
        device = {"name": "sda", "size": "16106127360"}

        mock_unmount.return_value = True
        mock_create_table.return_value = True
        mock_create_part.return_value = True
        mock_format_fs.return_value = True
        mock_exists.return_value = True  # Partition exists
        mock_live_mountpoint.return_value = None

        progress_calls = []

        def progress_callback(lines, ratio):
            progress_calls.append((lines, ratio))

        result = format_module.format_device(
            device, "ext4", "quick", progress_callback=progress_callback
        )

        assert result is True
        # Verify progress was reported at multiple stages
        assert len(progress_calls) >= 3  # Unmount, partition table, partition

    @patch("rpi_usb_cloner.storage.format._get_live_partition_mountpoint")
    @patch("rpi_usb_cloner.storage.format.os.path.exists")
    @patch("rpi_usb_cloner.storage.format._format_filesystem")
    @patch("rpi_usb_cloner.storage.format._create_partition")
    @patch("rpi_usb_cloner.storage.format._create_partition_table")
    @patch("rpi_usb_cloner.storage.format.unmount_device")
    def test_format_device_partition_suffix_for_numbered_device(
        self,
        mock_unmount,
        mock_create_table,
        mock_create_part,
        mock_format_fs,
        mock_exists,
        mock_live_mountpoint,
    ):
        """Test partition suffix 'p' for devices ending in digit (e.g., mmcblk0p1)."""
        device = {"name": "mmcblk0", "size": "16106127360", "rm": "1"}

        mock_unmount.return_value = True
        mock_create_table.return_value = True
        mock_create_part.return_value = True
        mock_format_fs.return_value = True
        mock_exists.return_value = True  # Partition exists
        mock_live_mountpoint.return_value = None

        result = format_module.format_device(device, "ext4", "quick")

        assert result is True
        # Verify partition path includes 'p' suffix
        format_fs_call = mock_format_fs.call_args[0]
        partition_path = format_fs_call[0]
        assert partition_path == "/dev/mmcblk0p1"

    @patch("rpi_usb_cloner.storage.format._get_live_partition_mountpoint")
    @patch("rpi_usb_cloner.storage.format.os.path.exists")
    @patch("rpi_usb_cloner.storage.format._format_filesystem")
    @patch("rpi_usb_cloner.storage.format._create_partition")
    @patch("rpi_usb_cloner.storage.format._create_partition_table")
    @patch("rpi_usb_cloner.storage.format.unmount_device")
    def test_format_device_no_partition_suffix_for_letter_device(
        self,
        mock_unmount,
        mock_create_table,
        mock_create_part,
        mock_format_fs,
        mock_exists,
        mock_live_mountpoint,
    ):
        """Test no partition suffix for devices ending in letter (e.g., sda1)."""
        device = {"name": "sda", "size": "16106127360"}

        mock_unmount.return_value = True
        mock_create_table.return_value = True
        mock_create_part.return_value = True
        mock_format_fs.return_value = True
        mock_exists.return_value = True  # Partition exists
        mock_live_mountpoint.return_value = None

        result = format_module.format_device(device, "ext4", "quick")

        assert result is True
        # Verify partition path has no 'p' suffix
        format_fs_call = mock_format_fs.call_args[0]
        partition_path = format_fs_call[0]
        assert partition_path == "/dev/sda1"


class TestConfigureFormatHelpers:
    """Tests for configure_format_helpers() function."""

    def test_configure_log_debug(self):
        """Test configuring debug logging (backwards compatibility)."""
        mock_logger = Mock()

        # Should not crash - log_debug parameter is ignored, uses loguru directly
        format_module.configure_format_helpers(log_debug=mock_logger)

    def test_log_debug_without_configuration(self):
        """Test that configure works without configuration."""
        # Should not raise exception
        format_module.configure_format_helpers(log_debug=None)
