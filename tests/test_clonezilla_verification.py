"""Tests for Clonezilla verification utilities."""

from unittest.mock import Mock, patch

import pytest

from rpi_usb_cloner.storage.clonezilla import verification
from tests import test_clonezilla_restore


@pytest.fixture
def mock_clonezilla_image(tmp_path):
    """Reuse the restore test fixture for Clonezilla images."""
    return test_clonezilla_restore.mock_clonezilla_image.__wrapped__(tmp_path)


@pytest.fixture
def mock_restore_plan(mock_clonezilla_image, tmp_path):
    """Reuse the restore plan fixture for verification tests."""
    return test_clonezilla_restore.mock_restore_plan.__wrapped__(
        mock_clonezilla_image, tmp_path
    )


class TestVerifyRestoredImage:
    """Tests for verify_restored_image() behavior."""

    @patch("rpi_usb_cloner.storage.clonezilla.verification.compute_image_sha256")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.compute_partition_sha256")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_children")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_verify_restored_image_valid_checksum_flow(
        self,
        mock_which,
        mock_get_device,
        mock_unmount,
        mock_get_children,
        mock_partition_hash,
        mock_image_hash,
        mock_restore_plan,
    ):
        """Test verification succeeds when image and target checksums match."""
        mock_which.return_value = "/usr/bin/sha256sum"
        mock_get_device.return_value = {"name": "sdb"}
        mock_unmount.return_value = True
        mock_get_children.return_value = [
            {"name": "sdb1", "type": "part"},
            {"name": "sdb2", "type": "part"},
        ]
        mock_image_hash.return_value = "abc123"
        mock_partition_hash.return_value = "abc123"

        progress_updates = []

        def progress_callback(lines, ratio):
            progress_updates.append((lines, ratio))

        result = verification.verify_restored_image(
            mock_restore_plan, "sdb", progress_callback=progress_callback
        )

        assert result is True
        assert mock_image_hash.call_count == len(mock_restore_plan.partition_ops)
        assert mock_partition_hash.call_count == len(mock_restore_plan.partition_ops)
        assert ("VERIFY", "Complete") in [tuple(lines) for lines, _ in progress_updates]

    @patch("rpi_usb_cloner.storage.clonezilla.verification.compute_image_sha256")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.compute_partition_sha256")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_children")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_verify_restored_image_detects_corrupt_image(
        self,
        mock_which,
        mock_get_device,
        mock_unmount,
        mock_get_children,
        mock_partition_hash,
        mock_image_hash,
        mock_restore_plan,
    ):
        """Test verification fails when image hash computation errors."""
        mock_which.return_value = "/usr/bin/sha256sum"
        mock_get_device.return_value = {"name": "sdb"}
        mock_unmount.return_value = True
        mock_get_children.return_value = [
            {"name": "sdb1", "type": "part"},
            {"name": "sdb2", "type": "part"},
        ]
        mock_image_hash.side_effect = RuntimeError("corrupt image")
        mock_partition_hash.return_value = "deadbeef"

        progress_updates = []

        def progress_callback(lines, ratio):
            progress_updates.append((lines, ratio))

        result = verification.verify_restored_image(
            mock_restore_plan, "sdb", progress_callback=progress_callback
        )

        assert result is False
        assert mock_image_hash.called
        assert not mock_partition_hash.called
        assert any(
            "Image hash error" in " ".join(lines) for lines, _ in progress_updates
        )

    @patch("rpi_usb_cloner.storage.clonezilla.verification.compute_image_sha256")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.compute_partition_sha256")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_children")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_verify_restored_image_reports_checksum_mismatch(
        self,
        mock_which,
        mock_get_device,
        mock_unmount,
        mock_get_children,
        mock_partition_hash,
        mock_image_hash,
        mock_restore_plan,
    ):
        """Test verification reports a mismatch when hashes differ."""
        mock_which.return_value = "/usr/bin/sha256sum"
        mock_get_device.return_value = {"name": "sdb"}
        mock_unmount.return_value = True
        mock_get_children.return_value = [{"name": "sdb1", "type": "part"}]
        mock_image_hash.return_value = "abc123"
        mock_partition_hash.return_value = "deadbeef"

        progress_updates = []

        def progress_callback(lines, ratio):
            progress_updates.append((lines, ratio))

        result = verification.verify_restored_image(
            mock_restore_plan, "sdb", progress_callback=progress_callback
        )

        assert result is False
        assert any("Mismatch" in " ".join(lines) for lines, _ in progress_updates)


class TestComputeImageSha256:
    """Tests for compute_image_sha256() error handling."""

    @patch("rpi_usb_cloner.storage.clonezilla.verification.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clonezilla.verification.shutil.which")
    def test_compute_image_sha256_missing_checksum_output(
        self, mock_which, mock_popen, tmp_path
    ):
        """Test missing checksum output raises an error."""
        image_file = tmp_path / "sda1.img"
        image_file.write_bytes(b"fake image")

        mock_which.return_value = "/usr/bin/sha256sum"

        cat_proc = Mock()
        cat_stdout = Mock()
        cat_proc.stdout = cat_stdout
        cat_proc.wait.return_value = 0
        cat_proc.returncode = 0

        sha_proc = Mock()
        sha_proc.communicate.return_value = ("", "")
        sha_proc.returncode = 0

        mock_popen.side_effect = [cat_proc, sha_proc]

        with pytest.raises(RuntimeError, match="No checksum returned"):
            verification.compute_image_sha256([image_file], compressed=False)
