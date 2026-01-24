"""File utilities for Clonezilla image operations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional


def extract_volume_suffix(path: Path) -> Optional[str]:
    """Extract the two-letter volume suffix from a file path (e.g., 'aa', 'ab')."""
    match = re.search(r"\.([a-z]{2})$", path.name)
    if not match:
        return None
    return match.group(1)


def volume_suffix_index(suffix: Optional[str]) -> int:
    """Convert a two-letter suffix to a numeric index for sorting."""
    if not suffix:
        return -1
    first = ord(suffix[0]) - ord("a")
    second = ord(suffix[1]) - ord("a")
    if first < 0 or first > 25 or second < 0 or second > 25:
        return -1
    return first * 26 + second


def sorted_clonezilla_volumes(paths: Iterable[Path]) -> list[Path]:
    """Sort Clonezilla volume files in the correct order.

    Handles multi-volume files with suffixes like .aa, .ab, .ac, etc.
    """

    def sort_key(path: Path) -> tuple[str, int, str]:
        suffix = extract_volume_suffix(path)
        base = path.name
        if suffix:
            base = base[: -len(suffix) - 1]
        return (base, volume_suffix_index(suffix), path.name)

    return sorted({path for path in paths}, key=sort_key)


def extract_partclone_fstype(part_name: str, file_name: str) -> Optional[str]:
    """Extract filesystem type from partclone image filename.

    Example: sda1.ext4-ptcl-img.gz.aa -> "ext4"
    """
    match = re.search(rf"{re.escape(part_name)}\.(.+?)-ptcl-img", file_name)
    if not match:
        return None
    return match.group(1)


def select_clonezilla_volume_set(
    primary: list[Path], secondary: list[Path]
) -> list[Path]:
    """Select the appropriate volume set when multiple patterns match.

    Returns the set with more volumes, or primary if equal.
    """
    if primary and secondary:
        return primary if len(primary) >= len(secondary) else secondary
    return primary or secondary


def find_image_files(image_dir: Path, part_name: str, suffix: str) -> list[Path]:
    """Find image files for a partition in a Clonezilla image directory.

    Args:
        image_dir: Path to the Clonezilla image directory
        part_name: Partition name (e.g., "sda1")
        suffix: File suffix pattern ("ptcl-img" or "img")

    Returns:
        List of image file paths, sorted by volume
    """
    if suffix == "ptcl-img":
        prefixed_matches = list(image_dir.glob(f"*-{part_name}.*-{suffix}*"))
        direct_matches = list(image_dir.glob(f"{part_name}.*-{suffix}*"))
        matches = select_clonezilla_volume_set(direct_matches, prefixed_matches)
        return sorted_clonezilla_volumes(matches)
    if suffix == "img":
        dd_prefixed = list(image_dir.glob(f"*-{part_name}.*-dd-img*"))
        dd_direct = list(image_dir.glob(f"{part_name}.*-dd-img*"))
        dd_matches = select_clonezilla_volume_set(dd_direct, dd_prefixed)
        if dd_matches:
            return sorted_clonezilla_volumes(dd_matches)
        img_prefixed = list(image_dir.glob(f"*-{part_name}.*.img*"))
        img_direct = list(image_dir.glob(f"{part_name}.*.img*"))
        img_matches = select_clonezilla_volume_set(img_direct, img_prefixed)
        return sorted_clonezilla_volumes(img_matches)
    pattern = f"*-{part_name}.*.{suffix}*"
    return sorted_clonezilla_volumes(image_dir.glob(pattern))


def has_partition_image_files(image_dir: Path, part_name: str) -> bool:
    """Check if partition image files exist in the directory."""
    return any(image_dir.glob(f"*-{part_name}.*-img*"))
