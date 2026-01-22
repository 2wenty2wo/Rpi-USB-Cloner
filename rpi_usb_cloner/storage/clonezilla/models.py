"""Data models for Clonezilla image operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ClonezillaImage:
    name: str
    path: Path
    parts: list[str]
    partition_table: Optional[Path]


@dataclass(frozen=True)
class DiskLayoutOp:
    kind: str
    path: Path
    contents: Optional[str]
    size_bytes: int


@dataclass(frozen=True)
class PartitionRestoreOp:
    partition: str
    image_files: list[Path]
    tool: str
    fstype: Optional[str]
    compressed: bool


@dataclass(frozen=True)
class RestorePlan:
    image_dir: Path
    parts: list[str]
    disk_layout_ops: list[DiskLayoutOp]
    partition_ops: list[PartitionRestoreOp]
