"""Tests for device verification using SHA256 checksums."""
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from rpi_usb_cloner.storage.clone.verification import (
    compute_sha256,
    verify_clone,
    verify_clone_device,
)


class TestComputeSha256:
    """Tests for compute_sha256 function."""

    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    @patch("rpi_usb_cloner.storage.clone.verification.shutil.which")
    @patch("rpi_usb_cloner.storage.clone.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clone.verification.time.time")
    def test_compute_checksum_success(self, mock_time, mock_popen, mock_which, mock_display):
        """Test successful checksum computation."""
        mock_which.side_effect = lambda x: f"/usr/bin/{x}"
        mock_time.side_effect = [0, 1, 2, 3]

        # Mock dd process
        dd_proc = Mock()
        dd_proc.returncode = 0
        dd_proc.poll.side_effect = [None, 0]
        dd_proc.stderr.readline.side_effect = ["12345678 bytes\n", ""]
        dd_proc.stderr.read.return_value = ""
        dd_proc.wait.return_value = None

        # Mock sha256sum process
        sha_proc = Mock()
        sha_proc.returncode = 0
        sha_proc.communicate.return_value = (
            "abc123def456 -\n",
            "",
        )

        mock_popen.side_effect = [dd_proc, sha_proc]

        checksum = compute_sha256("/dev/sdb", total_bytes=100000000)

        assert checksum == "abc123def456"
        # Verify display was updated
        assert mock_display.call_count > 0

    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    @patch("rpi_usb_cloner.storage.clone.verification.shutil.which")
    @patch("rpi_usb_cloner.storage.clone.verification.subprocess.Popen")
    def test_compute_checksum_no_tools(self, mock_popen, mock_which, mock_display):
        """Test checksum computation fails when tools are missing."""
        mock_which.return_value = None

        with pytest.raises(RuntimeError, match="dd or sha256sum not found"):
            compute_sha256("/dev/sdb")

    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    @patch("rpi_usb_cloner.storage.clone.verification.shutil.which")
    @patch("rpi_usb_cloner.storage.clone.verification.subprocess.Popen")
    def test_compute_checksum_dd_failure(self, mock_popen, mock_which, mock_display):
        """Test checksum computation fails when dd fails."""
        mock_which.side_effect = lambda x: f"/usr/bin/{x}"

        dd_proc = Mock()
        dd_proc.returncode = 1
        dd_proc.poll.return_value = 1
        dd_proc.stderr.readline.return_value = ""
        dd_proc.stderr.read.return_value = "dd: error reading '/dev/sdb': Input/output error"
        dd_proc.wait.return_value = None

        sha_proc = Mock()
        sha_proc.returncode = 0
        sha_proc.communicate.return_value = ("", "")

        mock_popen.side_effect = [dd_proc, sha_proc]

        with pytest.raises(RuntimeError, match="Input/output error"):
            compute_sha256("/dev/sdb")

    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    @patch("rpi_usb_cloner.storage.clone.verification.shutil.which")
    @patch("rpi_usb_cloner.storage.clone.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clone.verification.time.time")
    def test_compute_checksum_sha_failure(self, mock_time, mock_popen, mock_which, mock_display):
        """Test checksum computation fails when sha256sum fails."""
        mock_which.side_effect = lambda x: f"/usr/bin/{x}"
        mock_time.return_value = 0

        dd_proc = Mock()
        dd_proc.returncode = 0
        dd_proc.poll.return_value = 0
        dd_proc.stderr.readline.return_value = ""
        dd_proc.stderr.read.return_value = ""
        dd_proc.wait.return_value = None

        sha_proc = Mock()
        sha_proc.returncode = 1
        sha_proc.communicate.return_value = ("", "sha256sum: error")

        mock_popen.side_effect = [dd_proc, sha_proc]

        with pytest.raises(RuntimeError, match="sha256sum"):
            compute_sha256("/dev/sdb")

    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    @patch("rpi_usb_cloner.storage.clone.verification.shutil.which")
    @patch("rpi_usb_cloner.storage.clone.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clone.verification.time.time")
    def test_compute_checksum_with_size_limit(self, mock_time, mock_popen, mock_which, mock_display):
        """Test checksum computation with byte limit."""
        mock_which.side_effect = lambda x: f"/usr/bin/{x}"
        mock_time.return_value = 0

        dd_proc = Mock()
        dd_proc.returncode = 0
        dd_proc.poll.return_value = 0
        dd_proc.stderr.readline.return_value = ""
        dd_proc.wait.return_value = None

        sha_proc = Mock()
        sha_proc.returncode = 0
        sha_proc.communicate.return_value = ("abc123 -\n", "")

        mock_popen.side_effect = [dd_proc, sha_proc]

        compute_sha256("/dev/sdb", total_bytes=1000000)

        # Verify dd command includes count and iflag
        dd_call = mock_popen.call_args_list[0]
        dd_command = dd_call[0][0]
        assert "count=1000000" in dd_command
        assert "iflag=count_bytes" in dd_command

    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    @patch("rpi_usb_cloner.storage.clone.verification.shutil.which")
    @patch("rpi_usb_cloner.storage.clone.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clone.verification.time.time")
    def test_compute_checksum_progress_display(self, mock_time, mock_popen, mock_which, mock_display):
        """Test progress display during checksum computation."""
        mock_which.side_effect = lambda x: f"/usr/bin/{x}"
        mock_time.side_effect = [0, 1, 2, 3, 4, 10]  # Trigger timeout display

        dd_proc = Mock()
        dd_proc.returncode = 0
        dd_proc.poll.side_effect = [None, None, 0]
        dd_proc.stderr.readline.side_effect = ["10000000 bytes\n", "", ""]
        dd_proc.wait.return_value = None

        sha_proc = Mock()
        sha_proc.returncode = 0
        sha_proc.communicate.return_value = ("abc123 -\n", "")

        mock_popen.side_effect = [dd_proc, sha_proc]

        compute_sha256("/dev/sdb", total_bytes=100000000, title="TEST")

        # Check that progress was displayed with percentage
        display_calls = mock_display.call_args_list
        progress_calls = [c for c in display_calls if "10.0%" in str(c) or "Working" in str(c)]
        assert len(progress_calls) > 0


class TestVerifyCloneDevice:
    """Tests for verify_clone_device function."""

    @patch("rpi_usb_cloner.storage.clone.verification.compute_sha256")
    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    def test_verify_success(self, mock_display, mock_compute):
        """Test successful device verification."""
        mock_compute.side_effect = ["abc123", "abc123"]

        result = verify_clone_device("/dev/sda", "/dev/sdb", total_bytes=100000000)

        assert result is True
        assert mock_compute.call_count == 2
        # Verify both source and destination were checked
        calls = mock_compute.call_args_list
        assert calls[0][0][0] == "/dev/sda"
        assert calls[1][0][0] == "/dev/sdb"

    @patch("rpi_usb_cloner.storage.clone.verification.compute_sha256")
    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    def test_verify_mismatch(self, mock_display, mock_compute):
        """Test verification failure on checksum mismatch."""
        mock_compute.side_effect = ["abc123", "def456"]

        result = verify_clone_device("/dev/sda", "/dev/sdb")

        assert result is False
        # Check error was displayed
        error_calls = [c for c in mock_display.call_args_list if "Mismatch" in str(c)]
        assert len(error_calls) > 0

    @patch("rpi_usb_cloner.storage.clone.verification.compute_sha256")
    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    def test_verify_compute_error(self, mock_display, mock_compute):
        """Test verification failure on computation error."""
        mock_compute.side_effect = RuntimeError("I/O error")

        result = verify_clone_device("/dev/sda", "/dev/sdb")

        assert result is False
        # Check error was displayed
        error_calls = [c for c in mock_display.call_args_list if "Error" in str(c)]
        assert len(error_calls) > 0


class TestVerifyClone:
    """Tests for verify_clone function."""

    @pytest.fixture
    def mock_devices(self):
        """Create mock source and target devices."""
        source = {
            "name": "sda",
            "size": 32000000000,
        }
        target = {
            "name": "sdb",
            "size": 32000000000,
        }
        return source, target

    @pytest.fixture
    def mock_partitions(self):
        """Create mock partitions."""
        source_parts = [
            {"name": "sda1", "type": "part", "size": 10000000000},
            {"name": "sda2", "type": "part", "size": 20000000000},
        ]
        target_parts = [
            {"name": "sdb1", "type": "part", "size": 10000000000},
            {"name": "sdb2", "type": "part", "size": 20000000000},
        ]
        return source_parts, target_parts

    @patch("rpi_usb_cloner.storage.clone.verification.get_children")
    @patch("rpi_usb_cloner.storage.clone.verification.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.verification.compute_sha256")
    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    def test_verify_partition_based_clone(self, mock_display, mock_compute, mock_get_device, mock_get_children, mock_devices, mock_partitions):
        """Test verification of partition-based clone."""
        source, target = mock_devices
        source_parts, target_parts = mock_partitions

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]
        # All checksums match
        mock_compute.side_effect = ["hash1", "hash1", "hash2", "hash2"]

        result = verify_clone(source, target)

        assert result is True
        # Should verify both partitions (2 source + 2 target = 4 calls)
        assert mock_compute.call_count == 4

    @patch("rpi_usb_cloner.storage.clone.verification.get_children")
    @patch("rpi_usb_cloner.storage.clone.verification.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.verification.compute_sha256")
    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    def test_verify_partition_mismatch(self, mock_display, mock_compute, mock_get_device, mock_get_children, mock_devices, mock_partitions):
        """Test verification fails when partition checksums don't match."""
        source, target = mock_devices
        source_parts, target_parts = mock_partitions

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]
        # Second partition doesn't match
        mock_compute.side_effect = ["hash1", "hash1", "hash2", "hash3"]

        result = verify_clone(source, target)

        assert result is False

    @patch("rpi_usb_cloner.storage.clone.verification.get_children")
    @patch("rpi_usb_cloner.storage.clone.verification.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.verification.verify_clone_device")
    def test_verify_raw_clone_no_partitions(self, mock_verify_device, mock_get_device, mock_get_children, mock_devices):
        """Test verification of raw clone without partitions."""
        source, target = mock_devices

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [[], []]  # No partitions
        mock_verify_device.return_value = True

        result = verify_clone(source, target)

        assert result is True
        # Should fall back to device-level verification
        mock_verify_device.assert_called_once_with("/dev/sda", "/dev/sdb", 32000000000)

    @patch("rpi_usb_cloner.storage.clone.verification.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.verification.verify_clone_device")
    def test_verify_string_paths(self, mock_verify_device, mock_get_device):
        """Test verification with string device paths."""
        mock_get_device.return_value = None
        mock_verify_device.return_value = True

        result = verify_clone("/dev/sda", "/dev/sdb")

        assert result is True
        mock_verify_device.assert_called_once_with("/dev/sda", "/dev/sdb", None)

    @patch("rpi_usb_cloner.storage.clone.verification.get_children")
    @patch("rpi_usb_cloner.storage.clone.verification.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.verification.compute_sha256")
    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    def test_verify_missing_target_partition(self, mock_display, mock_compute, mock_get_device, mock_get_children, mock_devices):
        """Test verification fails when target partition is missing."""
        source, target = mock_devices
        source_parts = [
            {"name": "sda1", "type": "part", "size": 10000000000},
            {"name": "sda2", "type": "part", "size": 20000000000},
        ]
        target_parts = [
            {"name": "sdb1", "type": "part", "size": 10000000000},
            # Missing sdb2
        ]

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]

        result = verify_clone(source, target)

        assert result is False
        # Check error was displayed
        error_calls = [c for c in mock_display.call_args_list if "No target part" in str(c)]
        assert len(error_calls) > 0

    @patch("rpi_usb_cloner.storage.clone.verification.get_children")
    @patch("rpi_usb_cloner.storage.clone.verification.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.verification.compute_sha256")
    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    def test_verify_partition_number_matching(self, mock_display, mock_compute, mock_get_device, mock_get_children, mock_devices):
        """Test partition matching by partition number."""
        source, target = mock_devices
        # Non-sequential partition numbers
        source_parts = [
            {"name": "sda1", "type": "part", "size": 10000000000},
            {"name": "sda5", "type": "part", "size": 20000000000},  # Partition 5
        ]
        target_parts = [
            {"name": "sdb1", "type": "part", "size": 10000000000},
            {"name": "sdb5", "type": "part", "size": 20000000000},  # Partition 5
        ]

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]
        mock_compute.side_effect = ["hash1", "hash1", "hash5", "hash5"]

        result = verify_clone(source, target)

        assert result is True
        # Verify sda5 was matched with sdb5, not sdb2
        calls = mock_compute.call_args_list
        # Should verify sda1, sdb1, sda5, sdb5
        assert "/dev/sda5" in str(calls[2])
        assert "/dev/sdb5" in str(calls[3])

    @patch("rpi_usb_cloner.storage.clone.verification.get_children")
    @patch("rpi_usb_cloner.storage.clone.verification.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.verification.compute_sha256")
    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    def test_verify_nvme_partition_names(self, mock_display, mock_compute, mock_get_device, mock_get_children):
        """Test verification with NVMe partition naming (p1, p2)."""
        source = {"name": "nvme0n1", "size": 32000000000}
        target = {"name": "nvme1n1", "size": 32000000000}
        source_parts = [
            {"name": "nvme0n1p1", "type": "part", "size": 10000000000},
            {"name": "nvme0n1p2", "type": "part", "size": 20000000000},
        ]
        target_parts = [
            {"name": "nvme1n1p1", "type": "part", "size": 10000000000},
            {"name": "nvme1n1p2", "type": "part", "size": 20000000000},
        ]

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]
        mock_compute.side_effect = ["hash1", "hash1", "hash2", "hash2"]

        result = verify_clone(source, target)

        assert result is True
        # Verify correct partition matching
        assert mock_compute.call_count == 4

    @patch("rpi_usb_cloner.storage.clone.verification.get_children")
    @patch("rpi_usb_cloner.storage.clone.verification.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.verification.compute_sha256")
    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    def test_verify_computation_error(self, mock_display, mock_compute, mock_get_device, mock_get_children, mock_devices, mock_partitions):
        """Test verification handles computation errors gracefully."""
        source, target = mock_devices
        source_parts, target_parts = mock_partitions

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]
        mock_compute.side_effect = RuntimeError("I/O error reading device")

        result = verify_clone(source, target)

        assert result is False
        # Check error was displayed
        error_calls = [c for c in mock_display.call_args_list if "Error" in str(c)]
        assert len(error_calls) > 0
