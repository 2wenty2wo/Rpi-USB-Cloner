"""Additional tests for Clonezilla verification module.

Tests for coverage gaps in:
- get_verify_hash_timeout() - settings handling
- compute_image_sha256() - compressed images, zstd, timeouts, errors
- compute_partition_sha256() - timeouts, errors
- verify_restored_image() - edge cases, unmount failures, missing partitions
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rpi_usb_cloner.storage.clonezilla import verification


class TestGetVerifyHashTimeout:
    """Tests for get_verify_hash_timeout() function."""

    def test_returns_none_when_setting_none(self):
        """Test returns None when setting value is None."""
        with patch.object(verification.settings, 'get_setting', return_value=None):
            result = verification.get_verify_hash_timeout("verify_image_hash_timeout_seconds")
            assert result is None

    def test_returns_float_when_setting_valid(self):
        """Test returns float when setting value is valid."""
        with patch.object(verification.settings, 'get_setting', return_value="300"):
            result = verification.get_verify_hash_timeout("verify_image_hash_timeout_seconds")
            assert result == 300.0

    def test_returns_none_when_setting_zero(self):
        """Test returns None when setting value is zero."""
        with patch.object(verification.settings, 'get_setting', return_value="0"):
            result = verification.get_verify_hash_timeout("verify_image_hash_timeout_seconds")
            assert result is None

    def test_returns_none_when_setting_negative(self):
        """Test returns None when setting value is negative."""
        with patch.object(verification.settings, 'get_setting', return_value="-10"):
            result = verification.get_verify_hash_timeout("verify_image_hash_timeout_seconds")
            assert result is None

    def test_returns_none_when_setting_invalid_string(self):
        """Test returns None when setting value is not a number."""
        with patch.object(verification.settings, 'get_setting', return_value="invalid"):
            result = verification.get_verify_hash_timeout("verify_image_hash_timeout_seconds")
            assert result is None

    def test_returns_none_when_setting_empty_string(self):
        """Test returns None when setting value is empty string."""
        with patch.object(verification.settings, 'get_setting', return_value=""):
            result = verification.get_verify_hash_timeout("verify_image_hash_timeout_seconds")
            assert result is None


class TestComputeImageSha256Errors:
    """Tests for compute_image_sha256() error handling."""

    def test_raises_when_no_image_files(self):
        """Test raises RuntimeError when image_files is empty."""
        with pytest.raises(RuntimeError, match="No image files"):
            verification.compute_image_sha256([], compressed=False)

    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_raises_when_sha256sum_not_found(self, mock_which, mock_popen, tmp_path):
        """Test raises RuntimeError when sha256sum is not found."""
        mock_which.return_value = None
        image_file = tmp_path / "test.img"
        image_file.write_text("test")

        # Mock cat process since it's started before sha256sum check
        cat_proc = Mock()
        cat_proc.stdout = Mock()
        mock_popen.return_value = cat_proc

        with pytest.raises(RuntimeError, match="sha256sum not found"):
            verification.compute_image_sha256([image_file], compressed=False)

    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_raises_when_cat_fails(self, mock_which, mock_popen, tmp_path):
        """Test raises RuntimeError when cat process fails."""
        mock_which.return_value = "/usr/bin/sha256sum"
        image_file = tmp_path / "test.img"
        image_file.write_text("test")

        cat_proc = Mock()
        cat_proc.stdout = Mock()
        cat_proc.wait.return_value = 0
        cat_proc.returncode = 1  # cat fails

        sha_proc = Mock()
        sha_proc.communicate.return_value = ("abc123  -", "")
        sha_proc.returncode = 0

        mock_popen.side_effect = [cat_proc, sha_proc]

        with pytest.raises(RuntimeError, match="cat failed"):
            verification.compute_image_sha256([image_file], compressed=False)

    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_raises_when_sha256sum_fails(self, mock_which, mock_popen, tmp_path):
        """Test raises RuntimeError when sha256sum process fails."""
        mock_which.return_value = "/usr/bin/sha256sum"
        image_file = tmp_path / "test.img"
        image_file.write_text("test")

        cat_proc = Mock()
        cat_proc.stdout = Mock()
        cat_proc.wait.return_value = 0
        cat_proc.returncode = 0

        sha_proc = Mock()
        sha_proc.communicate.return_value = ("", "checksum error")
        sha_proc.returncode = 1  # sha256sum fails

        mock_popen.side_effect = [cat_proc, sha_proc]

        with pytest.raises(RuntimeError, match="sha256sum failed"):
            verification.compute_image_sha256([image_file], compressed=False)


class TestComputeImageSha256Compressed:
    """Tests for compute_image_sha256() with compressed images."""

    @patch("rpi_usb_cloner.storage.clonezilla.verification.get_compression_type")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_gzip_decompression_with_pigz(
        self, mock_which, mock_popen, mock_get_compression, tmp_path
    ):
        """Test gzip decompression prefers pigz over gzip."""
        mock_get_compression.return_value = "gzip"
        mock_which.side_effect = lambda x: {
            "pigz": "/usr/bin/pigz",
            "gzip": "/usr/bin/gzip",
            "sha256sum": "/usr/bin/sha256sum",
        }.get(x)

        image_file = tmp_path / "test.img"
        image_file.write_text("test")

        cat_proc = Mock()
        cat_stdout = Mock()
        cat_proc.stdout = cat_stdout
        cat_proc.wait.return_value = 0
        cat_proc.returncode = 0

        gzip_proc = Mock()
        gzip_stdout = Mock()
        gzip_proc.stdout = gzip_stdout
        gzip_proc.wait.return_value = 0
        gzip_proc.returncode = 0

        sha_proc = Mock()
        sha_proc.communicate.return_value = ("abc123  -", "")
        sha_proc.returncode = 0

        mock_popen.side_effect = [cat_proc, gzip_proc, sha_proc]

        result = verification.compute_image_sha256([image_file], compressed=True)

        assert result == "abc123"
        # Check pigz was used (first call after cat)
        assert mock_popen.call_args_list[1][0][0][0] == "/usr/bin/pigz"

    @patch("rpi_usb_cloner.storage.clonezilla.verification.get_compression_type")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_gzip_decompression_falls_back_to_gzip(
        self, mock_which, mock_popen, mock_get_compression, tmp_path
    ):
        """Test gzip decompression falls back to gzip when pigz not available."""
        mock_get_compression.return_value = "gzip"
        mock_which.side_effect = lambda x: {
            "pigz": None,
            "gzip": "/usr/bin/gzip",
            "sha256sum": "/usr/bin/sha256sum",
        }.get(x)

        image_file = tmp_path / "test.img"
        image_file.write_text("test")

        cat_proc = Mock()
        cat_stdout = Mock()
        cat_proc.stdout = cat_stdout
        cat_proc.wait.return_value = 0
        cat_proc.returncode = 0

        gzip_proc = Mock()
        gzip_stdout = Mock()
        gzip_proc.stdout = gzip_stdout
        gzip_proc.wait.return_value = 0
        gzip_proc.returncode = 0

        sha_proc = Mock()
        sha_proc.communicate.return_value = ("abc123  -", "")
        sha_proc.returncode = 0

        mock_popen.side_effect = [cat_proc, gzip_proc, sha_proc]

        result = verification.compute_image_sha256([image_file], compressed=True)

        assert result == "abc123"
        assert mock_popen.call_args_list[1][0][0][0] == "/usr/bin/gzip"

    @patch("rpi_usb_cloner.storage.clonezilla.verification.get_compression_type")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_gzip_raises_when_not_found(self, mock_which, mock_popen, mock_get_compression, tmp_path):
        """Test raises RuntimeError when gzip/pigz not found."""
        mock_get_compression.return_value = "gzip"
        mock_which.side_effect = lambda x: {
            "pigz": None,
            "gzip": None,
            "sha256sum": "/usr/bin/sha256sum",
        }.get(x)

        image_file = tmp_path / "test.img"
        image_file.write_text("test")

        # Mock cat process since it's started before gzip check
        cat_proc = Mock()
        cat_stdout = Mock()
        cat_proc.stdout = cat_stdout
        mock_popen.return_value = cat_proc

        with pytest.raises(RuntimeError, match="gzip not found"):
            verification.compute_image_sha256([image_file], compressed=True)

    @patch("rpi_usb_cloner.storage.clonezilla.verification.get_compression_type")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_zstd_decompression_with_pzstd(
        self, mock_which, mock_popen, mock_get_compression, tmp_path
    ):
        """Test zstd decompression prefers pzstd over zstd."""
        mock_get_compression.return_value = "zstd"
        mock_which.side_effect = lambda x: {
            "pzstd": "/usr/bin/pzstd",
            "zstd": "/usr/bin/zstd",
            "sha256sum": "/usr/bin/sha256sum",
        }.get(x)

        image_file = tmp_path / "test.img"
        image_file.write_text("test")

        cat_proc = Mock()
        cat_stdout = Mock()
        cat_proc.stdout = cat_stdout
        cat_proc.wait.return_value = 0
        cat_proc.returncode = 0

        zstd_proc = Mock()
        zstd_stdout = Mock()
        zstd_proc.stdout = zstd_stdout
        zstd_proc.wait.return_value = 0
        zstd_proc.returncode = 0

        sha_proc = Mock()
        sha_proc.communicate.return_value = ("def456  -", "")
        sha_proc.returncode = 0

        mock_popen.side_effect = [cat_proc, zstd_proc, sha_proc]

        result = verification.compute_image_sha256([image_file], compressed=True)

        assert result == "def456"
        assert mock_popen.call_args_list[1][0][0][0] == "/usr/bin/pzstd"

    @patch("rpi_usb_cloner.storage.clonezilla.verification.get_compression_type")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_zstd_raises_when_not_found(self, mock_which, mock_popen, mock_get_compression, tmp_path):
        """Test raises RuntimeError when zstd/pzstd not found."""
        mock_get_compression.return_value = "zstd"
        mock_which.side_effect = lambda x: {
            "pzstd": None,
            "zstd": None,
            "sha256sum": "/usr/bin/sha256sum",
        }.get(x)

        image_file = tmp_path / "test.img"
        image_file.write_text("test")

        # Mock cat process since it's started before zstd check
        cat_proc = Mock()
        cat_stdout = Mock()
        cat_proc.stdout = cat_stdout
        mock_popen.return_value = cat_proc

        with pytest.raises(RuntimeError, match="zstd not found"):
            verification.compute_image_sha256([image_file], compressed=True)


class TestComputeImageSha256Timeout:
    """Tests for compute_image_sha256() timeout handling."""

    @patch("rpi_usb_cloner.storage.clonezilla.verification.get_verify_hash_timeout")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_raises_on_timeout(
        self, mock_which, mock_popen, mock_get_timeout, tmp_path
    ):
        """Test raises RuntimeError when computation times out."""
        mock_which.return_value = "/usr/bin/sha256sum"
        mock_get_timeout.return_value = 30.0

        image_file = tmp_path / "test.img"
        image_file.write_text("test")

        cat_proc = Mock()
        cat_stdout = Mock()
        cat_proc.stdout = cat_stdout
        cat_proc.returncode = 0

        sha_proc = Mock()
        from subprocess import TimeoutExpired
        sha_proc.communicate.side_effect = TimeoutExpired("sha256sum", 30.0)

        mock_popen.side_effect = [cat_proc, sha_proc]

        with pytest.raises(RuntimeError, match="timed out"):
            verification.compute_image_sha256([image_file], compressed=False)

        # Verify processes were killed
        sha_proc.kill.assert_called()
        cat_proc.kill.assert_called()


class TestComputePartitionSha256:
    """Tests for compute_partition_sha256() function."""

    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_raises_when_dd_not_found(self, mock_which):
        """Test raises RuntimeError when dd not found."""
        mock_which.side_effect = lambda x: {
            "dd": None,
            "sha256sum": "/usr/bin/sha256sum",
        }.get(x)

        with pytest.raises(RuntimeError, match="dd or sha256sum not found"):
            verification.compute_partition_sha256("/dev/sda1")

    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_raises_when_sha256sum_not_found_for_partition(self, mock_which):
        """Test raises RuntimeError when sha256sum not found."""
        mock_which.side_effect = lambda x: {
            "dd": "/usr/bin/dd",
            "sha256sum": None,
        }.get(x)

        with pytest.raises(RuntimeError, match="dd or sha256sum not found"):
            verification.compute_partition_sha256("/dev/sda1")

    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_successful_partition_hash(self, mock_which, mock_popen):
        """Test successful partition hash computation."""
        mock_which.side_effect = lambda x: {
            "dd": "/usr/bin/dd",
            "sha256sum": "/usr/bin/sha256sum",
        }.get(x)

        dd_proc = Mock()
        dd_stdout = Mock()
        dd_proc.stdout = dd_stdout
        dd_proc.wait.return_value = 0
        dd_proc.returncode = 0

        sha_proc = Mock()
        sha_proc.communicate.return_value = ("partition_hash  -", "")
        sha_proc.returncode = 0

        mock_popen.side_effect = [dd_proc, sha_proc]

        result = verification.compute_partition_sha256("/dev/sda1")

        assert result == "partition_hash"
        # Verify dd was called with correct args
        assert mock_popen.call_args_list[0][0][0][0] == "/usr/bin/dd"
        assert "if=/dev/sda1" in mock_popen.call_args_list[0][0][0]

    @patch("rpi_usb_cloner.storage.clonezilla.verification.get_verify_hash_timeout")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_partition_hash_timeout(
        self, mock_which, mock_popen, mock_get_timeout
    ):
        """Test raises RuntimeError when partition hash times out."""
        mock_which.side_effect = lambda x: {
            "dd": "/usr/bin/dd",
            "sha256sum": "/usr/bin/sha256sum",
        }.get(x)
        mock_get_timeout.return_value = 60.0

        dd_proc = Mock()
        dd_stdout = Mock()
        dd_proc.stdout = dd_stdout
        dd_proc.returncode = 0

        sha_proc = Mock()
        from subprocess import TimeoutExpired
        sha_proc.communicate.side_effect = TimeoutExpired("sha256sum", 60.0)

        mock_popen.side_effect = [dd_proc, sha_proc]

        with pytest.raises(RuntimeError, match="timed out"):
            verification.compute_partition_sha256("/dev/sda1")

        sha_proc.kill.assert_called()
        dd_proc.kill.assert_called()

    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_raises_when_dd_fails(self, mock_which, mock_popen):
        """Test raises RuntimeError when dd process fails."""
        mock_which.side_effect = lambda x: {
            "dd": "/usr/bin/dd",
            "sha256sum": "/usr/bin/sha256sum",
        }.get(x)

        dd_proc = Mock()
        dd_stdout = Mock()
        dd_proc.stdout = dd_stdout
        dd_proc.wait.return_value = 0
        dd_proc.returncode = 1  # dd fails

        sha_proc = Mock()
        sha_proc.communicate.return_value = ("hash  -", "")
        sha_proc.returncode = 0

        mock_popen.side_effect = [dd_proc, sha_proc]

        with pytest.raises(RuntimeError, match="dd failed"):
            verification.compute_partition_sha256("/dev/sda1")

    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_raises_when_sha256sum_fails_for_partition(self, mock_which, mock_popen):
        """Test raises RuntimeError when sha256sum fails."""
        mock_which.side_effect = lambda x: {
            "dd": "/usr/bin/dd",
            "sha256sum": "/usr/bin/sha256sum",
        }.get(x)

        dd_proc = Mock()
        dd_stdout = Mock()
        dd_proc.stdout = dd_stdout
        dd_proc.wait.return_value = 0
        dd_proc.returncode = 0

        sha_proc = Mock()
        sha_proc.communicate.return_value = ("", "sha256 error")
        sha_proc.returncode = 1

        mock_popen.side_effect = [dd_proc, sha_proc]

        with pytest.raises(RuntimeError, match="sha256sum failed"):
            verification.compute_partition_sha256("/dev/sda1")

    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_raises_when_no_checksum_for_partition(self, mock_which, mock_popen):
        """Test raises RuntimeError when no checksum returned for partition."""
        mock_which.side_effect = lambda x: {
            "dd": "/usr/bin/dd",
            "sha256sum": "/usr/bin/sha256sum",
        }.get(x)

        dd_proc = Mock()
        dd_stdout = Mock()
        dd_proc.stdout = dd_stdout
        dd_proc.wait.return_value = 0
        dd_proc.returncode = 0

        sha_proc = Mock()
        sha_proc.communicate.return_value = ("", "")  # Empty output
        sha_proc.returncode = 0

        mock_popen.side_effect = [dd_proc, sha_proc]

        with pytest.raises(RuntimeError, match="No checksum returned"):
            verification.compute_partition_sha256("/dev/sda1")


class TestVerifyRestoredImageEdgeCases:
    """Tests for verify_restored_image() edge cases."""

    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_returns_false_when_sha256sum_not_found(self, mock_which):
        """Test returns False when sha256sum binary not found."""
        mock_which.return_value = None

        progress_updates = []

        def progress_callback(lines, ratio):
            progress_updates.append((lines, ratio))

        result = verification.verify_restored_image(
            Mock(), "sdb", progress_callback=progress_callback
        )

        assert result is False
        assert any("not found" in " ".join(lines) for lines, _ in progress_updates)

    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name")
    def test_returns_false_when_target_device_not_found(
        self, mock_get_device, mock_which
    ):
        """Test returns False when target device not found."""
        mock_which.return_value = "/usr/bin/sha256sum"
        mock_get_device.return_value = None

        progress_updates = []

        def progress_callback(lines, ratio):
            progress_updates.append((lines, ratio))

        result = verification.verify_restored_image(
            Mock(), "sdb", progress_callback=progress_callback
        )

        assert result is False
        assert any("Target device" in " ".join(lines) for lines, _ in progress_updates)

    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name")
    def test_returns_false_when_unmount_fails(
        self, mock_get_device, mock_unmount, mock_which
    ):
        """Test returns False when unmount fails."""
        mock_which.return_value = "/usr/bin/sha256sum"
        mock_get_device.return_value = {"name": "sdb"}
        mock_unmount.return_value = False

        progress_updates = []

        def progress_callback(lines, ratio):
            progress_updates.append((lines, ratio))

        result = verification.verify_restored_image(
            Mock(), "sdb", progress_callback=progress_callback
        )

        assert result is False
        assert any("Unmount failed" in " ".join(lines) for lines, _ in progress_updates)

    @patch("rpi_usb_cloner.storage.clonezilla.verification.compute_image_sha256")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_children")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_returns_false_when_partition_not_found(
        self, mock_which, mock_get_device, mock_unmount, mock_get_children, mock_image_hash
    ):
        """Test returns False when target partition not found."""
        mock_which.return_value = "/usr/bin/sha256sum"
        mock_get_device.return_value = {"name": "sdb"}
        mock_unmount.return_value = True
        # Return partitions that don't match the plan
        mock_get_children.return_value = [
            {"name": "sdb3", "type": "part"},  # Different partition number
        ]

        # Create a mock plan with partition_ops
        mock_plan = Mock()
        mock_op = Mock()
        mock_op.partition = "sda1"  # Looking for partition 1
        mock_op.image_files = [Mock()]
        mock_op.compressed = False
        mock_plan.partition_ops = [mock_op]

        progress_updates = []

        def progress_callback(lines, ratio):
            progress_updates.append((lines, ratio))

        result = verification.verify_restored_image(
            mock_plan, "sdb", progress_callback=progress_callback
        )

        assert result is False
        assert any("Partition missing" in " ".join(lines) for lines, _ in progress_updates)

    @patch("rpi_usb_cloner.storage.clonezilla.verification.compute_partition_sha256")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.compute_image_sha256")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_children")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_returns_false_when_target_hash_fails(
        self, mock_which, mock_get_device, mock_unmount, mock_get_children,
        mock_image_hash, mock_partition_hash
    ):
        """Test returns False when target partition hash computation fails."""
        mock_which.return_value = "/usr/bin/sha256sum"
        mock_get_device.return_value = {"name": "sdb"}
        mock_unmount.return_value = True
        mock_get_children.return_value = [
            {"name": "sdb1", "type": "part"},
        ]
        mock_image_hash.return_value = "abc123"
        mock_partition_hash.side_effect = RuntimeError("IO error")

        mock_plan = Mock()
        mock_op = Mock()
        mock_op.partition = "sda1"
        mock_op.image_files = [Mock()]
        mock_op.compressed = False
        mock_plan.partition_ops = [mock_op]

        progress_updates = []

        def progress_callback(lines, ratio):
            progress_updates.append((lines, ratio))

        result = verification.verify_restored_image(
            mock_plan, "sdb", progress_callback=progress_callback
        )

        assert result is False
        assert any("Target hash error" in " ".join(lines) for lines, _ in progress_updates)

    @patch("rpi_usb_cloner.storage.clonezilla.verification.compute_image_sha256")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_children")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_returns_false_when_invalid_partition_number(
        self, mock_which, mock_get_device, mock_unmount, mock_get_children, mock_image_hash
    ):
        """Test returns False when partition number cannot be determined."""
        mock_which.return_value = "/usr/bin/sha256sum"
        mock_get_device.return_value = {"name": "sdb"}
        mock_unmount.return_value = True
        mock_get_children.return_value = [
            {"name": "sdb1", "type": "part"},
        ]

        mock_plan = Mock()
        mock_op = Mock()
        mock_op.partition = "invalid"  # No valid partition number
        mock_op.image_files = [Mock()]
        mock_op.compressed = False
        mock_plan.partition_ops = [mock_op]

        progress_updates = []

        def progress_callback(lines, ratio):
            progress_updates.append((lines, ratio))

        result = verification.verify_restored_image(
            mock_plan, "sdb", progress_callback=progress_callback
        )

        assert result is False
        assert any("Invalid partition" in " ".join(lines) for lines, _ in progress_updates)

    def test_works_without_progress_callback(self):
        """Test verification works when progress_callback is None."""
        with patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which") as mock_which:
            mock_which.return_value = None  # sha256sum not found to trigger early return

            # Should not raise even without progress_callback
            result = verification.verify_restored_image(Mock(), "sdb", progress_callback=None)
            assert result is False
