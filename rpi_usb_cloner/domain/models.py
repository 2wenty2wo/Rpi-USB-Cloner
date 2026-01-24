"""Minimal domain model for USB cloning operations.

This module introduces type-safe domain objects to replace dict[str, Any]
scattered throughout the codebase, focusing on high-value areas first.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


# ==============================================================================
# Drive Domain
# ==============================================================================


@dataclass(frozen=True)
class Drive:
    """A USB drive detected by the system.

    Replaces the raw dict from lsblk with a type-safe domain object.
    Start by using this in service layer and clone operations.
    """

    name: str  # e.g., "sda"
    size_bytes: int  # Total size in bytes
    vendor: str | None = None  # e.g., "Kingston"
    model: str | None = None  # e.g., "DataTraveler"
    is_removable: bool = True  # Safety check

    @property
    def device_path(self) -> str:
        """Device node path (e.g., /dev/sda)."""
        return f"/dev/{self.name}"

    @property
    def size_gb(self) -> float:
        """Size in gigabytes."""
        return self.size_bytes / (1024**3)

    def format_label(self) -> str:
        """Format a human-readable label for display.

        Returns: e.g., "sda 8.0GB" or "sda Kingston DataTraveler (8.0GB)"
        """
        size_str = f"{self.size_gb:.1f}GB"

        # Build vendor/model string if available
        parts = []
        if self.vendor:
            parts.append(self.vendor.strip())
        if self.model:
            parts.append(self.model.strip())

        if parts:
            vendor_model = " ".join(parts)
            return f"{self.name} {vendor_model} ({size_str})"
        return f"{self.name} {size_str}"

    @classmethod
    def from_lsblk_dict(cls, device: dict[str, Any]) -> Drive:
        """Convert lsblk dict to Drive domain object.

        Args:
            device: Device dict from lsblk with keys: name, size, vendor, model, rm, tran

        Returns:
            Drive domain object

        Raises:
            KeyError: If required keys (name, size) are missing
            ValueError: If size cannot be converted to int
        """
        name = device["name"]
        size_bytes = int(device.get("size", 0))

        # Vendor and model are optional, clean whitespace
        vendor = device.get("vendor")
        if vendor:
            vendor = vendor.strip()

        model = device.get("model")
        if model:
            model = model.strip()

        # Determine if removable (rm=1 or tran=usb)
        is_removable = device.get("rm") == 1 or device.get("tran") == "usb"

        return cls(
            name=name,
            size_bytes=size_bytes,
            vendor=vendor,
            model=model,
            is_removable=is_removable,
        )


# ==============================================================================
# Image Repository Domain
# ==============================================================================


@dataclass(frozen=True)
class ImageRepo:
    """A USB drive or partition containing disk images.

    Identified by .rpi-usb-cloner-image-repo flag file.
    """

    path: Path  # Mount point or root directory
    drive_name: str | None  # Associated drive (e.g., "sdb")

    def contains_flag_file(
        self, flag_filename: str = ".rpi-usb-cloner-image-repo"
    ) -> bool:
        """Check if repo flag file exists.

        Args:
            flag_filename: Name of the flag file to check

        Returns:
            True if flag file exists in repo path
        """
        return (self.path / flag_filename).exists()


@dataclass(frozen=True)
class DiskImage:
    """A Clonezilla-compatible disk image or ISO file.

    Replaces Path objects with a domain type that carries metadata.
    """

    name: str  # Image name (directory or file name)
    path: Path  # Full path to image directory or ISO
    image_type: ImageType  # CLONEZILLA_DIR or ISO
    size_bytes: int | None = None  # Total size if calculable

    @property
    def is_iso(self) -> bool:
        """Check if this is an ISO image."""
        return self.image_type == ImageType.ISO

    @property
    def is_imageusb(self) -> bool:
        """Check if this is an ImageUSB .BIN file."""
        return self.image_type == ImageType.IMAGEUSB_BIN


class ImageType(Enum):
    """Type of disk image."""

    CLONEZILLA_DIR = "clonezilla"  # Directory with Clonezilla image files
    ISO = "iso"  # ISO file
    IMAGEUSB_BIN = "imageusb"  # ImageUSB .BIN file


# ==============================================================================
# Clone Job Domain
# ==============================================================================


@dataclass(frozen=True)
class CloneJob:
    """A cloning operation request.

    Encapsulates source, destination, and mode for clone operations.
    Makes validation and error handling more explicit.
    """

    source: Drive
    destination: Drive
    mode: CloneMode
    job_id: str  # Unique identifier for logging

    def validate(self) -> None:
        """Validate clone job constraints.

        This method centralizes critical safety checks that were previously
        scattered across the codebase or missing entirely.

        Raises:
            ValueError: If validation fails with a descriptive error message
        """
        # CRITICAL: Check source != destination (fixes known bug!)
        if self.source.name == self.destination.name:
            raise ValueError(
                f"Source and destination cannot be the same device: {self.source.name}"
            )

        # Safety check: destination must be removable
        if not self.destination.is_removable:
            raise ValueError(
                f"Destination {self.destination.name} is not removable - refusing to clone"
            )

        # Size check: destination must be >= source
        if self.source.size_bytes > self.destination.size_bytes:
            raise ValueError(
                f"Destination ({self.destination.size_gb:.1f}GB) is smaller than "
                f"source ({self.source.size_gb:.1f}GB)"
            )


class CloneMode(Enum):
    """Clone operation mode."""

    SMART = "smart"  # partclone (filesystem-aware)
    EXACT = "exact"  # dd (block-level)
    VERIFY = "verify"  # clone + SHA256 verification


# ==============================================================================
# Job State (optional, for future async operations)
# ==============================================================================


class JobState(Enum):
    """State of a long-running operation.

    Not used initially, but reserved for future async job tracking.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
