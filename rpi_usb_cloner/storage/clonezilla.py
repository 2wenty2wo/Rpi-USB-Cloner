"""Clonezilla disk image restoration (compatibility layer).

This module provides backwards compatibility by re-exporting functionality
from the refactored clonezilla package.

For new code, prefer importing directly from:
    rpi_usb_cloner.storage.clonezilla.*
"""

# Re-export all public APIs from the clonezilla package
from rpi_usb_cloner.storage.clonezilla import (
    ClonezillaImage,
    DiskLayoutOp,
    PartitionRestoreOp,
    RestorePlan,
    find_image_repository,
    find_partition_table,
    get_mountpoint,
    is_clonezilla_image_dir,
    list_clonezilla_image_dirs,
    load_image,
    parse_clonezilla_image,
    restore_clonezilla_image,
    restore_image,
    verify_restored_image,
)


__all__ = [
    "ClonezillaImage",
    "DiskLayoutOp",
    "PartitionRestoreOp",
    "RestorePlan",
    "find_image_repository",
    "find_partition_table",
    "get_mountpoint",
    "is_clonezilla_image_dir",
    "list_clonezilla_image_dirs",
    "load_image",
    "parse_clonezilla_image",
    "restore_clonezilla_image",
    "restore_image",
    "verify_restored_image",
]
