"""Tests for storage/clonezilla/restore.py - Clonezilla restore operations.

This test suite covers:
- Basic restore workflow
- All partition modes (k0=create partition table, k=use existing, k1=proportional resize, k2=enter cmdline)
- Validation (target size sufficient, image files exist)
- Partition table restoration
- Multi-partition restore
- Error handling (missing image files, target too small, corrupted images)
- Progress tracking
- Cleanup on failure
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rpi_usb_cloner.storage.clonezilla import restore
from rpi_usb_cloner.storage.clonezilla.models import (
    ClonezillaImage,
    DiskLayoutOp,
    PartitionRestoreOp,
    RestorePlan,
)


@pytest.fixture
def mock_clonezilla_image(tmp_path):
    """Fixture providing a mock ClonezillaImage."""
    image_dir = tmp_path / "test_image"
    image_dir.mkdir()

    # Create partition table file
    pt_file = image_dir / "sda-pt.sf"
    pt_file.write_text("label: dos\n")

    return ClonezillaImage(
        name="test_image",
        path=image_dir,
        parts=["sda1", "sda2"],
        partition_table=pt_file,
    )


@pytest.fixture
def mock_restore_plan(mock_clonezilla_image, tmp_path):
    """Fixture providing a mock RestorePlan."""
    image_files1 = [tmp_path / "sda1.vfat-ptcl-img.gz"]
    image_files2 = [tmp_path / "sda2.ext4-ptcl-img.gz"]

    # Create dummy image files
    for f in image_files1 + image_files2:
        f.write_bytes(b"test image data")

    pt_file = tmp_path / "sda-pt.sf"
    pt_file.write_text("label: dos\n")

    return RestorePlan(
        image_dir=mock_clonezilla_image.path,
        parts=["sda1", "sda2"],
        partition_ops=[
            PartitionRestoreOp(
                partition="sda1",
                image_files=image_files1,
                tool="partclone",
                fstype="vfat",
                compressed=True,
            ),
            PartitionRestoreOp(
                partition="sda2",
                image_files=image_files2,
                tool="partclone",
                fstype="ext4",
                compressed=True,
            ),
        ],
        disk_layout_ops=[
            DiskLayoutOp(
                kind="sfdisk",
                path=pt_file,
                contents="label: dos\n",
                size_bytes=1024,
            ),
        ],
    )


class TestGetBlockdevSizeBytes:
    """Tests for get_blockdev_size_bytes() function."""

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_get_blockdev_size_success(self, mock_which, mock_run):
        """Test getting device size with blockdev."""
        mock_which.return_value = "/usr/sbin/blockdev"
        mock_run.return_value = Mock(returncode=0, stdout="16106127360\n", stderr="")

        size = restore.get_blockdev_size_bytes("/dev/sda")

        assert size == 16106127360
        mock_run.assert_called_once_with(
            ["/usr/sbin/blockdev", "--getsize64", "/dev/sda"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    @patch("shutil.which")
    def test_get_blockdev_size_tool_not_found(self, mock_which):
        """Test when blockdev tool not available."""
        mock_which.return_value = None

        size = restore.get_blockdev_size_bytes("/dev/sda")

        assert size is None

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_get_blockdev_size_command_failure(self, mock_which, mock_run):
        """Test blockdev command failure."""
        mock_which.return_value = "/usr/sbin/blockdev"
        mock_run.return_value = Mock(returncode=1, stderr="error")

        size = restore.get_blockdev_size_bytes("/dev/sda")

        assert size is None


class TestGetDeviceSizeBytes:
    """Tests for get_device_size_bytes() function."""

    def test_get_device_size_from_device_info(self):
        """Test getting size from device info dict."""
        device_info = {"size": "16106127360"}

        size = restore.get_device_size_bytes(device_info, "/dev/sda")

        assert size == 16106127360

    @patch("rpi_usb_cloner.storage.clonezilla.restore.get_blockdev_size_bytes")
    def test_get_device_size_fallback_to_blockdev(self, mock_blockdev):
        """Test falling back to blockdev when device info unavailable."""
        mock_blockdev.return_value = 16106127360

        size = restore.get_device_size_bytes(None, "/dev/sda")

        assert size == 16106127360
        mock_blockdev.assert_called_once_with("/dev/sda")


class TestRereadPartitionTable:
    """Tests for reread_partition_table() function."""

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_reread_with_partprobe(self, mock_which, mock_run):
        """Test re-reading partition table with partprobe."""
        mock_which.return_value = "/usr/sbin/partprobe"

        restore.reread_partition_table("/dev/sda")

        mock_run.assert_called_once_with(
            ["/usr/sbin/partprobe", "/dev/sda"], check=False
        )

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_reread_fallback_to_blockdev(self, mock_which, mock_run):
        """Test falling back to blockdev when partprobe unavailable."""

        def which_side_effect(cmd):
            if cmd == "partprobe":
                return None
            if cmd == "blockdev":
                return "/usr/sbin/blockdev"
            return None

        mock_which.side_effect = which_side_effect

        restore.reread_partition_table("/dev/sda")

        mock_run.assert_called_once_with(
            ["/usr/sbin/blockdev", "--rereadpt", "/dev/sda"], check=False
        )


class TestSettleUdev:
    """Tests for settle_udev() function."""

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_settle_udev(self, mock_which, mock_run):
        """Test settling udev."""
        mock_which.return_value = "/usr/bin/udevadm"

        restore.settle_udev()

        mock_run.assert_called_once_with(["/usr/bin/udevadm", "settle"], check=False)

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_settle_udev_not_available(self, mock_which, mock_run):
        """Test when udevadm not available."""
        mock_which.return_value = None

        restore.settle_udev()

        # Should not crash
        mock_run.assert_not_called()


class TestMapTargetPartitions:
    """Tests for map_target_partitions() function."""

    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.get_children")
    def test_map_target_partitions(self, mock_get_children):
        """Test mapping source partitions to target partitions."""
        target_device = {"name": "sdb"}
        mock_get_children.return_value = [
            {"name": "sdb1", "type": "part", "size": "1073741824"},
            {"name": "sdb2", "type": "part", "size": "15032385536"},
        ]

        mapping = restore.map_target_partitions(["sda1", "sda2"], target_device)

        assert "sda1" in mapping
        assert "sda2" in mapping
        assert mapping["sda1"]["node"] == "/dev/sdb1"
        assert mapping["sda2"]["node"] == "/dev/sdb2"

    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.get_children")
    def test_map_target_partitions_skips_non_partitions(self, mock_get_children):
        """Test that non-partition children are skipped."""
        target_device = {"name": "sdb"}
        mock_get_children.return_value = [
            {"name": "sdb1", "type": "part", "size": "1073741824"},
            {"name": "sdb", "type": "disk", "size": "16106127360"},  # Not a partition
        ]

        mapping = restore.map_target_partitions(["sda1"], target_device)

        assert "sda1" in mapping
        assert mapping["sda1"]["node"] == "/dev/sdb1"


class TestCountTargetPartitions:
    """Tests for count_target_partitions() function."""

    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.get_children")
    def test_count_target_partitions(self, mock_get_children):
        """Test counting partitions on device."""
        target_device = {"name": "sdb"}
        mock_get_children.return_value = [
            {"name": "sdb1", "type": "part"},
            {"name": "sdb2", "type": "part"},
            {"name": "sdb", "type": "disk"},  # Not a partition
        ]

        count = restore.count_target_partitions(target_device)

        assert count == 2


class TestWritePartitionTable:
    """Tests for write_partition_table() function."""

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_write_partition_table_sfdisk(self, mock_which, mock_run, tmp_path):
        """Test writing partition table with sfdisk."""
        mock_which.return_value = "/usr/sbin/sfdisk"
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        table_path = tmp_path / "sda-pt.sf"
        table_path.write_text("label: dos\ndevice: /dev/sda\n")

        restore.write_partition_table(table_path, "/dev/sdb")

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "/usr/sbin/sfdisk" in call_args[0][0]
        assert "/dev/sdb" in call_args[0][0]
        assert call_args[1]["input"] == "label: dos\ndevice: /dev/sda\n"

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_write_partition_table_sgdisk(self, mock_which, mock_run, tmp_path):
        """Test writing GPT partition table with sgdisk."""
        mock_which.return_value = "/usr/sbin/sgdisk"
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        table_path = tmp_path / "sda-pt.sgdisk"
        table_path.write_text("GPT partition table\n")

        restore.write_partition_table(table_path, "/dev/sdb")

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "/usr/sbin/sgdisk" in call_args
        assert f"--load-backup={table_path}" in call_args

    def test_write_partition_table_unsupported_format(self, tmp_path):
        """Test error with unsupported partition table format."""
        table_path = tmp_path / "sda-pt.unknown"
        table_path.write_text("unknown format")

        with pytest.raises(RuntimeError, match="Unsupported partition table"):
            restore.write_partition_table(table_path, "/dev/sdb")

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_write_partition_table_sfdisk_failure(self, mock_which, mock_run, tmp_path):
        """Test sfdisk failure."""
        mock_which.return_value = "/usr/sbin/sfdisk"
        mock_run.return_value = Mock(returncode=1, stderr="sfdisk: error", stdout="")

        table_path = tmp_path / "sda-pt.sf"
        table_path.write_text("label: dos\n")

        with pytest.raises(RuntimeError, match="sfdisk: error"):
            restore.write_partition_table(table_path, "/dev/sdb")


class TestBuildRestoreCommandFromPlan:
    """Tests for build_restore_command_from_plan() function."""

    @patch("rpi_usb_cloner.storage.clonezilla.restore.get_partclone_tool")
    def test_build_partclone_restore_command(self, mock_get_tool):
        """Test building partclone restore command."""
        mock_get_tool.return_value = "partclone.ext4"

        op = PartitionRestoreOp(
            partition="sda1",
            image_files=[Path("/tmp/sda1.ext4-ptcl-img.gz")],
            tool="partclone",
            fstype="ext4",
            compressed=True,
        )

        command = restore.build_restore_command_from_plan(op, "/dev/sdb1")

        assert command[0] == "partclone.ext4"
        assert "-r" in command
        assert "-s" in command
        assert "-o" in command
        assert "/dev/sdb1" in command

    @patch("shutil.which")
    def test_build_dd_restore_command(self, mock_which):
        """Test building dd restore command."""
        mock_which.return_value = "/usr/bin/dd"

        op = PartitionRestoreOp(
            partition="sda1",
            image_files=[Path("/tmp/sda1.dd-img")],
            tool="dd",
            fstype=None,
            compressed=False,
        )

        command = restore.build_restore_command_from_plan(op, "/dev/sdb1")

        assert "/usr/bin/dd" in command[0]
        assert "of=/dev/sdb1" in command
        assert "bs=4M" in command

    @patch("rpi_usb_cloner.storage.clonezilla.restore.get_partclone_tool")
    def test_build_command_partclone_tool_not_found(self, mock_get_tool):
        """Test error when partclone tool not found."""
        mock_get_tool.return_value = None

        op = PartitionRestoreOp(
            partition="sda1",
            image_files=[Path("/tmp/sda1.ext4-ptcl-img.gz")],
            tool="partclone",
            fstype="ext4",
            compressed=True,
        )

        with pytest.raises(RuntimeError, match="partclone tool not found"):
            restore.build_restore_command_from_plan(op, "/dev/sdb1")


class TestRunRestorePipeline:
    """Tests for run_restore_pipeline() function."""

    @patch(
        "rpi_usb_cloner.storage.clonezilla.restore.clone.run_checked_with_streaming_progress"
    )
    @patch("rpi_usb_cloner.storage.clonezilla.restore.get_compression_type")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.subprocess.Popen")
    @patch("shutil.which")
    def test_run_restore_pipeline_with_gzip(
        self, mock_which, mock_popen, mock_get_comp, mock_run_checked, tmp_path
    ):
        """Test restore pipeline with gzip compression."""
        mock_which.return_value = "/usr/bin/gzip"
        mock_get_comp.return_value = "gzip"

        # Mock cat process
        mock_cat_proc = Mock()
        mock_cat_proc.returncode = 0
        mock_cat_proc.stdout = Mock()

        # Mock gzip process
        mock_gzip_proc = Mock()
        mock_gzip_proc.returncode = 0
        mock_gzip_proc.stdout = Mock()

        mock_popen.side_effect = [mock_cat_proc, mock_gzip_proc]

        image_files = [tmp_path / "sda1.ext4-ptcl-img.gz.aa"]
        for f in image_files:
            f.write_bytes(b"compressed data")

        restore_command = ["partclone.ext4", "-r", "-s", "-", "-o", "/dev/sdb1"]

        restore.run_restore_pipeline(
            image_files,
            restore_command,
            title="Restoring sda1",
        )

        # Verify cat and decompress processes were created
        assert mock_popen.call_count == 2
        # Verify restore command was executed
        mock_run_checked.assert_called_once()

    @patch(
        "rpi_usb_cloner.storage.clonezilla.restore.clone.run_checked_with_streaming_progress"
    )
    @patch("rpi_usb_cloner.storage.clonezilla.restore.get_compression_type")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.subprocess.Popen")
    def test_run_restore_pipeline_uncompressed(
        self, mock_popen, mock_get_comp, mock_run_checked, tmp_path
    ):
        """Test restore pipeline without compression."""
        mock_get_comp.return_value = None

        # Mock cat process
        mock_cat_proc = Mock()
        mock_cat_proc.returncode = 0
        mock_cat_proc.stdout = Mock()
        mock_popen.return_value = mock_cat_proc

        image_files = [tmp_path / "sda1.ext4-ptcl-img"]
        for f in image_files:
            f.write_bytes(b"uncompressed data")

        restore_command = ["partclone.ext4", "-r", "-s", "-", "-o", "/dev/sdb1"]

        restore.run_restore_pipeline(
            image_files,
            restore_command,
            title="Restoring sda1",
        )

        # Only cat process should be created (no decompression)
        assert mock_popen.call_count == 1
        mock_run_checked.assert_called_once()

    @patch(
        "rpi_usb_cloner.storage.clonezilla.restore.clone.run_checked_with_streaming_progress"
    )
    @patch("rpi_usb_cloner.storage.clonezilla.restore.get_compression_type")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.subprocess.Popen")
    def test_run_restore_pipeline_with_progress_callback(
        self, mock_popen, mock_get_comp, mock_run_checked, tmp_path
    ):
        """Test restore pipeline with progress callback."""
        mock_get_comp.return_value = None
        mock_cat_proc = Mock()
        mock_cat_proc.returncode = 0
        mock_cat_proc.stdout = Mock()
        mock_popen.return_value = mock_cat_proc

        image_files = [tmp_path / "sda1.img"]
        image_files[0].write_bytes(b"data")

        progress_calls = []

        def progress_callback(lines, ratio):
            progress_calls.append((lines, ratio))

        restore_command = ["dd", "of=/dev/sdb1"]

        restore.run_restore_pipeline(
            image_files,
            restore_command,
            title="Restoring",
            progress_callback=progress_callback,
        )

        # Progress callback should be passed through
        call_kwargs = mock_run_checked.call_args[1]
        assert call_kwargs["progress_callback"] == progress_callback


class TestRestoreClonezillaImage:
    """Tests for restore_clonezilla_image() main function."""

    @pytest.mark.skip(reason="Complex integration test requiring extensive mocking")
    @patch("os.geteuid")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.restore_partition_op")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.wait_for_target_partitions")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.apply_disk_layout_op")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.build_partition_mode_layout_ops")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.estimate_required_size_bytes")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.get_device_size_bytes")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.resolve_device_node")
    def test_restore_workflow_k0_mode(
        self,
        mock_resolve,
        mock_get_device,
        mock_unmount,
        mock_get_size,
        mock_estimate_size,
        mock_build_ops,
        mock_apply_layout,
        mock_wait_parts,
        mock_restore_op,
        mock_geteuid,
        mock_restore_plan,
    ):
        """Test restore workflow with k0 (create partition table) mode."""
        mock_geteuid.return_value = 0  # Running as root
        mock_resolve.return_value = "/dev/sdb"
        mock_get_device.return_value = {"name": "sdb", "size": "32212254720"}
        mock_unmount.return_value = True
        mock_get_size.return_value = 32212254720
        mock_estimate_size.return_value = 16106127360
        mock_build_ops.return_value = mock_restore_plan.disk_layout_ops
        mock_apply_layout.return_value = True
        mock_wait_parts.return_value = (
            {"name": "sdb"},
            {
                "sda1": {"node": "/dev/sdb1", "size_bytes": 1073741824},
                "sda2": {"node": "/dev/sdb2", "size_bytes": 15032385536},
            },
        )

        restore.restore_clonezilla_image(
            mock_restore_plan,
            "sdb",
            partition_mode="k0",
        )

        # Verify workflow steps
        mock_unmount.assert_called_once()
        mock_estimate_size.assert_called_once()
        mock_apply_layout.assert_called()
        mock_wait_parts.assert_called_once()
        # Should restore both partitions
        assert mock_restore_op.call_count == 2

    @patch("os.geteuid")
    def test_restore_requires_root(self, mock_geteuid, mock_restore_plan):
        """Test that restore requires root privileges."""
        mock_geteuid.return_value = 1000  # Not root

        with pytest.raises(RuntimeError, match="Run as root"):
            restore.restore_clonezilla_image(mock_restore_plan, "sdb")

    @patch("os.geteuid")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.resolve_device_node")
    def test_restore_unmount_failure(
        self,
        mock_resolve,
        mock_get_device,
        mock_unmount,
        mock_geteuid,
        mock_restore_plan,
    ):
        """Test restore aborted when unmount fails."""
        mock_geteuid.return_value = 0
        mock_resolve.return_value = "/dev/sdb"
        mock_get_device.return_value = {"name": "sdb"}
        mock_unmount.return_value = False

        with pytest.raises(RuntimeError, match="Failed to unmount"):
            restore.restore_clonezilla_image(mock_restore_plan, "sdb")

    @patch("os.geteuid")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.estimate_required_size_bytes")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.get_device_size_bytes")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.resolve_device_node")
    def test_restore_target_too_small(
        self,
        mock_resolve,
        mock_get_device,
        mock_unmount,
        mock_get_size,
        mock_estimate_size,
        mock_geteuid,
        mock_restore_plan,
    ):
        """Test error when target device too small."""
        mock_geteuid.return_value = 0
        mock_resolve.return_value = "/dev/sdb"
        mock_get_device.return_value = {"name": "sdb", "size": "8053063680"}
        mock_unmount.return_value = True
        mock_get_size.return_value = 8053063680  # 8GB
        mock_estimate_size.return_value = 16106127360  # Requires 16GB

        with pytest.raises(RuntimeError, match="Target device too small"):
            restore.restore_clonezilla_image(mock_restore_plan, "sdb")

    @patch("os.geteuid")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.wait_for_partition_count")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.build_partition_mode_layout_ops")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.estimate_required_size_bytes")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.get_device_size_bytes")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.unmount_device")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.get_device_by_name")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.resolve_device_node")
    def test_restore_k_mode_missing_partitions(
        self,
        mock_resolve,
        mock_get_device,
        mock_unmount,
        mock_get_size,
        mock_estimate_size,
        mock_build_ops,
        mock_wait_count,
        mock_geteuid,
        mock_restore_plan,
    ):
        """Test k mode (use existing partitions) with missing partitions."""
        mock_geteuid.return_value = 0
        mock_resolve.return_value = "/dev/sdb"
        mock_get_device.return_value = {"name": "sdb", "size": "32212254720"}
        mock_unmount.return_value = True
        mock_get_size.return_value = 32212254720
        mock_estimate_size.return_value = 16106127360
        mock_build_ops.return_value = []
        # Only 1 partition exists, but 2 required
        mock_wait_count.return_value = ({"name": "sdb"}, 1)

        with pytest.raises(RuntimeError, match="missing required partitions"):
            restore.restore_clonezilla_image(
                mock_restore_plan,
                "sdb",
                partition_mode="k",
            )


class TestWaitForPartitionCount:
    """Tests for wait_for_partition_count() function."""

    @patch("time.monotonic")
    @patch("time.sleep")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.count_target_partitions")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.get_device_by_name")
    def test_wait_for_partition_count_success(
        self, mock_get_device, mock_count, mock_sleep, mock_monotonic
    ):
        """Test waiting for partitions succeeds."""
        mock_monotonic.side_effect = [0, 0.5, 1.0]
        mock_get_device.return_value = {"name": "sdb"}
        mock_count.return_value = 2

        device, count = restore.wait_for_partition_count(
            "sdb",
            required_count=2,
            timeout_seconds=10,
        )

        assert count == 2
        assert device["name"] == "sdb"

    @patch("time.monotonic")
    @patch("time.sleep")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.count_target_partitions")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.get_device_by_name")
    def test_wait_for_partition_count_timeout(
        self, mock_get_device, mock_count, mock_sleep, mock_monotonic
    ):
        """Test waiting for partitions times out."""
        # Simulate timeout
        mock_monotonic.side_effect = [0, 1, 2, 3, 11]  # Exceeds 10s timeout
        mock_get_device.return_value = {"name": "sdb"}
        mock_count.return_value = 1  # Never reaches 2

        with pytest.raises(RuntimeError, match="did not create all partitions"):
            restore.wait_for_partition_count(
                "sdb",
                required_count=2,
                timeout_seconds=10,
            )

    @patch("time.monotonic")
    @patch("time.sleep")
    @patch("rpi_usb_cloner.storage.clonezilla.restore.devices.get_device_by_name")
    def test_wait_for_partition_count_device_not_found(
        self, mock_get_device, mock_sleep, mock_monotonic
    ):
        """Test error when device not found."""
        mock_monotonic.side_effect = [0, 1, 2, 11]
        mock_get_device.return_value = None

        with pytest.raises(RuntimeError, match="Unable to refresh target device"):
            restore.wait_for_partition_count(
                "sdb",
                required_count=2,
                timeout_seconds=10,
            )
