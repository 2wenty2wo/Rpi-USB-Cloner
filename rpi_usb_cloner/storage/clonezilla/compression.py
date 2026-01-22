"""Compression detection utilities for Clonezilla images."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def is_gzip_compressed(image_files: list[Path]) -> bool:
    """Check if image files are gzip compressed."""
    for image_file in image_files:
        if ".gz" in image_file.suffixes:
            return True
        if image_file.name.endswith(".gz"):
            return True
    return False


def is_zstd_compressed(image_files: list[Path]) -> bool:
    """Check if image files are zstd compressed."""
    for image_file in image_files:
        if ".zst" in image_file.suffixes:
            return True
        if image_file.name.endswith(".zst"):
            return True
    return False


def get_compression_type(image_files: list[Path]) -> Optional[str]:
    """Detect compression type of image files.

    Returns:
        "zstd" if zstd compressed
        "gzip" if gzip compressed
        None if uncompressed
    """
    if is_zstd_compressed(image_files):
        return "zstd"
    if is_gzip_compressed(image_files):
        return "gzip"
    return None


def is_compressed(image_files: list[Path]) -> bool:
    """Check if image files are compressed."""
    return get_compression_type(image_files) is not None
