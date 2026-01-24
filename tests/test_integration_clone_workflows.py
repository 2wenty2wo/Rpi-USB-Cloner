"""Integration tests for clone workflows."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from rpi_usb_cloner.storage.clone import clone_device
from rpi_usb_cloner.storage.clone.erase import erase_device


@pytest.mark.integration
class TestCloneWorkflow:
    """Integration tests for complete clone workflows."""

    @pytest.fixture
    def mock_devices(self):
        """Create mock source and target devices."""
        source = {
            "name": "sda",
            "size": 16000000000,
            "type": "disk",
        }
        target = {
            "name": "sdb",
            "size": 32000000000,
            "type": "disk",
        }
        return source, target

    @pytest.fixture
    def mock_partitions(self):
        """Create mock partitions for devices."""
        source_parts = [
            {
                "name": "sda1",
                "type": "part",
                "fstype": "vfat",
                "size": 500000000,
                "label": "BOOT",
            },
            {
                "name": "sda2",
                "type": "part",
                "fstype": "ext4",
                "size": 15000000000,
                "label": "rootfs",
            },
        ]
        target_parts = [
            {
                "name": "sdb1",
                "type": "part",
                "fstype": "",
                "size": 500000000,
            },
            {
                "name": "sdb2",
                "type": "part",
                "fstype": "",
                "size": 15000000000,
            },
        ]
        return source_parts, target_parts

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_partclone")
    @patch("rpi_usb_cloner.storage.clone.operations.copy_partition_table")
    def test_smart_clone_workflow(
        self,
        mock_copy_table,
        mock_clone_partclone,
        mock_unmount,
        mock_display,
        mock_devices,
    ):
        """Test complete smart clone workflow."""
        source, target = mock_devices

        result = clone_device(source, target, mode="smart")

        assert result is True
        # Verify workflow steps
        mock_unmount.assert_called_once_with(target)
        mock_copy_table.assert_called_once()
        mock_clone_partclone.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_dd")
    def test_exact_clone_workflow(
        self,
        mock_clone_dd,
        mock_unmount,
        mock_display,
        mock_devices,
    ):
        """Test complete exact/raw clone workflow."""
        source, target = mock_devices

        result = clone_device(source, target, mode="exact")

        assert result is True
        mock_unmount.assert_called_once_with(target)
        mock_clone_dd.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.verification.verify_clone")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_device_smart")
    def test_verify_clone_workflow(
        self,
        mock_smart,
        mock_verify,
        mock_devices,
    ):
        """Test complete clone with verification workflow."""
        source, target = mock_devices
        mock_smart.return_value = True
        mock_verify.return_value = True

        result = clone_device(source, target, mode="verify")

        assert result is True
        mock_smart.assert_called_once()
        mock_verify.assert_called_once_with(source, target)

    @patch("rpi_usb_cloner.storage.clone.verification.verify_clone")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_device_smart")
    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    def test_verify_clone_workflow_verification_fails(
        self,
        mock_display,
        mock_smart,
        mock_verify,
        mock_devices,
    ):
        """Test clone workflow when verification fails."""
        source, target = mock_devices
        mock_smart.return_value = True
        mock_verify.return_value = False

        result = clone_device(source, target, mode="verify")

        assert result is False
        # Clone should succeed but verification fails
        mock_smart.assert_called_once()
        mock_verify.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    @patch("rpi_usb_cloner.storage.clone.operations.copy_partition_table")
    def test_clone_workflow_partition_table_failure(
        self,
        mock_copy_table,
        mock_unmount,
        mock_display,
        mock_devices,
    ):
        """Test clone workflow fails when partition table copy fails."""
        source, target = mock_devices
        mock_copy_table.side_effect = RuntimeError("Partition table error")

        result = clone_device(source, target, mode="smart")

        assert result is False
        mock_unmount.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.get_children")
    @patch("rpi_usb_cloner.storage.clone.operations.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.operations.copy_partition_table")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    @patch("builtins.open", new_callable=MagicMock)
    @patch(
        "rpi_usb_cloner.storage.clone.operations.run_checked_with_streaming_progress"
    )
    def test_full_smart_clone_with_partitions(
        self,
        mock_run,
        mock_open,
        mock_which,
        mock_unmount,
        mock_copy_table,
        mock_get_device,
        mock_get_children,
        mock_display,
        mock_devices,
        mock_partitions,
    ):
        """Test complete smart clone with partition-by-partition copying."""
        source, target = mock_devices
        source_parts, target_parts = mock_partitions

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]
        mock_which.side_effect = lambda x: (
            f"/usr/bin/{x}" if x in ["partclone.fat", "partclone.ext4"] else None
        )
        mock_run.return_value = Mock()

        result = clone_device(source, target, mode="smart")

        assert result is True
        # Should have cloned both partitions
        assert mock_run.call_count == 2


@pytest.mark.integration
class TestEraseWorkflow:
    """Integration tests for erase workflows."""

    @pytest.fixture
    def mock_target(self):
        """Create mock target device."""
        return {
            "name": "sdb",
            "size": 16000000000,
        }

    @patch("rpi_usb_cloner.storage.clone.erase.validate_device_unmounted")
    @patch("rpi_usb_cloner.storage.clone.erase.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.erase.unmount_device")
    @patch("rpi_usb_cloner.storage.clone.erase.shutil.which")
    @patch("rpi_usb_cloner.storage.clone.erase.run_checked_with_streaming_progress")
    def test_secure_erase_workflow(
        self,
        mock_run,
        mock_which,
        mock_unmount,
        mock_get_device,
        mock_validate_unmounted,
        mock_target,
    ):
        """Test complete secure erase workflow."""
        mock_which.return_value = "/usr/bin/shred"
        mock_run.return_value = Mock()

        result = erase_device(mock_target, "secure")

        assert result is True
        mock_unmount.assert_called_once_with(mock_target)
        mock_run.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.erase.validate_device_unmounted")
    @patch("rpi_usb_cloner.storage.clone.erase.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.erase.unmount_device")
    @patch("rpi_usb_cloner.storage.clone.erase.shutil.which")
    @patch("rpi_usb_cloner.storage.clone.erase.run_checked_with_streaming_progress")
    @patch("rpi_usb_cloner.storage.clone.erase.app_state")
    def test_quick_erase_workflow(
        self,
        mock_state,
        mock_run,
        mock_which,
        mock_unmount,
        mock_get_device,
        mock_validate_unmounted,
        mock_target,
    ):
        """Test complete quick erase workflow."""
        mock_state.QUICK_WIPE_MIB = 100

        def which_side_effect(cmd):
            return f"/usr/bin/{cmd}"

        mock_which.side_effect = which_side_effect
        mock_run.return_value = Mock()

        result = erase_device(mock_target, "quick")

        assert result is True
        mock_unmount.assert_called_once()
        # Should call wipefs + dd start + dd end = 3 calls
        assert mock_run.call_count == 3


@pytest.mark.integration
class TestCloneAndVerifyWorkflow:
    """Integration tests for clone + verify workflows."""

    @patch("rpi_usb_cloner.storage.clone.verification.get_children")
    @patch("rpi_usb_cloner.storage.clone.verification.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.verification.compute_sha256")
    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_device_smart")
    def test_clone_and_verify_partitions_success(
        self,
        mock_smart,
        mock_display,
        mock_compute,
        mock_get_device,
        mock_get_children,
    ):
        """Test cloning and verifying partitions."""
        source = {"name": "sda", "size": 16000000000}
        target = {"name": "sdb", "size": 16000000000}
        source_parts = [
            {"name": "sda1", "type": "part", "size": 500000000},
            {"name": "sda2", "type": "part", "size": 15000000000},
        ]
        target_parts = [
            {"name": "sdb1", "type": "part", "size": 500000000},
            {"name": "sdb2", "type": "part", "size": 15000000000},
        ]

        mock_smart.return_value = True
        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]
        # Matching checksums for both partitions
        mock_compute.side_effect = ["hash1", "hash1", "hash2", "hash2"]

        result = clone_device(source, target, mode="verify")

        assert result is True
        # Should verify both partitions (2 source + 2 target = 4 calls)
        assert mock_compute.call_count == 4

    @patch("rpi_usb_cloner.storage.clone.verification.get_children")
    @patch("rpi_usb_cloner.storage.clone.verification.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.verification.compute_sha256")
    @patch("rpi_usb_cloner.storage.clone.verification.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_device_smart")
    def test_clone_and_verify_checksum_mismatch(
        self,
        mock_smart,
        mock_display,
        mock_compute,
        mock_get_device,
        mock_get_children,
    ):
        """Test clone succeeds but verification finds mismatch."""
        source = {"name": "sda", "size": 16000000000}
        target = {"name": "sdb", "size": 16000000000}
        source_parts = [
            {"name": "sda1", "type": "part", "size": 500000000},
        ]
        target_parts = [
            {"name": "sdb1", "type": "part", "size": 500000000},
        ]

        mock_smart.return_value = True
        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [source_parts, target_parts]
        # Mismatched checksums
        mock_compute.side_effect = ["hash1", "hash2"]

        result = clone_device(source, target, mode="verify")

        assert result is False
        # Clone succeeded but verification failed
        mock_smart.assert_called_once()


@pytest.mark.integration
class TestEndToEndCloneScenarios:
    """End-to-end integration tests for realistic clone scenarios."""

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    @patch("rpi_usb_cloner.storage.clone.operations.get_children")
    @patch("rpi_usb_cloner.storage.clone.operations.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clone.operations.shutil.which")
    @patch("rpi_usb_cloner.storage.clone.operations.run_checked_command")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_dd")
    def test_clone_unpartitioned_disk(
        self,
        mock_dd,
        mock_run_cmd,
        mock_which,
        mock_get_device,
        mock_get_children,
        mock_unmount,
        mock_display,
    ):
        """Test cloning disk without partitions (raw image)."""
        source = {"name": "sda", "size": 8000000000}
        target = {"name": "sdb", "size": 8000000000}

        mock_get_device.side_effect = [source, target]
        mock_get_children.side_effect = [[], []]  # No partitions
        mock_which.return_value = "/usr/bin/sfdisk"
        mock_run_cmd.return_value = "label: dos\n"

        result = clone_device(source, target, mode="smart")

        # Should fall back to dd for unpartitioned disk
        assert result is True
        mock_dd.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.operations.display_lines")
    @patch("rpi_usb_cloner.storage.clone.operations.unmount_device")
    @patch("rpi_usb_cloner.storage.clone.operations.clone_dd")
    def test_clone_with_exact_mode_bypasses_partition_detection(
        self,
        mock_dd,
        mock_unmount,
        mock_display,
    ):
        """Test exact mode bypasses partition detection and uses dd directly."""
        source = {"name": "sda", "size": 8000000000}
        target = {"name": "sdb", "size": 16000000000}

        result = clone_device(source, target, mode="exact")

        assert result is True
        mock_unmount.assert_called_once()
        mock_dd.assert_called_once()
        # Verify dd was called with correct devices
        call_args = mock_dd.call_args
        assert source in call_args[0]
        assert target in call_args[0]
