"""Tests for Clonezilla partition table operations."""

import struct
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rpi_usb_cloner.storage.clonezilla.models import DiskLayoutOp
from rpi_usb_cloner.storage.clonezilla.partition_table import (
    apply_disk_layout_op,
    build_partition_mode_layout_ops,
    build_sfdisk_script_from_parted,
    collect_disk_layout_ops,
    estimate_last_lba_from_sgdisk_backup,
    estimate_required_size_bytes,
    expand_parted_compact_script,
    format_command_failure,
    format_sfdisk_line,
    get_sfdisk_int_field,
    is_parted_print_output,
    looks_like_sfdisk_script,
    normalize_parted_label,
    normalize_partition_mode,
    parse_parted_layout,
    parse_parted_sector,
    parse_sfdisk_fields,
    read_disk_layout_op,
    scale_partition_geometry,
    scale_sfdisk_layout,
    select_disk_layout_ops,
    set_sfdisk_field,
)


class TestCollectDiskLayoutOps:
    def test_collect_disk_layout_ops_disk_file(self, tmp_path):
        """Test collecting disk layout operation from disk file."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "disk").write_text(
            "label: dos\n/dev/sda1 : start=2048, size=10000"
        )

        ops = collect_disk_layout_ops(image_dir)
        assert len(ops) >= 1
        disk_op = next((op for op in ops if op.kind == "disk"), None)
        assert disk_op is not None

    def test_collect_disk_layout_ops_sfdisk_file(self, tmp_path):
        """Test collecting sfdisk layout operation."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "sfdisk").write_text("label: gpt\n")

        ops = collect_disk_layout_ops(image_dir)
        sfdisk_op = next((op for op in ops if op.kind == "sfdisk"), None)
        assert sfdisk_op is not None

    def test_collect_disk_layout_ops_pt_parted(self, tmp_path):
        """Test collecting parted partition table."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "sda-pt.parted").write_text("unit s\nmklabel gpt\n")

        ops = collect_disk_layout_ops(image_dir)
        parted_op = next((op for op in ops if op.kind == "pt.parted"), None)
        assert parted_op is not None

    def test_collect_disk_layout_ops_pt_sf(self, tmp_path):
        """Test collecting pt.sf files."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "sda-pt.sf").write_text("partition table")

        ops = collect_disk_layout_ops(image_dir)
        sf_op = next((op for op in ops if op.kind == "pt.sf"), None)
        assert sf_op is not None

    def test_collect_disk_layout_ops_empty_dir(self, tmp_path):
        """Test collecting from empty directory."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()

        ops = collect_disk_layout_ops(image_dir)
        assert ops == []

    def test_collect_disk_layout_ops_no_select(self, tmp_path):
        """Test collecting without selection/prioritization."""
        image_dir = tmp_path / "image"
        image_dir.mkdir()
        (image_dir / "sda-pt.parted").write_text("parted script")
        (image_dir / "sda-pt.sf").write_text("sf data")

        ops = collect_disk_layout_ops(image_dir, select=False)
        assert len(ops) >= 2


class TestSelectDiskLayoutOps:
    def test_select_disk_layout_ops_prioritizes_sgdisk(self):
        """Test that pt.sgdisk has highest priority."""
        ops = [
            DiskLayoutOp(
                kind="pt.parted", path=Path("/a"), contents="", size_bytes=100
            ),
            DiskLayoutOp(
                kind="pt.sgdisk", path=Path("/b"), contents="", size_bytes=100
            ),
            DiskLayoutOp(kind="sfdisk", path=Path("/c"), contents="", size_bytes=100),
        ]

        result = select_disk_layout_ops(ops)
        assert result[0].kind == "pt.sgdisk"

    def test_select_disk_layout_ops_empty(self):
        """Test selecting from empty list."""
        result = select_disk_layout_ops([])
        assert result == []

    def test_select_disk_layout_ops_full_priority_order(self):
        """Test complete priority ordering."""
        ops = [
            DiskLayoutOp(kind="disk", path=Path("/a"), contents="", size_bytes=100),
            DiskLayoutOp(kind="gpt", path=Path("/b"), contents="", size_bytes=100),
            DiskLayoutOp(
                kind="pt.sgdisk", path=Path("/c"), contents="", size_bytes=100
            ),
        ]

        result = select_disk_layout_ops(ops)
        assert result[0].kind == "pt.sgdisk"
        assert result[1].kind == "gpt"
        assert result[2].kind == "disk"


class TestReadDiskLayoutOp:
    def test_read_disk_layout_op_text_file(self, tmp_path):
        """Test reading text-based layout file."""
        path = tmp_path / "sda-pt.sf"
        content = "label: gpt\n/dev/sda1 : start=2048"
        path.write_text(content, newline="")  # Preserve Unix line endings

        op = read_disk_layout_op("pt.sf", path)
        assert op.kind == "pt.sf"
        assert op.path == path
        assert op.contents == content
        assert op.size_bytes == len(content.encode())

    def test_read_disk_layout_op_binary_file(self, tmp_path):
        """Test reading binary layout file."""
        path = tmp_path / "sda-mbr"
        binary_data = b"\x00\x01\x02\x03" + b"\x00" * 508
        path.write_bytes(binary_data)

        op = read_disk_layout_op("mbr", path)
        assert op.kind == "mbr"
        assert op.contents is None  # Binary files have no text contents
        assert op.size_bytes == len(binary_data)

    def test_read_disk_layout_op_mixed_content(self, tmp_path):
        """Test reading file with null byte in first 1024 bytes."""
        path = tmp_path / "mixed"
        content = b"text\x00binary"
        path.write_bytes(content)

        op = read_disk_layout_op("test", path)
        assert op.contents is None  # Contains null byte, treated as binary


class TestEstimateRequiredSizeBytes:
    def test_estimate_from_last_lba(self):
        """Test estimating size from last-lba field."""
        op = DiskLayoutOp(
            kind="pt.sf",
            path=Path("/test"),
            contents="last-lba: 1000000\nsector-size: 512",
            size_bytes=100,
        )

        size = estimate_required_size_bytes([op])
        assert size == (1000000 + 1) * 512

    def test_estimate_from_partition_end(self):
        """Test estimating size from partition start+size."""
        op = DiskLayoutOp(
            kind="sfdisk",
            path=Path("/test"),
            contents="/dev/sda1 : start=2048, size=100000",
            size_bytes=100,
        )

        size = estimate_required_size_bytes([op])
        assert size == (2048 + 100000) * 512  # Default sector size

    def test_estimate_with_custom_sector_size(self):
        """Test estimating with custom sector size."""
        op = DiskLayoutOp(
            kind="sfdisk",
            path=Path("/test"),
            contents="sector-size: 4096\n/dev/sda1 : start=100, size=1000",
            size_bytes=100,
        )

        size = estimate_required_size_bytes([op])
        assert size == (100 + 1000) * 4096

    def test_estimate_no_data(self):
        """Test when no size information is available."""
        op = DiskLayoutOp(
            kind="test", path=Path("/test"), contents="no useful data", size_bytes=100
        )

        size = estimate_required_size_bytes([op])
        assert size is None

    def test_estimate_empty_list(self):
        """Test with empty operation list."""
        size = estimate_required_size_bytes([])
        assert size is None

    def test_estimate_from_sgdisk_backup(self, tmp_path):
        """Test estimating size from binary sgdisk backup (GPT)."""
        path = tmp_path / "sda-pt.sgdisk"
        gpt_header = bytearray(512)
        gpt_header[0:8] = b"EFI PART"
        struct.pack_into("<Q", gpt_header, 24, 100)
        struct.pack_into("<Q", gpt_header, 32, 200)
        struct.pack_into("<Q", gpt_header, 48, 150)
        path.write_bytes(bytes(gpt_header))

        op = DiskLayoutOp(kind="pt.sgdisk", path=path, contents=None, size_bytes=512)

        size = estimate_required_size_bytes([op])

        assert size == (200 + 1) * 512


class TestEstimateLastLbaFromSgdiskBackup:
    def test_estimate_last_lba_valid_gpt(self, tmp_path):
        """Test extracting LBA from valid GPT header."""
        path = tmp_path / "gpt-backup"

        # Create minimal GPT header structure
        gpt_header = bytearray(512)
        gpt_header[0:8] = b"EFI PART"  # Signature
        struct.pack_into("<Q", gpt_header, 24, 1000)  # Current LBA
        struct.pack_into("<Q", gpt_header, 32, 2000)  # Backup LBA
        struct.pack_into("<Q", gpt_header, 48, 1999)  # Last usable LBA

        path.write_bytes(bytes(gpt_header))

        lba = estimate_last_lba_from_sgdisk_backup(path)
        assert lba == 2000  # Maximum of the three values

    def test_estimate_last_lba_no_signature(self, tmp_path):
        """Test when EFI PART signature is not found."""
        path = tmp_path / "invalid"
        path.write_bytes(b"invalid data" * 100)

        lba = estimate_last_lba_from_sgdisk_backup(path)
        assert lba is None

    def test_estimate_last_lba_truncated_file(self, tmp_path):
        """Test with file too small to contain GPT header."""
        path = tmp_path / "truncated"
        path.write_bytes(b"EFI PART" + b"\x00" * 10)

        lba = estimate_last_lba_from_sgdisk_backup(path)
        assert lba is None


class TestNormalizePartitionMode:
    def test_normalize_partition_mode_k0(self):
        """Test normalizing k0 mode."""
        assert normalize_partition_mode("k0") == "k0"

    def test_normalize_partition_mode_k(self):
        """Test normalizing k mode."""
        assert normalize_partition_mode("k") == "k"

    def test_normalize_partition_mode_with_dash(self):
        """Test normalizing mode with leading dash."""
        assert normalize_partition_mode("-k1") == "k1"

    def test_normalize_partition_mode_uppercase(self):
        """Test normalizing uppercase mode."""
        assert normalize_partition_mode("K2") == "k2"

    def test_normalize_partition_mode_whitespace(self):
        """Test normalizing mode with whitespace."""
        assert normalize_partition_mode("  k1  ") == "k1"

    def test_normalize_partition_mode_none(self):
        """Test normalizing None."""
        assert normalize_partition_mode(None) == "k0"

    def test_normalize_partition_mode_empty(self):
        """Test normalizing empty string."""
        assert normalize_partition_mode("") == "k0"


class TestBuildPartitionModeLayoutOps:
    def test_build_partition_mode_layout_ops_invalid(self):
        """Test invalid partition mode raises."""
        with pytest.raises(RuntimeError, match="Unsupported partition mode"):
            build_partition_mode_layout_ops([], partition_mode="k3", target_size=None)

    def test_build_partition_mode_layout_ops_k2(self):
        """Test k2 returns no layout ops."""
        op = DiskLayoutOp(
            kind="sfdisk", path=Path("/test"), contents="data", size_bytes=1
        )

        result = build_partition_mode_layout_ops(
            [op], partition_mode="k2", target_size=10
        )

        assert result == []

    def test_build_partition_mode_layout_ops_k0(self):
        """Test k0 retains original layout ops."""
        op = DiskLayoutOp(
            kind="sfdisk", path=Path("/test"), contents="data", size_bytes=1
        )

        result = build_partition_mode_layout_ops(
            [op], partition_mode="k0", target_size=10
        )

        assert result == [op]

    def test_build_partition_mode_layout_ops_k1_scaling(self):
        """Test k1 uses scaled layout when available."""
        op = DiskLayoutOp(
            kind="sfdisk",
            path=Path("/test"),
            contents="label: dos\nsector-size: 512\n/dev/sda1 : start=2048, size=10000",
            size_bytes=100,
        )

        result = build_partition_mode_layout_ops(
            [op], partition_mode="k1", target_size=50000 * 512
        )

        assert len(result) == 1
        assert result[0].kind == "sfdisk"
        assert "start=" in result[0].contents


class TestParseSfdiskFields:
    def test_parse_sfdisk_fields_simple(self):
        """Test parsing simple sfdisk fields."""
        result = parse_sfdisk_fields("start=2048, size=10000")
        assert result == [("start", "2048"), ("size", "10000")]

    def test_parse_sfdisk_fields_with_bootable(self):
        """Test parsing fields with bootable flag."""
        result = parse_sfdisk_fields("start=2048, size=10000, bootable")
        assert ("bootable", "") in result

    def test_parse_sfdisk_fields_empty(self):
        """Test parsing empty string."""
        result = parse_sfdisk_fields("")
        assert result == []

    def test_parse_sfdisk_fields_with_type(self):
        """Test parsing fields with partition type."""
        result = parse_sfdisk_fields("start=2048, size=10000, type=83")
        assert ("type", "83") in result


class TestGetSfdiskIntField:
    def test_get_sfdisk_int_field_found(self):
        """Test getting existing integer field."""
        fields = [("start", "2048"), ("size", "10000")]
        assert get_sfdisk_int_field(fields, "start") == 2048

    def test_get_sfdisk_int_field_with_suffix(self):
        """Test getting field with 's' suffix."""
        fields = [("start", "2048s")]
        assert get_sfdisk_int_field(fields, "start") == 2048

    def test_get_sfdisk_int_field_not_found(self):
        """Test getting non-existent field."""
        fields = [("start", "2048")]
        assert get_sfdisk_int_field(fields, "missing") is None

    def test_get_sfdisk_int_field_invalid_format(self):
        """Test getting field with invalid format."""
        fields = [("start", "invalid")]
        assert get_sfdisk_int_field(fields, "start") is None


class TestSetSfdiskField:
    def test_set_sfdisk_field_update_existing(self):
        """Test updating existing field."""
        fields = [("start", "2048"), ("size", "10000")]
        result = set_sfdisk_field(fields, "start", "4096")
        assert result == [("start", "4096"), ("size", "10000")]

    def test_set_sfdisk_field_add_new(self):
        """Test adding new field."""
        fields = [("start", "2048")]
        result = set_sfdisk_field(fields, "size", "10000")
        assert ("size", "10000") in result

    def test_set_sfdisk_field_empty_list(self):
        """Test adding field to empty list."""
        result = set_sfdisk_field([], "start", "2048")
        assert result == [("start", "2048")]


class TestFormatSfdiskLine:
    def test_format_sfdisk_line_with_values(self):
        """Test formatting sfdisk line with field values."""
        fields = [("start", "2048"), ("size", "10000")]
        result = format_sfdisk_line("/dev/sda1", fields)
        assert result == "/dev/sda1 : start=2048, size=10000"

    def test_format_sfdisk_line_with_flag(self):
        """Test formatting line with flag (no value)."""
        fields = [("start", "2048"), ("bootable", "")]
        result = format_sfdisk_line("/dev/sda1", fields)
        assert result == "/dev/sda1 : start=2048, bootable"

    def test_format_sfdisk_line_empty_fields(self):
        """Test formatting line with no fields."""
        result = format_sfdisk_line("/dev/sda1", [])
        assert result == "/dev/sda1 : "


class TestScalePartitionGeometry:
    def test_scale_partition_geometry_simple(self):
        """Test scaling single partition."""
        partitions = [{"start": 2048, "size": 100000, "number": 1}]

        result = scale_partition_geometry(
            partitions, target_sectors=200000, sector_size=512, layout_label="test"
        )

        assert result is not None
        assert result[0]["new_start"] == 2048
        assert result[0]["new_size"] > 100000  # Should be scaled up

    def test_scale_partition_geometry_multiple_partitions(self):
        """Test scaling multiple partitions."""
        partitions = [
            {"start": 2048, "size": 50000, "number": 1},
            {"start": 52048, "size": 50000, "number": 2},
        ]

        result = scale_partition_geometry(
            partitions, target_sectors=300000, sector_size=512, layout_label="test"
        )

        assert result is not None
        assert len(result) == 2
        # Last partition should expand to fill remaining space
        assert result[1]["new_start"] + result[1]["new_size"] == 300000

    def test_scale_partition_geometry_no_partitions(self):
        """Test scaling empty partition list."""
        result = scale_partition_geometry(
            [], target_sectors=100000, sector_size=512, layout_label="test"
        )

        assert result is None

    def test_scale_partition_geometry_target_too_small(self):
        """Test when target is smaller than source."""
        partitions = [{"start": 2048, "size": 100000, "number": 1}]

        result = scale_partition_geometry(
            partitions,
            target_sectors=50000,  # Smaller than partition end
            sector_size=512,
            layout_label="test",
        )

        assert result is None


class TestApplyDiskLayoutOp:
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_apply_disk_layout_op_mbr_failure(self, mock_run, mock_which, tmp_path):
        """Test mbr apply surfaces dd failure."""
        mock_which.return_value = "/usr/bin/dd"
        mock_run.return_value = Mock(
            returncode=1, stderr="dd error", stdout="", args=["dd", "if=/dev/sda"]
        )

        path = tmp_path / "sda-mbr"
        path.write_bytes(b"\x00" * 512)
        op = DiskLayoutOp(kind="mbr", path=path, contents=None, size_bytes=512)

        with pytest.raises(RuntimeError, match="dd failed"):
            apply_disk_layout_op(op, "/dev/sdb")


class TestParsePartedSector:
    def test_parse_parted_sector_with_suffix(self):
        """Test parsing sector value with 's' suffix."""
        assert parse_parted_sector("2048s", False) == 2048

    def test_parse_parted_sector_unit_is_sectors(self):
        """Test parsing when unit is sectors."""
        assert parse_parted_sector("2048", True) == 2048

    def test_parse_parted_sector_no_suffix_no_unit(self):
        """Test parsing without suffix when unit is not sectors."""
        assert parse_parted_sector("2048", False) is None

    def test_parse_parted_sector_invalid(self):
        """Test parsing invalid value."""
        assert parse_parted_sector("invalid", False) is None


class TestNormalizePartedLabel:
    def test_normalize_parted_label_gpt(self):
        """Test normalizing GPT label."""
        assert normalize_parted_label("GPT") == "gpt"

    def test_normalize_parted_label_msdos(self):
        """Test normalizing msdos to dos."""
        assert normalize_parted_label("msdos") == "dos"

    def test_normalize_parted_label_mbr(self):
        """Test normalizing mbr to dos."""
        assert normalize_parted_label("mbr") == "dos"

    def test_normalize_parted_label_dos(self):
        """Test normalizing dos label."""
        assert normalize_parted_label("dos") == "dos"

    def test_normalize_parted_label_unsupported(self):
        """Test normalizing unsupported label."""
        assert normalize_parted_label("unsupported") is None

    def test_normalize_parted_label_none(self):
        """Test normalizing None."""
        assert normalize_parted_label(None) is None

    def test_normalize_parted_label_whitespace(self):
        """Test normalizing with whitespace."""
        assert normalize_parted_label("  GPT  ") == "gpt"


class TestFormatCommandFailure:
    def test_format_command_failure_with_stderr(self):
        """Test formatting failure with stderr."""
        result = Mock()
        result.returncode = 1
        result.stderr = "error message"
        result.stdout = ""

        message = format_command_failure("Command failed", ["cmd", "arg"], result)
        assert "Command failed" in message
        assert "cmd arg" in message
        assert "stderr: error message" in message

    def test_format_command_failure_with_stdout(self):
        """Test formatting failure with stdout."""
        result = Mock()
        result.returncode = 1
        result.stderr = ""
        result.stdout = "output message"

        message = format_command_failure("Command failed", ["cmd"], result)
        assert "stdout: output message" in message

    def test_format_command_failure_both_streams(self):
        """Test formatting with both stderr and stdout."""
        result = Mock()
        result.returncode = 1
        result.stderr = "error"
        result.stdout = "output"

        message = format_command_failure("Failed", ["cmd"], result)
        assert "stderr: error" in message
        assert "stdout: output" in message

    def test_format_command_failure_no_output(self):
        """Test formatting with no output."""
        result = Mock()
        result.returncode = 1
        result.stderr = ""
        result.stdout = ""

        message = format_command_failure("Failed", ["cmd"], result)
        assert message == "Failed (cmd)"


class TestIsPartedPrintOutput:
    def test_is_parted_print_output_with_model(self):
        """Test detecting parted print output with Model."""
        assert is_parted_print_output("Model: ATA Samsung SSD") is True

    def test_is_parted_print_output_with_partition_table(self):
        """Test detecting output with Partition Table."""
        assert is_parted_print_output("Partition Table: gpt") is True

    def test_is_parted_print_output_with_number_header(self):
        """Test detecting output with Number Start header."""
        assert is_parted_print_output("Number  Start   End") is True

    def test_is_parted_print_output_script(self):
        """Test script is not detected as print output."""
        assert is_parted_print_output("unit s\nmklabel gpt") is False

    def test_is_parted_print_output_empty(self):
        """Test empty string."""
        assert is_parted_print_output("") is False


class TestExpandPartedCompactScript:
    def test_expand_parted_compact_script_semicolons(self):
        """Test expanding semicolon-separated commands."""
        compact = "unit s; mklabel gpt; mkpart primary 2048s 10000s"
        result = expand_parted_compact_script(compact)
        lines = result.split("\n")
        assert "unit s" in lines
        assert "mklabel gpt" in lines
        assert "mkpart primary 2048s 10000s" in lines

    def test_expand_parted_compact_script_multiline(self):
        """Test expanding multi-line compact script."""
        compact = "unit s; mklabel gpt\nmkpart primary 2048s 10000s"
        result = expand_parted_compact_script(compact)
        assert "unit s" in result
        assert "mklabel gpt" in result
        assert "mkpart primary 2048s 10000s" in result

    def test_expand_parted_compact_script_empty(self):
        """Test expanding empty script."""
        with pytest.raises(RuntimeError, match="Compact parted file is empty"):
            expand_parted_compact_script("")

    def test_expand_parted_compact_script_only_whitespace(self):
        """Test expanding script with only whitespace."""
        with pytest.raises(RuntimeError, match="Compact parted file is empty"):
            expand_parted_compact_script("   \n  \n  ")

    def test_expand_parted_compact_script_no_commands(self):
        """Test script with no actual commands."""
        with pytest.raises(RuntimeError, match="does not contain any commands"):
            expand_parted_compact_script("; ; ;")


class TestLooksLikeSfdiskScript:
    def test_looks_like_sfdisk_script_label(self):
        """Test detecting sfdisk script with label."""
        assert looks_like_sfdisk_script("label: gpt") is True

    def test_looks_like_sfdisk_script_device(self):
        """Test detecting script with device."""
        assert looks_like_sfdisk_script("/dev/sda1 : start=2048") is True

    def test_looks_like_sfdisk_script_unit(self):
        """Test detecting script with unit."""
        assert looks_like_sfdisk_script("unit: sectors") is True

    def test_looks_like_sfdisk_script_sector_size(self):
        """Test detecting script with sector-size."""
        assert looks_like_sfdisk_script("sector-size: 512") is True

    def test_looks_like_sfdisk_script_not_script(self):
        """Test non-script content."""
        assert looks_like_sfdisk_script("random text") is False

    def test_looks_like_sfdisk_script_empty(self):
        """Test empty content."""
        assert looks_like_sfdisk_script("") is False


class TestParsePartedLayout:
    def test_parse_parted_layout_print_output(self):
        """Test parsing parted print output."""
        content = """Model: ATA Samsung SSD
Disk /dev/sda: 2000398934016s
Sector size (logical/physical): 512B/512B
Partition Table: gpt

Number  Start   End          Size         File system
1       2048s   1050623s     1048576s     fat32
2       1050624s 1999999999s 1998949376s  ext4
"""
        result = parse_parted_layout(content)
        assert result is not None
        sector_size, label, partitions = result
        assert sector_size == 512
        assert label == "gpt"
        assert len(partitions) == 2
        assert partitions[0]["start"] == 2048
        assert partitions[0]["size"] == 1048576

    def test_parse_parted_layout_script_output(self):
        """Test parsing parted script with mkpart commands."""
        content = """unit s
mklabel gpt
mkpart primary 2048s 1050623s
mkpart primary 1050624s 1999999999s
"""
        result = parse_parted_layout(content)
        assert result is not None
        sector_size, label, partitions = result
        assert label == "gpt"
        assert len(partitions) == 2

    def test_parse_parted_layout_invalid(self):
        """Test parsing invalid content."""
        result = parse_parted_layout("invalid content")
        assert result is None

    def test_parse_parted_layout_empty(self):
        """Test parsing empty content."""
        result = parse_parted_layout("")
        assert result is None


class TestScaleSfdiskLayout:
    def test_scale_sfdisk_layout_simple(self):
        """Test scaling sfdisk layout."""
        op = DiskLayoutOp(
            kind="sfdisk",
            path=Path("/test"),
            contents="label: gpt\nsector-size: 512\n/dev/sda1 : start=2048, size=100000",
            size_bytes=100,
        )

        result = scale_sfdisk_layout(op, 500000 * 512)
        assert result is not None
        assert result.kind == "sfdisk"
        assert "start=" in result.contents
        # Size should be scaled

    def test_scale_sfdisk_layout_no_partitions(self):
        """Test scaling layout with no partitions."""
        op = DiskLayoutOp(
            kind="sfdisk", path=Path("/test"), contents="label: gpt\n", size_bytes=100
        )

        result = scale_sfdisk_layout(op, 1000000)
        assert result is None

    def test_scale_sfdisk_layout_wrong_kind(self):
        """Test scaling non-sfdisk operation."""
        op = DiskLayoutOp(
            kind="other", path=Path("/test"), contents="data", size_bytes=100
        )

        result = scale_sfdisk_layout(op, 1000000)
        assert result is None

    def test_scale_sfdisk_layout_no_contents(self):
        """Test scaling operation without contents."""
        op = DiskLayoutOp(
            kind="sfdisk", path=Path("/test"), contents=None, size_bytes=100
        )

        result = scale_sfdisk_layout(op, 1000000)
        assert result is None


class TestBuildSfdiskScriptFromParted:
    def test_build_sfdisk_script_gpt(self):
        """Test building sfdisk script from GPT parted layout."""
        partitions = [
            {
                "number": 1,
                "start": 2048,
                "size": 100000,
                "new_start": 2048,
                "new_size": 200000,
                "flags": [],
                "fstype": "ext4",
            }
        ]

        script = build_sfdisk_script_from_parted(
            label="gpt", sector_size=512, partitions=partitions
        )

        assert script is not None
        assert "label: gpt" in script
        assert "unit: sectors" in script
        assert "sector-size: 512" in script
        assert "start=2048" in script
        assert "size=200000" in script

    def test_build_sfdisk_script_dos_bootable(self):
        """Test building DOS script with bootable partition."""
        partitions = [
            {
                "number": 1,
                "start": 2048,
                "size": 100000,
                "new_start": 2048,
                "new_size": 100000,
                "flags": ["boot"],
                "fstype": "ext4",
            }
        ]

        script = build_sfdisk_script_from_parted(
            label="dos", sector_size=512, partitions=partitions
        )

        assert script is not None
        assert "label: dos" in script
        assert "bootable" in script

    def test_build_sfdisk_script_unsupported_label(self):
        """Test building script with unsupported label."""
        script = build_sfdisk_script_from_parted(
            label="unsupported", sector_size=512, partitions=[]
        )

        assert script is None

    def test_build_sfdisk_script_esp_partition(self):
        """Test building script with ESP partition."""
        partitions = [
            {
                "number": 1,
                "start": 2048,
                "size": 100000,
                "new_start": 2048,
                "new_size": 100000,
                "flags": ["esp"],
                "fstype": "fat32",
            }
        ]

        script = build_sfdisk_script_from_parted(
            label="gpt", sector_size=512, partitions=partitions
        )

        assert script is not None
        assert "type=EF00" in script
