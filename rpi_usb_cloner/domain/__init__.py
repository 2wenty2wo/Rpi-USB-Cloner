"""Domain models for USB cloning operations.

This package contains type-safe domain objects to replace dict[str, Any]
scattered throughout the codebase, focusing on high-value areas first.
"""

from __future__ import annotations

from .models import (
    CloneJob,
    CloneMode,
    DiskImage,
    Drive,
    ImageRepo,
    ImageType,
    JobState,
)


__all__ = [
    "CloneJob",
    "CloneMode",
    "DiskImage",
    "Drive",
    "ImageRepo",
    "ImageType",
    "JobState",
]
