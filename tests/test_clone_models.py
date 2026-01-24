"""Tests for clone operation display helpers and models."""


from rpi_usb_cloner.storage.clone.models import (
    format_filesystem_type,
    get_partition_display_name,
    get_partition_number,
    normalize_clone_mode,
    resolve_device_node,
)


class TestGetPartitionDisplayName:
    """Tests for get_partition_display_name function."""

    def test_display_name_from_partlabel(self):
        """Test display name from GPT partition label."""
        part = {"partlabel": "EFI System", "label": "BOOT", "name": "sda1"}
        assert get_partition_display_name(part) == "EFI System"

    def test_display_name_from_label(self):
        """Test display name from filesystem label."""
        part = {"partlabel": "", "label": "BOOT", "name": "sda1"}
        assert get_partition_display_name(part) == "BOOT"

    def test_display_name_from_name(self):
        """Test display name from partition name."""
        part = {"partlabel": "", "label": "", "name": "sda1"}
        assert get_partition_display_name(part) == "sda1"

    def test_display_name_fallback(self):
        """Test fallback to 'partition' when no info available."""
        part = {"partlabel": "", "label": "", "name": ""}
        assert get_partition_display_name(part) == "partition"

    def test_display_name_missing_keys(self):
        """Test with missing keys in partition dict."""
        part = {"name": "sda1"}
        assert get_partition_display_name(part) == "sda1"

    def test_display_name_whitespace_partlabel(self):
        """Test that whitespace-only partlabel is ignored."""
        part = {"partlabel": "   ", "label": "DATA", "name": "sda1"}
        assert get_partition_display_name(part) == "DATA"

    def test_display_name_whitespace_label(self):
        """Test that whitespace-only label is ignored."""
        part = {"partlabel": "", "label": "   ", "name": "sda1"}
        assert get_partition_display_name(part) == "sda1"


class TestFormatFilesystemType:
    """Tests for format_filesystem_type function."""

    def test_format_vfat(self):
        """Test formatting vfat filesystem."""
        assert format_filesystem_type("vfat") == "FAT32"

    def test_format_fat16(self):
        """Test formatting fat16 filesystem."""
        assert format_filesystem_type("fat16") == "FAT16"

    def test_format_fat32(self):
        """Test formatting fat32 filesystem."""
        assert format_filesystem_type("fat32") == "FAT32"

    def test_format_ntfs(self):
        """Test formatting NTFS filesystem."""
        assert format_filesystem_type("ntfs") == "NTFS"

    def test_format_exfat(self):
        """Test formatting exFAT filesystem."""
        assert format_filesystem_type("exfat") == "exFAT"

    def test_format_ext2(self):
        """Test formatting ext2 filesystem."""
        assert format_filesystem_type("ext2") == "ext2"

    def test_format_ext3(self):
        """Test formatting ext3 filesystem."""
        assert format_filesystem_type("ext3") == "ext3"

    def test_format_ext4(self):
        """Test formatting ext4 filesystem."""
        assert format_filesystem_type("ext4") == "ext4"

    def test_format_xfs(self):
        """Test formatting XFS filesystem."""
        assert format_filesystem_type("xfs") == "XFS"

    def test_format_btrfs(self):
        """Test formatting Btrfs filesystem."""
        assert format_filesystem_type("btrfs") == "Btrfs"

    def test_format_case_insensitive(self):
        """Test that filesystem types are case-insensitive."""
        assert format_filesystem_type("VFAT") == "FAT32"
        assert format_filesystem_type("NTFS") == "NTFS"
        assert format_filesystem_type("EXT4") == "ext4"

    def test_format_unknown_filesystem(self):
        """Test formatting unknown filesystem type."""
        assert format_filesystem_type("zfs") == "zfs"
        assert format_filesystem_type("unknown") == "unknown"

    def test_format_empty_filesystem(self):
        """Test formatting empty filesystem type."""
        assert format_filesystem_type("") == "unknown"

    def test_format_none_filesystem(self):
        """Test formatting None filesystem type."""
        assert format_filesystem_type(None) == "unknown"


class TestGetPartitionNumber:
    """Tests for get_partition_number function."""

    def test_get_number_standard_partition(self):
        """Test extracting number from standard partition name."""
        assert get_partition_number("sda1") == 1
        assert get_partition_number("sdb5") == 5
        assert get_partition_number("sdc10") == 10

    def test_get_number_nvme_partition(self):
        """Test extracting number from NVMe partition name."""
        assert get_partition_number("nvme0n1p1") == 1
        assert get_partition_number("nvme0n1p2") == 2
        assert get_partition_number("nvme1n1p5") == 5

    def test_get_number_mmc_partition(self):
        """Test extracting number from MMC partition name."""
        assert get_partition_number("mmcblk0p1") == 1
        assert get_partition_number("mmcblk1p3") == 3

    def test_get_number_no_partition(self):
        """Test None is returned for device without partition number."""
        assert get_partition_number("sda") is None
        assert get_partition_number("loop") is None

    def test_get_number_empty_name(self):
        """Test None is returned for empty name."""
        assert get_partition_number("") is None

    def test_get_number_none_name(self):
        """Test None is returned for None name."""
        assert get_partition_number(None) is None

    def test_get_number_invalid_name(self):
        """Test None is returned for invalid partition name."""
        assert get_partition_number("not-a-partition") is None
        assert get_partition_number("abc") is None


class TestNormalizeCloneMode:
    """Tests for normalize_clone_mode function."""

    def test_normalize_smart(self):
        """Test normalizing 'smart' mode."""
        assert normalize_clone_mode("smart") == "smart"
        assert normalize_clone_mode("SMART") == "smart"

    def test_normalize_exact(self):
        """Test normalizing 'exact' mode."""
        assert normalize_clone_mode("exact") == "exact"
        assert normalize_clone_mode("EXACT") == "exact"

    def test_normalize_verify(self):
        """Test normalizing 'verify' mode."""
        assert normalize_clone_mode("verify") == "verify"
        assert normalize_clone_mode("VERIFY") == "verify"

    def test_normalize_raw_to_exact(self):
        """Test normalizing 'raw' mode to 'exact'."""
        assert normalize_clone_mode("raw") == "exact"
        assert normalize_clone_mode("RAW") == "exact"

    def test_normalize_none(self):
        """Test None defaults to 'smart'."""
        assert normalize_clone_mode(None) == "smart"

    def test_normalize_empty_string(self):
        """Test empty string defaults to 'smart'."""
        assert normalize_clone_mode("") == "smart"

    def test_normalize_unknown_mode(self):
        """Test unknown mode defaults to 'smart'."""
        assert normalize_clone_mode("unknown") == "smart"
        assert normalize_clone_mode("invalid") == "smart"

    def test_normalize_case_insensitive(self):
        """Test mode normalization is case-insensitive."""
        assert normalize_clone_mode("SmArT") == "smart"
        assert normalize_clone_mode("ExAcT") == "exact"
        assert normalize_clone_mode("VeRiFy") == "verify"


class TestResolveDeviceNode:
    """Tests for resolve_device_node function."""

    def test_resolve_from_dict(self):
        """Test resolving device node from device dict."""
        device = {"name": "sda", "size": 32000000000}
        assert resolve_device_node(device) == "/dev/sda"

    def test_resolve_from_string_without_dev(self):
        """Test resolving device node from plain string."""
        assert resolve_device_node("sda") == "/dev/sda"
        assert resolve_device_node("sdb1") == "/dev/sdb1"

    def test_resolve_from_string_with_dev(self):
        """Test resolving device node from /dev/ path."""
        assert resolve_device_node("/dev/sda") == "/dev/sda"
        assert resolve_device_node("/dev/sdb1") == "/dev/sdb1"

    def test_resolve_nvme_device(self):
        """Test resolving NVMe device node."""
        device = {"name": "nvme0n1"}
        assert resolve_device_node(device) == "/dev/nvme0n1"

    def test_resolve_mmc_device(self):
        """Test resolving MMC device node."""
        device = {"name": "mmcblk0"}
        assert resolve_device_node(device) == "/dev/mmcblk0"

    def test_resolve_partition(self):
        """Test resolving partition device node."""
        device = {"name": "sda1"}
        assert resolve_device_node(device) == "/dev/sda1"

    def test_resolve_dict_minimal(self):
        """Test resolving with minimal device dict."""
        device = {"name": "sdc"}
        assert resolve_device_node(device) == "/dev/sdc"

    def test_resolve_string_edge_cases(self):
        """Test resolving various string formats."""
        # Already has /dev/
        assert resolve_device_node("/dev/sda") == "/dev/sda"
        # Doesn't have /dev/
        assert resolve_device_node("sda") == "/dev/sda"
        # Complex partition names
        assert resolve_device_node("nvme0n1p1") == "/dev/nvme0n1p1"
        assert resolve_device_node("/dev/nvme0n1p1") == "/dev/nvme0n1p1"
