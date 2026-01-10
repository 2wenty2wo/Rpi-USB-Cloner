"""Tests for Clonezilla data models."""
from pathlib import Path

import pytest

from rpi_usb_cloner.storage.clonezilla.models import (
    ClonezillaImage,
    DiskLayoutOp,
    PartitionRestoreOp,
    RestorePlan,
)


class TestClonezillaImage:
    def test_create_image_with_all_fields(self):
        """Test creating a ClonezillaImage with all fields populated."""
        parts = ["sda1", "sda2", "sda3"]
        pt_path = Path("/images/test/sda-pt.parted")

        image = ClonezillaImage(
            name="test-image",
            path=Path("/images/test"),
            parts=parts,
            partition_table=pt_path
        )

        assert image.name == "test-image"
        assert image.path == Path("/images/test")
        assert image.parts == parts
        assert image.partition_table == pt_path

    def test_create_image_without_partition_table(self):
        """Test creating a ClonezillaImage without partition table."""
        parts = ["sda1"]

        image = ClonezillaImage(
            name="simple-image",
            path=Path("/images/simple"),
            parts=parts,
            partition_table=None
        )

        assert image.name == "simple-image"
        assert image.path == Path("/images/simple")
        assert image.parts == parts
        assert image.partition_table is None

    def test_create_image_with_empty_parts(self):
        """Test creating a ClonezillaImage with empty parts list."""
        image = ClonezillaImage(
            name="empty",
            path=Path("/images/empty"),
            parts=[],
            partition_table=None
        )

        assert image.parts == []

    def test_image_is_frozen(self):
        """Test that ClonezillaImage instances are immutable."""
        image = ClonezillaImage(
            name="test",
            path=Path("/test"),
            parts=["sda1"],
            partition_table=None
        )

        with pytest.raises(AttributeError):
            image.name = "modified"

        with pytest.raises(AttributeError):
            image.parts = ["sda2"]

    def test_image_equality(self):
        """Test equality comparison between ClonezillaImage instances."""
        image1 = ClonezillaImage(
            name="test",
            path=Path("/test"),
            parts=["sda1"],
            partition_table=Path("/test/pt")
        )

        image2 = ClonezillaImage(
            name="test",
            path=Path("/test"),
            parts=["sda1"],
            partition_table=Path("/test/pt")
        )

        assert image1 == image2

    def test_image_inequality(self):
        """Test inequality when fields differ."""
        image1 = ClonezillaImage(
            name="test1",
            path=Path("/test"),
            parts=["sda1"],
            partition_table=None
        )

        image2 = ClonezillaImage(
            name="test2",
            path=Path("/test"),
            parts=["sda1"],
            partition_table=None
        )

        assert image1 != image2


class TestDiskLayoutOp:
    def test_create_disk_layout_op_with_contents(self):
        """Test creating a DiskLayoutOp with contents."""
        op = DiskLayoutOp(
            kind="gpt",
            path=Path("/dev/sda"),
            contents="partition table data",
            size_bytes=512000000000
        )

        assert op.kind == "gpt"
        assert op.path == Path("/dev/sda")
        assert op.contents == "partition table data"
        assert op.size_bytes == 512000000000

    def test_create_disk_layout_op_without_contents(self):
        """Test creating a DiskLayoutOp without contents."""
        op = DiskLayoutOp(
            kind="mbr",
            path=Path("/dev/sdb"),
            contents=None,
            size_bytes=256000000000
        )

        assert op.kind == "mbr"
        assert op.path == Path("/dev/sdb")
        assert op.contents is None
        assert op.size_bytes == 256000000000

    def test_disk_layout_op_with_zero_size(self):
        """Test creating a DiskLayoutOp with zero size."""
        op = DiskLayoutOp(
            kind="gpt",
            path=Path("/dev/sdc"),
            contents=None,
            size_bytes=0
        )

        assert op.size_bytes == 0

    def test_disk_layout_op_is_frozen(self):
        """Test that DiskLayoutOp instances are immutable."""
        op = DiskLayoutOp(
            kind="gpt",
            path=Path("/dev/sda"),
            contents=None,
            size_bytes=1000
        )

        with pytest.raises(AttributeError):
            op.kind = "mbr"

        with pytest.raises(AttributeError):
            op.size_bytes = 2000

    def test_disk_layout_op_equality(self):
        """Test equality comparison between DiskLayoutOp instances."""
        op1 = DiskLayoutOp(
            kind="gpt",
            path=Path("/dev/sda"),
            contents="data",
            size_bytes=1000
        )

        op2 = DiskLayoutOp(
            kind="gpt",
            path=Path("/dev/sda"),
            contents="data",
            size_bytes=1000
        )

        assert op1 == op2


class TestPartitionRestoreOp:
    def test_create_partition_restore_op_compressed(self):
        """Test creating a PartitionRestoreOp for compressed partition."""
        image_files = [
            Path("/images/test/sda1.ext4-ptcl-img.gz.aa"),
            Path("/images/test/sda1.ext4-ptcl-img.gz.ab")
        ]

        op = PartitionRestoreOp(
            partition="sda1",
            image_files=image_files,
            tool="partclone.ext4",
            fstype="ext4",
            compressed=True
        )

        assert op.partition == "sda1"
        assert op.image_files == image_files
        assert op.tool == "partclone.ext4"
        assert op.fstype == "ext4"
        assert op.compressed is True

    def test_create_partition_restore_op_uncompressed(self):
        """Test creating a PartitionRestoreOp for uncompressed partition."""
        image_files = [Path("/images/test/sda2.ntfs-ptcl-img.aa")]

        op = PartitionRestoreOp(
            partition="sda2",
            image_files=image_files,
            tool="partclone.ntfs",
            fstype="ntfs",
            compressed=False
        )

        assert op.partition == "sda2"
        assert op.image_files == image_files
        assert op.tool == "partclone.ntfs"
        assert op.fstype == "ntfs"
        assert op.compressed is False

    def test_create_partition_restore_op_without_fstype(self):
        """Test creating a PartitionRestoreOp without fstype."""
        image_files = [Path("/images/test/sda3.dd-img")]

        op = PartitionRestoreOp(
            partition="sda3",
            image_files=image_files,
            tool="dd",
            fstype=None,
            compressed=False
        )

        assert op.partition == "sda3"
        assert op.image_files == image_files
        assert op.tool == "dd"
        assert op.fstype is None
        assert op.compressed is False

    def test_partition_restore_op_with_single_file(self):
        """Test PartitionRestoreOp with single image file."""
        image_files = [Path("/images/test/sda1.ext4-ptcl-img")]

        op = PartitionRestoreOp(
            partition="sda1",
            image_files=image_files,
            tool="partclone.ext4",
            fstype="ext4",
            compressed=False
        )

        assert len(op.image_files) == 1
        assert op.image_files[0] == Path("/images/test/sda1.ext4-ptcl-img")

    def test_partition_restore_op_with_multiple_files(self):
        """Test PartitionRestoreOp with multiple split image files."""
        image_files = [
            Path("/images/test/sda1.aa"),
            Path("/images/test/sda1.ab"),
            Path("/images/test/sda1.ac"),
        ]

        op = PartitionRestoreOp(
            partition="sda1",
            image_files=image_files,
            tool="partclone.ext4",
            fstype="ext4",
            compressed=True
        )

        assert len(op.image_files) == 3

    def test_partition_restore_op_is_frozen(self):
        """Test that PartitionRestoreOp instances are immutable."""
        op = PartitionRestoreOp(
            partition="sda1",
            image_files=[Path("/test")],
            tool="partclone.ext4",
            fstype="ext4",
            compressed=True
        )

        with pytest.raises(AttributeError):
            op.partition = "sda2"

        with pytest.raises(AttributeError):
            op.compressed = False

    def test_partition_restore_op_equality(self):
        """Test equality comparison between PartitionRestoreOp instances."""
        files = [Path("/test/sda1.img")]

        op1 = PartitionRestoreOp(
            partition="sda1",
            image_files=files,
            tool="partclone.ext4",
            fstype="ext4",
            compressed=True
        )

        op2 = PartitionRestoreOp(
            partition="sda1",
            image_files=files,
            tool="partclone.ext4",
            fstype="ext4",
            compressed=True
        )

        assert op1 == op2


class TestRestorePlan:
    def test_create_restore_plan_complete(self):
        """Test creating a complete RestorePlan with all operations."""
        image_dir = Path("/images/test")
        parts = ["sda1", "sda2"]

        disk_layout_ops = [
            DiskLayoutOp(
                kind="gpt",
                path=Path("/dev/sda"),
                contents="pt data",
                size_bytes=512000000000
            )
        ]

        partition_ops = [
            PartitionRestoreOp(
                partition="sda1",
                image_files=[Path("/images/test/sda1.img")],
                tool="partclone.ext4",
                fstype="ext4",
                compressed=True
            ),
            PartitionRestoreOp(
                partition="sda2",
                image_files=[Path("/images/test/sda2.img")],
                tool="partclone.ext4",
                fstype="ext4",
                compressed=True
            )
        ]

        plan = RestorePlan(
            image_dir=image_dir,
            parts=parts,
            disk_layout_ops=disk_layout_ops,
            partition_ops=partition_ops
        )

        assert plan.image_dir == image_dir
        assert plan.parts == parts
        assert len(plan.disk_layout_ops) == 1
        assert len(plan.partition_ops) == 2

    def test_create_restore_plan_empty_operations(self):
        """Test creating a RestorePlan with empty operation lists."""
        plan = RestorePlan(
            image_dir=Path("/images/empty"),
            parts=[],
            disk_layout_ops=[],
            partition_ops=[]
        )

        assert plan.image_dir == Path("/images/empty")
        assert plan.parts == []
        assert plan.disk_layout_ops == []
        assert plan.partition_ops == []

    def test_create_restore_plan_multiple_disk_layouts(self):
        """Test creating a RestorePlan with multiple disk layout operations."""
        disk_layout_ops = [
            DiskLayoutOp(
                kind="gpt",
                path=Path("/dev/sda"),
                contents=None,
                size_bytes=1000000000
            ),
            DiskLayoutOp(
                kind="mbr",
                path=Path("/dev/sdb"),
                contents="mbr data",
                size_bytes=500000000
            )
        ]

        plan = RestorePlan(
            image_dir=Path("/images/test"),
            parts=["sda1", "sdb1"],
            disk_layout_ops=disk_layout_ops,
            partition_ops=[]
        )

        assert len(plan.disk_layout_ops) == 2
        assert plan.disk_layout_ops[0].kind == "gpt"
        assert plan.disk_layout_ops[1].kind == "mbr"

    def test_restore_plan_is_frozen(self):
        """Test that RestorePlan instances are immutable."""
        plan = RestorePlan(
            image_dir=Path("/test"),
            parts=["sda1"],
            disk_layout_ops=[],
            partition_ops=[]
        )

        with pytest.raises(AttributeError):
            plan.image_dir = Path("/other")

        with pytest.raises(AttributeError):
            plan.parts = ["sda2"]

    def test_restore_plan_equality(self):
        """Test equality comparison between RestorePlan instances."""
        ops = [
            DiskLayoutOp(
                kind="gpt",
                path=Path("/dev/sda"),
                contents=None,
                size_bytes=1000
            )
        ]

        plan1 = RestorePlan(
            image_dir=Path("/test"),
            parts=["sda1"],
            disk_layout_ops=ops,
            partition_ops=[]
        )

        plan2 = RestorePlan(
            image_dir=Path("/test"),
            parts=["sda1"],
            disk_layout_ops=ops,
            partition_ops=[]
        )

        assert plan1 == plan2

    def test_restore_plan_with_complex_scenario(self):
        """Test RestorePlan with a complex multi-partition restore scenario."""
        image_dir = Path("/images/complex")
        parts = ["sda1", "sda2", "sda3", "sda5"]

        disk_layout_ops = [
            DiskLayoutOp(
                kind="gpt",
                path=Path("/dev/sda"),
                contents="GPT partition table",
                size_bytes=1000000000000
            )
        ]

        partition_ops = [
            PartitionRestoreOp(
                partition="sda1",
                image_files=[Path("/images/complex/sda1.ext4-ptcl-img.gz.aa")],
                tool="partclone.ext4",
                fstype="ext4",
                compressed=True
            ),
            PartitionRestoreOp(
                partition="sda2",
                image_files=[
                    Path("/images/complex/sda2.ntfs-ptcl-img.aa"),
                    Path("/images/complex/sda2.ntfs-ptcl-img.ab"),
                ],
                tool="partclone.ntfs",
                fstype="ntfs",
                compressed=False
            ),
            PartitionRestoreOp(
                partition="sda3",
                image_files=[Path("/images/complex/sda3.dd-img")],
                tool="dd",
                fstype=None,
                compressed=False
            ),
            PartitionRestoreOp(
                partition="sda5",
                image_files=[Path("/images/complex/sda5.fat32-ptcl-img")],
                tool="partclone.fat32",
                fstype="vfat",
                compressed=False
            )
        ]

        plan = RestorePlan(
            image_dir=image_dir,
            parts=parts,
            disk_layout_ops=disk_layout_ops,
            partition_ops=partition_ops
        )

        assert len(plan.parts) == 4
        assert len(plan.disk_layout_ops) == 1
        assert len(plan.partition_ops) == 4
        assert plan.partition_ops[0].compressed is True
        assert plan.partition_ops[1].compressed is False
        assert plan.partition_ops[2].tool == "dd"
        assert plan.partition_ops[3].fstype == "vfat"
