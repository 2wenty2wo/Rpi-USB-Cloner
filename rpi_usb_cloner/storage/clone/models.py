"""Display helper functions for clone operations."""
import re


def get_partition_display_name(part):
    """Get a friendly display name for a partition.

    Returns the partition label if available, otherwise the partition name.
    """
    # Try partition label first (GPT)
    partlabel = part.get("partlabel", "").strip()
    if partlabel:
        return partlabel

    # Try filesystem label
    label = part.get("label", "").strip()
    if label:
        return label

    # Fall back to partition name (e.g., "sda1")
    name = part.get("name", "")
    if name:
        return name

    return "partition"


def format_filesystem_type(fstype):
    """Convert filesystem type to user-friendly display name.

    Args:
        fstype: Filesystem type string (e.g., "ext4", "vfat", "ntfs")

    Returns:
        Friendly display name (e.g., "ext4", "FAT32", "NTFS")
    """
    if not fstype:
        return "unknown"

    fstype_lower = fstype.lower()

    # Map filesystem types to friendly names
    friendly_names = {
        "vfat": "FAT32",
        "fat16": "FAT16",
        "fat32": "FAT32",
        "ntfs": "NTFS",
        "exfat": "exFAT",
        "ext2": "ext2",
        "ext3": "ext3",
        "ext4": "ext4",
        "xfs": "XFS",
        "btrfs": "Btrfs",
    }

    return friendly_names.get(fstype_lower, fstype)


def get_partition_number(name):
    """Extract partition number from device name."""
    if not name:
        return None
    match = re.search(r"(?:p)?(\d+)$", name)
    if not match:
        return None
    return int(match.group(1))


def normalize_clone_mode(mode):
    """Normalize clone mode string."""
    if not mode:
        return "smart"
    mode = mode.lower()
    if mode == "raw":
        return "exact"
    if mode in ("smart", "exact", "verify"):
        return mode
    return "smart"


def resolve_device_node(device):
    """Convert device name or dict to device node path."""
    if isinstance(device, str):
        return device if device.startswith("/dev/") else f"/dev/{device}"
    return f"/dev/{device.get('name')}"
