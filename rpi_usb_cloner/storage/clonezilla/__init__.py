"""Clonezilla disk image restoration with partition table scaling and verification.

This package provides comprehensive support for restoring Clonezilla disk images,
handling complex partition table operations, filesystem restoration, and automatic
partition scaling.

Main Functions:
    - find_image_repository(): Find Clonezilla image repository on a mounted device
    - list_clonezilla_image_dirs(): List all Clonezilla image directories
    - load_image(): Load Clonezilla image metadata
    - parse_clonezilla_image(): Parse image and create restore plan
    - restore_image(): Restore image (legacy API)
    - restore_clonezilla_image(): Restore image with full partition mode support
    - verify_restored_image(): Verify restoration with SHA256

Data Models:
    - ClonezillaImage: Image metadata
    - RestorePlan: Complete restoration plan
    - PartitionRestoreOp: Single partition restore operation
    - DiskLayoutOp: Disk layout operation
"""
from .image_discovery import (
    find_image_repository,
    find_partition_table,
    get_mountpoint,
    is_clonezilla_image_dir,
    list_clonezilla_image_dirs,
    load_image,
    parse_clonezilla_image,
)
from .models import ClonezillaImage, DiskLayoutOp, PartitionRestoreOp, RestorePlan
from .restore import restore_clonezilla_image, restore_image
from .verification import verify_restored_image

__all__ = [
    # Main functions
    "find_image_repository",
    "list_clonezilla_image_dirs",
    "load_image",
    "parse_clonezilla_image",
    "restore_image",
    "restore_clonezilla_image",
    "verify_restored_image",
    # Helper functions
    "find_partition_table",
    "get_mountpoint",
    "is_clonezilla_image_dir",
    # Data models
    "ClonezillaImage",
    "DiskLayoutOp",
    "PartitionRestoreOp",
    "RestorePlan",
]
