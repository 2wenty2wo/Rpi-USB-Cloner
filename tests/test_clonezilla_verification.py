"""Tests for Clonezilla image verification.

Tests cover:
- SHA256 hash computation for images
- SHA256 hash computation for partitions
- Image verification during restore
- Timeout handling
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess

import pytest

from rpi_usb_cloner.storage.clonezilla.verification import (
    compute_image_sha256,
    compute_partition_sha256,
    verify_restored_image,
    get_verify_hash_timeout,
)
from rpi_usb_cloner.storage.clonezilla.models import RestorePlan, PartitionRestoreOp


class TestGetVerifyHashTimeout:
    """Test timeout retrieval from settings."""

    def test_timeout_from_settings(self, mocker):
        """Test getting timeout from settings."""
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.settings.get_setting",
            return_value="300",
        )

        timeout = get_verify_hash_timeout("verify_image_hash_timeout_seconds")

        assert timeout == 300.0

    def test_timeout_none_setting(self, mocker):
        """Test None when setting is None."""
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.settings.get_setting",
            return_value=None,
        )

        timeout = get_verify_hash_timeout("verify_image_hash_timeout_seconds")

        assert timeout is None

    def test_timeout_invalid_value(self, mocker):
        """Test None for invalid setting value."""
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.settings.get_setting",
            return_value="invalid",
        )

        timeout = get_verify_hash_timeout("verify_image_hash_timeout_seconds")

        assert timeout is None

    def test_timeout_zero_or_negative(self, mocker):
        """Test None for zero or negative timeout."""
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.settings.get_setting",
            return_value="0",
        )

        timeout = get_verify_hash_timeout("verify_image_hash_seconds")

        assert timeout is None


class TestComputeImageSHA256:
    """Test computing SHA256 for image files."""

    def test_compute_uncompressed_image(self, mocker, tmp_path):
        """Test SHA256 for uncompressed image."""
        image_file = tmp_path / "sda1.img"
        image_file.write_bytes(b"image data")

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.sorted_clonezilla_volumes",
            return_value=[image_file],
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_cat = Mock()
        mock_cat.stdout = None
        mock_cat.wait.return_value = 0

        mock_sha = Mock()
        mock_sha.stdout = "abc123456789def  -"
        mock_sha.stderr = ""
        mock_sha.returncode = 0
        mock_sha.communicate.return_value = ("abc123456789def  -", "")

        mock_popen.side_effect = [mock_cat, mock_sha]

        result = compute_image_sha256([image_file], compressed=False)

        assert result == "abc123456789def"

    def test_compute_gzip_compressed_image(self, mocker, tmp_path):
        """Test SHA256 for gzip compressed image."""
        image_file = tmp_path / "sda1.img.gz"
        image_file.write_bytes(b"compressed data")

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            side_effect=["/usr/bin/pigz", "/usr/bin/sha256sum"],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.sorted_clonezilla_volumes",
            return_value=[image_file],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.get_compression_type",
            return_value="gzip",
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_cat = Mock()
        mock_cat.stdout = None
        mock_cat.wait.return_value = 0

        mock_gzip = Mock()
        mock_gzip.stdout = None
        mock_gzip.wait.return_value = 0

        mock_sha = Mock()
        mock_sha.communicate.return_value = ("def987654321abc  -", "")
        mock_sha.returncode = 0

        mock_popen.side_effect = [mock_cat, mock_gzip, mock_sha]

        result = compute_image_sha256([image_file], compressed=True)

        assert result == "def987654321abc"

    def test_compute_zstd_compressed_image(self, mocker, tmp_path):
        """Test SHA256 for zstd compressed image."""
        image_file = tmp_path / "sda1.img.zst"
        image_file.write_bytes(b"zstd compressed data")

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            side_effect=["/usr/bin/zstd", "/usr/bin/sha256sum"],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.sorted_clonezilla_volumes",
            return_value=[image_file],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.get_compression_type",
            return_value="zstd",
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_cat = Mock()
        mock_cat.stdout = None
        mock_cat.wait.return_value = 0

        mock_zstd = Mock()
        mock_zstd.stdout = None
        mock_zstd.wait.return_value = 0

        mock_sha = Mock()
        mock_sha.communicate.return_value = ("zstd123hash456  -", "")
        mock_sha.returncode = 0

        mock_popen.side_effect = [mock_cat, mock_zstd, mock_sha]

        result = compute_image_sha256([image_file], compressed=True)

        assert result == "zstd123hash456"

    def test_compute_no_image_files(self):
        """Test error when no image files."""
        with pytest.raises(RuntimeError, match="No image files"):
            compute_image_sha256([], compressed=False)

    def test_compute_sha256sum_not_found(self, mocker):
        """Test error when sha256sum not available."""
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value=None,
        )

        with pytest.raises(RuntimeError, match="sha256sum not found"):
            compute_image_sha256([Path("/tmp/test.img")], compressed=False)

    def test_compute_gzip_not_found(self, mocker):
        """Test error when gzip not available."""
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            side_effect=[None, "/usr/bin/sha256sum"],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.get_compression_type",
            return_value="gzip",
        )

        with pytest.raises(RuntimeError, match="gzip not found"):
            compute_image_sha256([Path("/tmp/test.img.gz")], compressed=True)

    def test_compute_sha_failure(self, mocker, tmp_path):
        """Test error when sha256sum fails."""
        image_file = tmp_path / "sda1.img"
        image_file.write_bytes(b"image data")

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.sorted_clonezilla_volumes",
            return_value=[image_file],
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_cat = Mock()
        mock_cat.stdout = None
        mock_cat.wait.return_value = 0

        mock_sha = Mock()
        mock_sha.communicate.return_value = ("", "sha256sum: error")
        mock_sha.returncode = 1

        mock_popen.side_effect = [mock_cat, mock_sha]

        with pytest.raises(RuntimeError, match="sha256sum failed"):
            compute_image_sha256([image_file], compressed=False)

    def test_compute_no_checksum_output(self, mocker, tmp_path):
        """Test error when no checksum in output."""
        image_file = tmp_path / "sda1.img"
        image_file.write_bytes(b"image data")

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.sorted_clonezilla_volumes",
            return_value=[image_file],
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_cat = Mock()
        mock_cat.stdout = None
        mock_cat.wait.return_value = 0

        mock_sha = Mock()
        mock_sha.communicate.return_value = ("", "")  # Empty output
        mock_sha.returncode = 0

        mock_popen.side_effect = [mock_cat, mock_sha]

        with pytest.raises(RuntimeError, match="No checksum returned"):
            compute_image_sha256([image_file], compressed=False)

    def test_compute_timeout(self, mocker, tmp_path):
        """Test timeout during hash computation."""
        image_file = tmp_path / "sda1.img"
        image_file.write_bytes(b"image data")

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.sorted_clonezilla_volumes",
            return_value=[image_file],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.get_verify_hash_timeout",
            return_value=1.0,
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_cat = Mock()
        mock_cat.stdout = None

        mock_sha = Mock()
        mock_sha.communicate.side_effect = subprocess.TimeoutExpired(
            "sha256sum", timeout=1.0
        )

        mock_popen.side_effect = [mock_cat, mock_sha]

        with pytest.raises(RuntimeError, match="timed out"):
            compute_image_sha256([image_file], compressed=False)


class TestComputePartitionSHA256:
    """Test computing SHA256 for partition."""

    def test_compute_partition_success(self, mocker):
        """Test successful partition hash computation."""
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            side_effect=["/bin/dd", "/usr/bin/sha256sum"],
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_dd = Mock()
        mock_dd.stdout = None
        mock_dd.wait.return_value = 0

        mock_sha = Mock()
        mock_sha.communicate.return_value = ("partition123hash  -", "")
        mock_sha.returncode = 0

        mock_popen.side_effect = [mock_dd, mock_sha]

        result = compute_partition_sha256("/dev/sda1")

        assert result == "partition123hash"

    def test_compute_partition_dd_not_found(self, mocker):
        """Test error when dd not found."""
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            side_effect=[None, "/usr/bin/sha256sum"],
        )

        with pytest.raises(RuntimeError, match="dd or sha256sum not found"):
            compute_partition_sha256("/dev/sda1")

    def test_compute_partition_sha256sum_not_found(self, mocker):
        """Test error when sha256sum not found."""
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            side_effect=["/bin/dd", None],
        )

        with pytest.raises(RuntimeError, match="dd or sha256sum not found"):
            compute_partition_sha256("/dev/sda1")

    def test_compute_partition_timeout(self, mocker):
        """Test timeout during partition hash."""
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            side_effect=["/bin/dd", "/usr/bin/sha256sum"],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.get_verify_hash_timeout",
            return_value=1.0,
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_dd = Mock()
        mock_dd.stdout = None

        mock_sha = Mock()
        mock_sha.communicate.side_effect = subprocess.TimeoutExpired(
            "sha256sum", timeout=1.0
        )

        mock_popen.side_effect = [mock_dd, mock_sha]

        with pytest.raises(RuntimeError, match="timed out"):
            compute_partition_sha256("/dev/sda1")

    def test_compute_partition_dd_failure(self, mocker):
        """Test error when dd fails."""
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            side_effect=["/bin/dd", "/usr/bin/sha256sum"],
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_dd = Mock()
        mock_dd.stdout = None
        mock_dd.wait.return_value = 1  # Failure

        mock_sha = Mock()
        mock_sha.communicate.return_value = ("", "")
        mock_sha.returncode = 0

        mock_popen.side_effect = [mock_dd, mock_sha]

        with pytest.raises(RuntimeError, match="dd failed"):
            compute_partition_sha256("/dev/sda1")


class TestVerifyRestoredImage:
    """Test full image verification after restore."""

    def test_verify_success(self, mocker):
        """Test successful verification."""
        # Create mock restore plan
        mock_op = Mock(spec=PartitionRestoreOp)
        mock_op.partition = "sda1"
        mock_op.image_files = [Path("/tmp/sda1.img")]
        mock_op.compressed = False

        mock_plan = Mock(spec=RestorePlan)
        mock_plan.partition_ops = [mock_op]

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )

        # Mock device operations
        mock_target_dev = Mock()
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name",
            return_value=mock_target_dev,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_children",
            return_value=[
                {"name": "sda1", "type": "part"},
            ],
        )

        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        # Mock hash computation - both return same hash
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.compute_image_sha256",
            return_value="matchinghash123",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.compute_partition_sha256",
            return_value="matchinghash123",
        )

        result = verify_restored_image(mock_plan, "sda", progress_callback=progress_cb)

        assert result is True

    def test_verify_sha256sum_not_found(self, mocker):
        """Test failure when sha256sum not available."""
        mock_plan = Mock(spec=RestorePlan)
        mock_plan.partition_ops = []

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value=None,
        )

        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        result = verify_restored_image(mock_plan, "sda", progress_callback=progress_cb)

        assert result is False
        assert any("sha256sum" in str(call[0]) for call in progress_calls)

    def test_verify_device_not_found(self, mocker):
        """Test failure when target device not found."""
        mock_plan = Mock(spec=RestorePlan)
        mock_plan.partition_ops = [Mock(spec=PartitionRestoreOp)]

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name",
            return_value=None,
        )

        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        result = verify_restored_image(mock_plan, "sda", progress_callback=progress_cb)

        assert result is False

    def test_verify_unmount_failure(self, mocker):
        """Test failure when unmount fails."""
        mock_plan = Mock(spec=RestorePlan)
        mock_plan.partition_ops = [Mock(spec=PartitionRestoreOp)]

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name",
            return_value=Mock(),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device",
            return_value=False,
        )

        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        result = verify_restored_image(mock_plan, "sda", progress_callback=progress_cb)

        assert result is False

    def test_verify_partition_not_found(self, mocker):
        """Test failure when partition missing."""
        mock_op = Mock(spec=PartitionRestoreOp)
        mock_op.partition = "sda1"
        mock_op.image_files = [Path("/tmp/sda1.img")]
        mock_op.compressed = False

        mock_plan = Mock(spec=RestorePlan)
        mock_plan.partition_ops = [mock_op]

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name",
            return_value=Mock(),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device",
            return_value=True,
        )
        # No matching partition in target
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_children",
            return_value=[
                {"name": "sda2", "type": "part"},  # Different partition
            ],
        )

        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        result = verify_restored_image(mock_plan, "sda", progress_callback=progress_cb)

        assert result is False

    def test_verify_hash_mismatch(self, mocker):
        """Test failure when hashes don't match."""
        mock_op = Mock(spec=PartitionRestoreOp)
        mock_op.partition = "sda1"
        mock_op.image_files = [Path("/tmp/sda1.img")]
        mock_op.compressed = False

        mock_plan = Mock(spec=RestorePlan)
        mock_plan.partition_ops = [mock_op]

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name",
            return_value=Mock(),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_children",
            return_value=[{"name": "sda1", "type": "part"}],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.get_partition_number",
            return_value=1,
        )

        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        # Different hashes
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.compute_image_sha256",
            return_value="imagehash123",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.compute_partition_sha256",
            return_value="partitionhash456",
        )

        result = verify_restored_image(mock_plan, "sda", progress_callback=progress_cb)

        assert result is False

    def test_verify_multiple_partitions(self, mocker):
        """Test verification of multiple partitions."""
        mock_op1 = Mock(spec=PartitionRestoreOp)
        mock_op1.partition = "sda1"
        mock_op1.image_files = [Path("/tmp/sda1.img")]
        mock_op1.compressed = False

        mock_op2 = Mock(spec=PartitionRestoreOp)
        mock_op2.partition = "sda2"
        mock_op2.image_files = [Path("/tmp/sda2.img")]
        mock_op2.compressed = False

        mock_plan = Mock(spec=RestorePlan)
        mock_plan.partition_ops = [mock_op1, mock_op2]

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name",
            return_value=Mock(),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_children",
            return_value=[
                {"name": "sda1", "type": "part"},
                {"name": "sda2", "type": "part"},
            ],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.get_partition_number",
            side_effect=[1, 2],
        )

        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.compute_image_sha256",
            side_effect=["hash1", "hash2"],
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.compute_partition_sha256",
            side_effect=["hash1", "hash2"],
        )

        result = verify_restored_image(mock_plan, "sda", progress_callback=progress_cb)

        assert result is True
        # Should have progress for both partitions
        assert len([c for c in progress_calls if "V 1/2" in str(c[0])]) > 0
        assert len([c for c in progress_calls if "V 2/2" in str(c[0])]) > 0

    def test_verify_image_hash_error(self, mocker):
        """Test handling image hash computation error."""
        mock_op = Mock(spec=PartitionRestoreOp)
        mock_op.partition = "sda1"
        mock_op.image_files = [Path("/tmp/sda1.img")]
        mock_op.compressed = False

        mock_plan = Mock(spec=RestorePlan)
        mock_plan.partition_ops = [mock_op]

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name",
            return_value=Mock(),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_children",
            return_value=[{"name": "sda1", "type": "part"}],
        )

        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.compute_image_sha256",
            side_effect=RuntimeError("Hash computation failed"),
        )

        result = verify_restored_image(mock_plan, "sda", progress_callback=progress_cb)

        assert result is False

    def test_verify_partition_hash_error(self, mocker):
        """Test handling partition hash computation error."""
        mock_op = Mock(spec=PartitionRestoreOp)
        mock_op.partition = "sda1"
        mock_op.image_files = [Path("/tmp/sda1.img")]
        mock_op.compressed = False

        mock_plan = Mock(spec=RestorePlan)
        mock_plan.partition_ops = [mock_op]

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.shutil.which",
            return_value="/usr/bin/sha256sum",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name",
            return_value=Mock(),
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.devices.get_children",
            return_value=[{"name": "sda1", "type": "part"}],
        )

        progress_calls = []

        def progress_cb(lines, progress):
            progress_calls.append((lines, progress))

        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.compute_image_sha256",
            return_value="somehash",
        )
        mocker.patch(
            "rpi_usb_cloner.storage.clonezilla.verification.compute_partition_sha256",
            side_effect=RuntimeError("Partition read failed"),
        )

        result = verify_restored_image(mock_plan, "sda", progress_callback=progress_cb)

        assert result is False
