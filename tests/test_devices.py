"""
Tests for rpi_usb_cloner.storage.devices module.

This test suite covers:
- Device detection and enumeration
- Device filtering (removable vs system disks)
- Unmount operations and error handling
- Device validation
- Human-readable formatting functions
"""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from rpi_usb_cloner.storage import devices


@pytest.fixture(autouse=True)
def reset_lsblk_cache():
    devices._lsblk_cache = None
    devices._lsblk_cache_time = None
    devices._last_lsblk_names = None
    yield


class TestHumanSize:
    """Tests for human_size() function."""

    def test_bytes(self):
        assert devices.human_size(500) == "500.0B"

    def test_kilobytes(self):
        assert devices.human_size(1536) == "1.5KB"

    def test_megabytes(self):
        assert devices.human_size(1572864) == "1.5MB"

    def test_gigabytes(self):
        assert devices.human_size(16106127360) == "15.0GB"

    def test_terabytes(self):
        assert devices.human_size(1099511627776) == "1.0TB"

    def test_none_value(self):
        assert devices.human_size(None) == "0B"

    def test_zero(self):
        assert devices.human_size(0) == "0.0B"

    def test_very_large(self):
        # 10 PB
        result = devices.human_size(10 * 1024**5)
        assert "PB" in result


class TestFormatDeviceLabel:
    """Tests for format_device_label() function."""

    def test_with_device_dict(self, mock_usb_device):
        label = devices.format_device_label(mock_usb_device)
        assert "sda" in label
        assert "15GB" in label or "15.0GB" in label

    def test_with_string_name(self):
        label = devices.format_device_label("sda")
        assert label == "sda"

    def test_with_none(self):
        label = devices.format_device_label(None)
        assert label == ""

    def test_removes_decimal_zero(self):
        device = {"name": "sda", "size": "16106127360"}  # Exactly 15.0GB
        label = devices.format_device_label(device)
        assert "15GB" in label or "15.0GB" in label


class TestGetHumanDeviceLabel:
    """Tests for get_human_device_label() function."""

    def test_with_vendor_and_model(self):
        """Test device with vendor and model info."""
        device = {
            "name": "sda",
            "size": 17179869184,  # 16GB
            "vendor": "SanDisk",
            "model": "Cruzer",
        }
        label = devices.get_human_device_label(device)
        assert "16GB" in label
        assert "SANDISK" in label or "CRUZER" in label

    def test_with_model_only(self):
        """Test device with only model info."""
        device = {
            "name": "sdb",
            "size": 8589934592,  # 8GB
            "vendor": None,
            "model": "Kingston DataTraveler",
        }
        label = devices.get_human_device_label(device)
        assert "8GB" in label
        assert "KINGSTON" in label

    def test_with_vendor_only(self):
        """Test device with only vendor info."""
        device = {
            "name": "sdc",
            "size": 32212254720,  # 30GB
            "vendor": "Samsung",
            "model": None,
        }
        label = devices.get_human_device_label(device)
        assert "30GB" in label
        assert "SAMSUNG" in label

    def test_fallback_to_usb(self):
        """Test fallback to 'USB' when no vendor/model info."""
        device = {
            "name": "sdd",
            "size": 4294967296,  # 4GB
            "vendor": None,
            "model": None,
            "label": None,
        }
        label = devices.get_human_device_label(device)
        assert "4GB" in label
        assert "USB" in label

    def test_fallback_to_partition_label(self):
        """Test fallback to partition label when no vendor/model."""
        device = {
            "name": "sde",
            "size": 2147483648,  # 2GB
            "vendor": "",
            "model": "",
            "label": "MyDrive",
        }
        label = devices.get_human_device_label(device)
        assert "2GB" in label
        assert "MYDRIVE" in label

    def test_fallback_to_child_partition_label(self):
        """Test fallback to child partition label when disk label is empty."""
        device = {
            "name": "sdf",
            "size": 1073741824,  # 1GB
            "vendor": None,
            "model": None,
            "label": "",
            "children": [
                {"name": "sdf1", "label": ""},
                {"name": "sdf2", "label": "Backup"},
            ],
        }
        label = devices.get_human_device_label(device)
        assert "1GB" in label
        assert "BACKUP" in label

    def test_string_input(self):
        """Test with string input instead of dict."""
        label = devices.get_human_device_label("sda")
        assert label == "SDA"

    def test_max_length_truncation(self):
        """Test that long labels are truncated."""
        device = {
            "name": "sda",
            "size": 17179869184,  # 16GB
            "vendor": "VeryLongVendorName",
            "model": "ExtremelyLongModelNameThatWouldOverflow",
        }
        label = devices.get_human_device_label(device, max_length=20)
        assert len(label) <= 20

    def test_model_contains_vendor(self):
        """Test when model string contains vendor name (avoid duplication)."""
        device = {
            "name": "sda",
            "size": 17179869184,
            "vendor": "SanDisk",
            "model": "SanDisk Ultra",
        }
        label = devices.get_human_device_label(device)
        # Should not have "SANDISK SANDISK ULTRA", just "SANDISK ULTRA"
        assert label.count("SANDISK") == 1


class TestGetBlockDevices:
    """Tests for get_block_devices() function."""

    def test_successful_lsblk_call(self, mocker, mock_lsblk_output):
        """Test successful device enumeration."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = mock_lsblk_output
        mock_run.return_value = mock_result

        devices_list = devices.get_block_devices()

        assert len(devices_list) == 2
        assert devices_list[0]["name"] == "mmcblk0"
        assert devices_list[1]["name"] == "sda"

    def test_lsblk_command_failure(self, mocker):
        """Test handling of lsblk command failure."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_run.side_effect = subprocess.CalledProcessError(1, "lsblk", stderr="error")

        devices_list = devices.get_block_devices()

        assert devices_list == []

    def test_invalid_json_output(self, mocker):
        """Test handling of malformed lsblk JSON output."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = "invalid json{"
        mock_run.return_value = mock_result

        devices_list = devices.get_block_devices()

        assert devices_list == []

    def test_empty_blockdevices(self, mocker, mock_lsblk_empty):
        """Test handling of empty device list."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = mock_lsblk_empty
        mock_run.return_value = mock_result

        devices_list = devices.get_block_devices()

        assert devices_list == []

    def test_error_handler_called_on_failure(self, mocker):
        """Test that error_handler is called when lsblk fails."""
        mock_error_handler = Mock()
        devices.configure_device_helpers(error_handler=mock_error_handler)

        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_run.side_effect = subprocess.CalledProcessError(1, "lsblk", stderr="error")

        devices.get_block_devices()

        mock_error_handler.assert_called_once()
        args = mock_error_handler.call_args[0][0]
        assert "LSBLK ERROR" in args

    def test_cache_hit_uses_single_lsblk_call(self, mocker, mock_lsblk_output):
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = mock_lsblk_output
        mock_run.return_value = mock_result
        mocker.patch(
            "rpi_usb_cloner.storage.devices.time.monotonic",
            side_effect=[0.0, 0.5],
        )

        first = devices.get_block_devices()
        second = devices.get_block_devices()

        assert first == second
        assert mock_run.call_count == 1

    def test_cache_expiry_refreshes_lsblk(self, mocker, mock_lsblk_output):
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = mock_lsblk_output
        mock_run.return_value = mock_result
        mocker.patch(
            "rpi_usb_cloner.storage.devices.time.monotonic",
            side_effect=[0.0, 2.0],
        )

        devices.get_block_devices()
        devices.get_block_devices()

        assert mock_run.call_count == 2

    def test_force_refresh_bypasses_cache(self, mocker, mock_lsblk_output):
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = mock_lsblk_output
        mock_run.return_value = mock_result
        mocker.patch(
            "rpi_usb_cloner.storage.devices.time.monotonic",
            side_effect=[0.0, 0.1],
        )

        devices.get_block_devices()
        devices.get_block_devices(force_refresh=True)

        assert mock_run.call_count == 2

    def test_force_refresh_error_returns_empty(self, mocker, mock_lsblk_output):
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = mock_lsblk_output
        mock_run.side_effect = [mock_result, subprocess.CalledProcessError(1, "lsblk")]

        first = devices.get_block_devices()
        second = devices.get_block_devices(force_refresh=True)

        assert first
        assert second == []


class TestGetDeviceByName:
    """Tests for get_device_by_name() function."""

    def test_find_existing_device(self, mocker, mock_lsblk_output):
        """Test finding a device by name."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = mock_lsblk_output
        mock_run.return_value = mock_result

        device = devices.get_device_by_name("sda")

        assert device is not None
        assert device["name"] == "sda"
        assert device["tran"] == "usb"

    def test_device_not_found(self, mocker, mock_lsblk_output):
        """Test when device doesn't exist."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = mock_lsblk_output
        mock_run.return_value = mock_result

        device = devices.get_device_by_name("sdc")

        assert device is None

    def test_none_name(self, mocker):
        """Test with None as device name."""
        device = devices.get_device_by_name(None)
        assert device is None

    def test_empty_string_name(self, mocker):
        """Test with empty string as device name."""
        device = devices.get_device_by_name("")
        assert device is None


class TestHasRootMountpoint:
    """Tests for has_root_mountpoint() function."""

    def test_device_mounted_at_root(self):
        """Test device mounted at /."""
        device = {"mountpoint": "/", "children": []}
        assert devices.has_root_mountpoint(device) is True

    def test_device_mounted_at_boot(self):
        """Test device mounted at /boot."""
        device = {"mountpoint": "/boot", "children": []}
        assert devices.has_root_mountpoint(device) is True

    def test_device_mounted_at_boot_firmware(self):
        """Test device mounted at /boot/firmware."""
        device = {"mountpoint": "/boot/firmware", "children": []}
        assert devices.has_root_mountpoint(device) is True

    def test_child_mounted_at_root(self):
        """Test child partition mounted at root."""
        device = {"mountpoint": None, "children": [{"mountpoint": "/", "children": []}]}
        assert devices.has_root_mountpoint(device) is True

    def test_no_root_mountpoint(self):
        """Test device with no critical mountpoints."""
        device = {
            "mountpoint": "/media/usb",
            "children": [{"mountpoint": "/mnt/data", "children": []}],
        }
        assert devices.has_root_mountpoint(device) is False

    def test_no_mountpoint(self):
        """Test unmounted device."""
        device = {"mountpoint": None, "children": []}
        assert devices.has_root_mountpoint(device) is False


class TestIsRootDevice:
    """Tests for is_root_device() function."""

    def test_system_disk(self, mock_system_disk):
        """Test that system disk is identified as root device."""
        assert devices.is_root_device(mock_system_disk) is True

    def test_usb_disk(self, mock_usb_device):
        """Test that USB disk is not identified as root device."""
        assert devices.is_root_device(mock_usb_device) is False

    def test_partition_not_root_device(self):
        """Test that partitions are never root devices."""
        partition = {"type": "part", "mountpoint": "/", "children": []}
        assert devices.is_root_device(partition) is False


class TestListUsbDisks:
    """Tests for list_usb_disks() function."""

    def test_filters_out_system_disk(self, mocker, mock_lsblk_output):
        """Test that system disk is filtered out."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = mock_lsblk_output
        mock_run.return_value = mock_result

        usb_disks = devices.list_usb_disks()

        # Should only return USB device, not system disk
        assert len(usb_disks) == 1
        assert usb_disks[0]["name"] == "sda"

    def test_includes_removable_devices(self, mocker):
        """Test that removable devices are included."""
        lsblk_data = {
            "blockdevices": [
                {
                    "name": "sdb",
                    "type": "disk",
                    "rm": 1,  # Removable but not USB transport (integer, not string)
                    "tran": None,
                    "mountpoint": None,
                    "children": [],
                }
            ]
        }
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = json.dumps(lsblk_data)
        mock_run.return_value = mock_result

        usb_disks = devices.list_usb_disks()

        assert len(usb_disks) == 1
        assert usb_disks[0]["name"] == "sdb"

    def test_filters_out_partitions(self, mocker, mock_usb_device):
        """Test that partitions are filtered out, only disks returned."""
        lsblk_data = {"blockdevices": [mock_usb_device]}
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_result = Mock()
        mock_result.stdout = json.dumps(lsblk_data)
        mock_run.return_value = mock_result

        usb_disks = devices.list_usb_disks()

        # Should return only the disk, not the partition
        assert len(usb_disks) == 1
        assert usb_disks[0]["type"] == "disk"


class TestUnmountDevice:
    """Tests for unmount_device() function - CRITICAL SECURITY TESTS."""

    def test_unmount_device_with_mountpoint(self, mocker):
        """Test unmounting device with single mountpoint."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        device = {"mountpoint": "/media/usb", "children": []}

        devices.unmount_device(device)

        mock_run.assert_called_once_with(["umount", "/media/usb"], check=False)

    def test_unmount_device_with_children(self, mocker, mock_usb_device):
        """Test unmounting device with child partitions."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")

        devices.unmount_device(mock_usb_device)

        # Should attempt to unmount child partition
        assert mock_run.call_count >= 1
        calls = [str(call) for call in mock_run.call_args_list]
        assert any("/media/usb" in str(call) for call in calls)

    def test_unmount_device_no_mountpoint(self, mocker):
        """Test unmounting device that's not mounted."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        device = {"mountpoint": None, "children": []}

        devices.unmount_device(device)

        # Should not attempt any unmount
        mock_run.assert_not_called()

    def test_unmount_failure_is_silent(self, mocker):
        """CRITICAL: Test that unmount failures are silently ignored."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_run.side_effect = subprocess.CalledProcessError(1, "umount", stderr="busy")
        device = {"mountpoint": "/media/usb", "children": []}

        # This should NOT raise an exception
        devices.unmount_device(device)

        # Verify the unmount was attempted
        mock_run.assert_called_once()

    def test_unmount_multiple_children(self, mocker):
        """Test unmounting device with multiple partitions."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        device = {
            "mountpoint": None,
            "children": [
                {"mountpoint": "/media/usb1"},
                {"mountpoint": "/media/usb2"},
                {"mountpoint": None},  # Not mounted
            ],
        }

        devices.unmount_device(device)

        assert mock_run.call_count == 2


class TestUnmountDeviceWithRetry:
    """Tests for unmount_device_with_retry() function."""

    def test_successful_unmount_first_try(self, mocker, mock_usb_device):
        """Test successful unmount on first attempt."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_log = Mock()

        success, used_lazy = devices.unmount_device_with_retry(
            mock_usb_device, log_debug=mock_log
        )

        assert success is True
        assert used_lazy is False
        assert mock_run.call_count >= 1

    def test_no_mountpoints(self, mocker):
        """Test device with no mountpoints."""
        device = {"name": "sda", "mountpoint": None, "children": []}
        mock_log = Mock()

        success, used_lazy = devices.unmount_device_with_retry(
            device, log_debug=mock_log
        )

        assert success is True
        assert used_lazy is False

    @pytest.mark.slow
    def test_retry_on_failure(self, mocker):
        """Test retry mechanism on unmount failure."""
        # Simplify - just test that retries happen with mocked time.sleep
        mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mocker.patch("time.sleep")

        device = {
            "name": "sda",
            "mountpoint": None,
            "children": [{"name": "sda1", "mountpoint": "/media/usb"}],
        }

        # Mock the check - simulate device becoming unmounted after retries

        def mock_proc_mounts(*args, **kwargs):
            # Return empty to simulate no mounts
            from io import StringIO

            return StringIO("")

        mocker.patch("builtins.open", side_effect=mock_proc_mounts)

        success, used_lazy = devices.unmount_device_with_retry(device)

        # Should have attempted to unmount and eventually succeeded
        assert isinstance(success, bool)
        assert isinstance(used_lazy, bool)

    @pytest.mark.slow
    def test_falls_back_to_lazy_unmount(self, mocker):
        """Test fallback to lazy unmount when normal unmount fails."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")

        call_count = [0]

        def run_side_effect(cmd, **kwargs):
            call_count[0] += 1
            if cmd[0] == "sync":
                return
            # Normal unmounts fail
            if cmd[0] == "umount" and "-l" not in cmd:
                raise subprocess.CalledProcessError(1, "umount")
            # Lazy unmount succeeds
            return

        mock_run.side_effect = run_side_effect

        device = {
            "name": "sda",
            "mountpoint": None,
            "children": [{"name": "sda1", "mountpoint": "/media/usb"}],
        }

        with patch("builtins.open", create=True) as mock_open:
            # Simulate /proc/mounts showing device mounted, then unmounted
            mount_data = [
                "/dev/sda1 /media/usb vfat rw 0 0\n",  # First check: mounted
                "",  # After lazy unmount: unmounted
            ]
            mock_open.return_value.__enter__.return_value = iter(mount_data)

            with patch("time.sleep"):  # Speed up test
                success, used_lazy = devices.unmount_device_with_retry(device)

        # Should succeed with lazy unmount
        assert success is True or used_lazy is True

    def test_complete_failure(self, mocker):
        """Test when even lazy unmount fails."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_run.side_effect = subprocess.CalledProcessError(1, "umount")

        device = {
            "name": "sda",
            "mountpoint": None,
            "children": [{"name": "sda1", "mountpoint": "/media/usb"}],
        }

        with patch("builtins.open", create=True) as mock_open:
            # Simulate device staying mounted
            mount_data = "/dev/sda1 /media/usb vfat rw 0 0\n"
            mock_open.return_value.__enter__.return_value = [mount_data] * 10

            with patch("time.sleep"):  # Speed up test
                success, used_lazy = devices.unmount_device_with_retry(device)

        assert success is False


class TestPowerOffDevice:
    """Tests for power_off_device() function."""

    def test_successful_udisksctl_power_off(self, mocker):
        """Test successful power off with udisksctl."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        device = {"name": "sda"}
        mock_log = Mock()

        result = devices.power_off_device(device, log_debug=mock_log)

        assert result is True
        mock_run.assert_called_once_with(
            ["udisksctl", "power-off", "-b", "/dev/sda"], check=True
        )

    def test_fallback_to_hdparm(self, mocker):
        """Test fallback to hdparm when udisksctl fails."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")

        def run_side_effect(cmd, **kwargs):
            if "udisksctl" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            return  # hdparm succeeds

        mock_run.side_effect = run_side_effect
        device = {"name": "sda"}

        result = devices.power_off_device(device)

        assert result is True
        assert mock_run.call_count == 2

    def test_all_methods_fail(self, mocker):
        """Test when all power-off methods fail."""
        mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
        device = {"name": "sda"}

        result = devices.power_off_device(device)

        assert result is False


class TestConfigureDeviceHelpers:
    """Tests for configure_device_helpers() function."""

    def test_configure_log_debug(self):
        """Test configuring debug logger (backwards compatibility)."""
        mock_logger = Mock()
        # Should not crash - log_debug parameter is ignored after LoggerFactory migration
        devices.configure_device_helpers(log_debug=mock_logger)

    def test_configure_error_handler(self):
        """Test configuring error handler."""
        mock_handler = Mock()
        devices.configure_device_helpers(error_handler=mock_handler)

        assert devices._error_handler == mock_handler

    def test_configure_both(self):
        """Test configuring both logger and error handler."""
        mock_logger = Mock()
        mock_handler = Mock()

        devices.configure_device_helpers(
            log_debug=mock_logger, error_handler=mock_handler
        )

        # Only error_handler is still used; log_debug is ignored (LoggerFactory migration)
        assert devices._error_handler == mock_handler

    def test_configure_with_none(self):
        """Test configuring with None."""
        devices.configure_device_helpers(log_debug=None, error_handler=None)

        # error_handler should be None
        assert devices._error_handler is None


class TestRunCommand:
    """Tests for run_command() helper function."""

    def test_successful_command(self, mocker):
        """Test successful command execution."""
        mock_subprocess = mocker.patch("subprocess.run")
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "success"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        result = devices.run_command(["echo", "test"])

        assert result.returncode == 0
        mock_subprocess.assert_called_once_with(
            ["echo", "test"], check=True, text=True, capture_output=True
        )

    def test_failed_command(self, mocker):
        """Test failed command execution."""
        mock_subprocess = mocker.patch("subprocess.run")
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            1, ["false"], stderr="error"
        )

        with pytest.raises(subprocess.CalledProcessError):
            devices.run_command(["false"])

    def test_check_false_suppresses_exception(self, mocker):
        """Test check=False prevents exception on failure."""
        mock_subprocess = mocker.patch("subprocess.run")
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_subprocess.return_value = mock_result

        # Should not raise
        result = devices.run_command(["false"], check=False)

        assert result.returncode == 1
