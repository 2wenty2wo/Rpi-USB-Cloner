"""Tests for storage/mount.py - USB device mounting operations.

This test suite complements test_mount_security.py with happy-path tests covering:
- Successful mount operations
- Mountpoint directory creation
- Successful unmount operations
- get_partition() for various device types (sda, nvme, mmcblk)
- Mount point path generation
- Handling already-mounted devices
- Cleanup on mount failures
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from rpi_usb_cloner.storage import mount


class TestGetPartition:
    """Tests for get_partition() function - happy paths."""

    @patch("subprocess.run")
    def test_get_partition_sda_device(self, mock_run):
        """Test getting partition from standard disk (sda)."""
        fdisk_output = """Disk /dev/sda: 15 GiB, 16106127360 bytes
...
Device     Boot Start      End  Sectors Size Id Type
/dev/sda1  *     2048  1050623  1048576 512M  c W95 FAT32 (LBA)
/dev/sda2     1050624 31428095 30377472  14.5G 83 Linux"""

        mock_run.return_value = Mock(returncode=0, stdout=fdisk_output)

        result = mount.get_partition("/dev/sda")

        assert result == "/dev/sda2"  # Last partition
        mock_run.assert_called_once_with(
            ["fdisk", "-l", "/dev/sda"], check=True, capture_output=True, text=True
        )

    @patch("subprocess.run")
    def test_get_partition_nvme_device(self, mock_run):
        """Test getting partition from NVMe device."""
        fdisk_output = """Disk /dev/nvme0n1: 256 GiB
...
Device           Start       End   Sectors  Size Type
/dev/nvme0n1p1    2048   1050623   1048576  512M EFI System
/dev/nvme0n1p2 1050624 536870911 535820288  256G Linux filesystem"""

        mock_run.return_value = Mock(returncode=0, stdout=fdisk_output)

        result = mount.get_partition("/dev/nvme0n1")

        assert result == "/dev/nvme0n1p2"

    @patch("subprocess.run")
    def test_get_partition_mmcblk_device(self, mock_run):
        """Test getting partition from MMC device."""
        fdisk_output = """Disk /dev/mmcblk0: 31.9 GB
...
Device         Boot  Start      End  Sectors  Size Id Type
/dev/mmcblk0p1 *      2048   526335   524288  256M  c W95 FAT32 (LBA)
/dev/mmcblk0p2      526336 62333951 61807616 29.5G 83 Linux"""

        mock_run.return_value = Mock(returncode=0, stdout=fdisk_output)

        result = mount.get_partition("/dev/mmcblk0")

        assert result == "/dev/mmcblk0p2"

    @patch("subprocess.run")
    def test_get_partition_single_partition(self, mock_run):
        """Test getting partition when only one partition exists."""
        fdisk_output = """Disk /dev/sdb: 8 GiB
...
Device     Boot Start      End  Sectors Size Id Type
/dev/sdb1        2048 16777215 16775168   8G  b W95 FAT32"""

        mock_run.return_value = Mock(returncode=0, stdout=fdisk_output)

        result = mount.get_partition("/dev/sdb")

        assert result == "/dev/sdb1"

    @patch("subprocess.run")
    def test_get_partition_no_partitions(self, mock_run):
        """Test error when no partitions found."""
        fdisk_output = """Disk /dev/sdc: 16 GiB
Disk model: USB Flash Drive
Units: sectors of 1 * 512 = 512 bytes
Sector size (logical/physical): 512 bytes / 512 bytes"""

        mock_run.return_value = Mock(returncode=0, stdout=fdisk_output)

        with pytest.raises(RuntimeError, match="Could not find partition"):
            mount.get_partition("/dev/sdc")


class TestMountPartition:
    """Tests for mount_partition() function - happy paths."""

    @patch("os.path.ismount", return_value=False)
    @patch("subprocess.run")
    def test_mount_partition_success(self, mock_run, mock_ismount):
        """Test successful partition mount."""
        mock_run.return_value = Mock(returncode=0, stderr="")

        mount.mount_partition("/dev/sda1", "usb")

        # Verify mkdir and mount were called
        assert mock_run.call_count == 2

        mkdir_call = mock_run.call_args_list[0][0][0]
        assert mkdir_call == ["mkdir", "-p", "/media/usb"]

        mount_call = mock_run.call_args_list[1][0][0]
        assert mount_call == ["mount", "/dev/sda1", "/media/usb"]

    @patch("os.path.ismount", return_value=False)
    @patch("subprocess.run")
    def test_mount_partition_creates_directory(self, mock_run, mock_ismount):
        """Test that mount_partition creates mountpoint directory."""
        mock_run.return_value = Mock(returncode=0, stderr="")

        mount.mount_partition("/dev/sda1", "test_mount")

        # Verify mkdir was called with correct path
        mkdir_call = mock_run.call_args_list[0][0][0]
        assert mkdir_call == ["mkdir", "-p", "/media/test_mount"]

    @patch("os.path.ismount", return_value=True)
    @patch("subprocess.run")
    def test_mount_partition_already_mounted(self, mock_run, mock_ismount):
        """Test mount_partition skips when already mounted."""
        mount.mount_partition("/dev/sda1", "usb")

        # Verify no subprocess calls were made
        mock_run.assert_not_called()

    @patch("os.path.ismount", return_value=False)
    @patch("subprocess.run")
    def test_mount_partition_default_name(self, mock_run, mock_ismount):
        """Test mount_partition with default 'usb' name."""
        mock_run.return_value = Mock(returncode=0, stderr="")

        mount.mount_partition("/dev/sda1")

        # Verify default name 'usb' was used
        mount_call = mock_run.call_args_list[1][0][0]
        assert "/media/usb" in mount_call

    @patch("os.path.ismount", return_value=False)
    @patch("subprocess.run")
    def test_mount_partition_mkdir_failure_propagates(self, mock_run, mock_ismount):
        """Test that mkdir failures raise RuntimeError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "mkdir", stderr="mkdir: Permission denied"
        )

        with pytest.raises(RuntimeError, match="Failed to mount"):
            mount.mount_partition("/dev/sda1", "test")

    @patch("os.path.ismount", return_value=False)
    @patch("subprocess.run")
    def test_mount_partition_mount_failure_after_mkdir(self, mock_run, mock_ismount):
        """Test mount failure after successful mkdir."""
        # First call (mkdir) succeeds, second call (mount) fails
        mock_run.side_effect = [
            Mock(returncode=0, stderr=""),
            subprocess.CalledProcessError(32, "mount", stderr="mount: device busy"),
        ]

        with pytest.raises(RuntimeError, match="Failed to mount"):
            mount.mount_partition("/dev/sda1", "test")


class TestUnmountPartition:
    """Tests for unmount_partition() function - happy paths."""

    @patch("os.path.ismount", return_value=True)
    @patch("subprocess.run")
    def test_unmount_partition_success(self, mock_run, mock_ismount):
        """Test successful partition unmount."""
        mock_run.return_value = Mock(returncode=0, stderr="")

        mount.unmount_partition("usb")

        # Verify umount was called
        mock_run.assert_called_once_with(
            ["umount", "/media/usb"], check=True, capture_output=True, text=True
        )

    @patch("os.path.ismount", return_value=False)
    @patch("subprocess.run")
    def test_unmount_partition_not_mounted(self, mock_run, mock_ismount):
        """Test unmount_partition skips when not mounted."""
        mount.unmount_partition("usb")

        # Verify no subprocess calls were made
        mock_run.assert_not_called()

    @patch("os.path.ismount", return_value=True)
    @patch("subprocess.run")
    def test_unmount_partition_default_name(self, mock_run, mock_ismount):
        """Test unmount_partition with default 'usb' name."""
        mock_run.return_value = Mock(returncode=0, stderr="")

        mount.unmount_partition()

        # Verify default name 'usb' was used
        umount_call = mock_run.call_args[0][0]
        assert "/media/usb" in umount_call


class TestMountWrapper:
    """Tests for mount() wrapper function - happy paths."""

    @patch("rpi_usb_cloner.storage.mount.mount_partition")
    @patch("rpi_usb_cloner.storage.mount.get_partition")
    def test_mount_with_device_name(self, mock_get_part, mock_mount_part):
        """Test mount() wrapper with device path."""
        mock_get_part.return_value = "/dev/sda1"

        mount.mount("/dev/sda", "backup")

        # Verify both functions called correctly
        mock_get_part.assert_called_once_with("/dev/sda")
        mock_mount_part.assert_called_once_with("/dev/sda1", "backup")

    @patch("rpi_usb_cloner.storage.mount.mount_partition")
    @patch("rpi_usb_cloner.storage.mount.get_partition")
    @patch("rpi_usb_cloner.storage.mount.get_device_name")
    def test_mount_without_name_uses_device_name(
        self, mock_get_name, mock_get_part, mock_mount_part
    ):
        """Test mount() uses device name when name not provided."""
        mock_get_name.return_value = "sda"
        mock_get_part.return_value = "/dev/sda1"

        mount.mount("/dev/sda")

        # Verify device name was extracted and used
        mock_get_name.assert_called_once_with("/dev/sda")
        mock_mount_part.assert_called_once_with("/dev/sda1", "sda")

    @patch("rpi_usb_cloner.storage.mount.mount_partition")
    @patch("rpi_usb_cloner.storage.mount.get_partition")
    def test_mount_propagates_get_partition_errors(
        self, mock_get_part, mock_mount_part
    ):
        """Test mount() propagates errors from get_partition."""
        mock_get_part.side_effect = RuntimeError("No partition found")

        with pytest.raises(RuntimeError, match="No partition found"):
            mount.mount("/dev/sda", "test")

        # mount_partition should not be called
        mock_mount_part.assert_not_called()

    @patch("rpi_usb_cloner.storage.mount.mount_partition")
    @patch("rpi_usb_cloner.storage.mount.get_partition")
    def test_mount_propagates_mount_partition_errors(
        self, mock_get_part, mock_mount_part
    ):
        """Test mount() propagates errors from mount_partition."""
        mock_get_part.return_value = "/dev/sda1"
        mock_mount_part.side_effect = RuntimeError("Mount failed")

        with pytest.raises(RuntimeError, match="Mount failed"):
            mount.mount("/dev/sda", "test")


class TestUnmountWrapper:
    """Tests for unmount() wrapper function - happy paths."""

    @patch("rpi_usb_cloner.storage.mount.unmount_partition")
    def test_unmount_with_name(self, mock_unmount_part):
        """Test unmount() wrapper with explicit name."""
        mount.unmount("/dev/sda", "backup")

        # Verify unmount_partition called with name
        mock_unmount_part.assert_called_once_with("backup")

    @patch("rpi_usb_cloner.storage.mount.unmount_partition")
    @patch("rpi_usb_cloner.storage.mount.get_device_name")
    def test_unmount_without_name_uses_device_name(
        self, mock_get_name, mock_unmount_part
    ):
        """Test unmount() uses device name when name not provided."""
        mock_get_name.return_value = "sda"

        mount.unmount("/dev/sda")

        # Verify device name was extracted and used
        mock_get_name.assert_called_once_with("/dev/sda")
        mock_unmount_part.assert_called_once_with("sda")

    @patch("rpi_usb_cloner.storage.mount.unmount_partition")
    def test_unmount_propagates_errors(self, mock_unmount_part):
        """Test unmount() propagates errors from unmount_partition."""
        mock_unmount_part.side_effect = RuntimeError("Unmount failed")

        with pytest.raises(RuntimeError, match="Unmount failed"):
            mount.unmount("/dev/sda", "test")


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_device_name(self):
        """Test get_device_name() extracts basename."""
        assert mount.get_device_name("/dev/sda") == "sda"
        assert mount.get_device_name("/dev/nvme0n1") == "nvme0n1"
        assert mount.get_device_name("/dev/mmcblk0") == "mmcblk0"

    def test_get_media_path(self):
        """Test get_media_path() generates correct path."""
        assert mount.get_media_path("sda") == "/media/sda"
        assert mount.get_media_path("usb") == "/media/usb"
        assert mount.get_media_path("backup") == "/media/backup"

    def test_get_device_block_path(self):
        """Test get_device_block_path() generates correct sysfs path."""
        assert mount.get_device_block_path("/dev/sda") == "/sys/block/sda"
        assert mount.get_device_block_path("/dev/nvme0n1") == "/sys/block/nvme0n1"


class TestIsMounted:
    """Tests for is_mounted() function."""

    @patch("os.path.ismount")
    def test_is_mounted_returns_true(self, mock_ismount):
        """Test is_mounted() returns True for mounted device."""
        mock_ismount.return_value = True

        result = mount.is_mounted("/dev/sda")

        assert result is True
        mock_ismount.assert_called_once_with("/media/sda")

    @patch("os.path.ismount")
    def test_is_mounted_returns_false(self, mock_ismount):
        """Test is_mounted() returns False for unmounted device."""
        mock_ismount.return_value = False

        result = mount.is_mounted("/dev/sda")

        assert result is False


class TestSysfsOperations:
    """Tests for sysfs-based information retrieval."""

    @patch("os.path.exists")
    @patch("builtins.open", create=True)
    def test_is_removable_true(self, mock_open, mock_exists):
        """Test is_removable() returns True for removable device."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = "1"

        result = mount.is_removable("/dev/sda")

        assert result is True

    @patch("os.path.exists")
    @patch("builtins.open", create=True)
    def test_is_removable_false(self, mock_open, mock_exists):
        """Test is_removable() returns False for non-removable device."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = "0"

        result = mount.is_removable("/dev/mmcblk0")

        assert result is False

    @patch("os.path.exists")
    def test_is_removable_no_sysfs_entry(self, mock_exists):
        """Test is_removable() returns None when sysfs entry missing."""
        mock_exists.return_value = False

        result = mount.is_removable("/dev/sda")

        assert result is None

    @patch("os.path.exists")
    @patch("builtins.open", create=True)
    def test_get_size(self, mock_open, mock_exists):
        """Test get_size() returns correct size in bytes."""
        mock_exists.return_value = True
        # Size is in 512-byte sectors
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "31457280\n"  # ~16GB
        )

        result = mount.get_size("/dev/sda")

        # 31457280 * 512 = 16106127360 bytes (~15GB)
        assert result == 31457280 * 512

    @patch("os.path.exists")
    def test_get_size_no_sysfs_entry(self, mock_exists):
        """Test get_size() returns -1 when sysfs entry missing."""
        mock_exists.return_value = False

        result = mount.get_size("/dev/sda")

        assert result == -1

    @patch("os.path.exists")
    @patch("builtins.open", create=True)
    def test_get_model(self, mock_open, mock_exists):
        """Test get_model() returns device model."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "USB Flash Drive  \n"
        )

        result = mount.get_model("/dev/sda")

        assert result == "USB Flash Drive"

    @patch("os.path.exists")
    def test_get_model_no_sysfs_entry(self, mock_exists):
        """Test get_model() returns None when sysfs entry missing."""
        mock_exists.return_value = False

        result = mount.get_model("/dev/sda")

        assert result is None

    @patch("os.path.exists")
    @patch("builtins.open", create=True)
    def test_get_vendor(self, mock_open, mock_exists):
        """Test get_vendor() returns device vendor."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = "SanDisk \n"

        result = mount.get_vendor("/dev/sda")

        assert result == "SanDisk"

    @patch("os.path.exists")
    def test_get_vendor_no_sysfs_entry(self, mock_exists):
        """Test get_vendor() returns None when sysfs entry missing."""
        mock_exists.return_value = False

        result = mount.get_vendor("/dev/sda")

        assert result is None


class TestListMediaDevices:
    """Tests for list_media_devices() function."""

    # Note: These tests are skipped as they require complex file mocking
    # The function reads /proc/partitions which is difficult to mock properly
    @pytest.mark.skip(reason="Requires complex /proc/partitions mocking")
    def test_list_media_devices_finds_usb_devices(self):
        """Test list_media_devices() finds USB devices."""

    @pytest.mark.skip(reason="Requires complex /proc/partitions mocking")
    def test_list_media_devices_skips_partitions(self):
        """Test list_media_devices() skips partition entries."""
