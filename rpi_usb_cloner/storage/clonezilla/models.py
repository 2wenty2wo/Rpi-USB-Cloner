"""Data models for Clonezilla image operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ClonezillaImage:
    name: str
    path: Path
    parts: list[str]
    partition_table: Path | None


@dataclass(frozen=True)
class DiskLayoutOp:
    kind: str
    path: Path
    contents: str | None
    size_bytes: int


@dataclass(frozen=True)
class PartitionRestoreOp:
    partition: str
    image_files: list[Path]
    tool: str
    fstype: str | None
    compressed: bool


@dataclass(frozen=True)
class RestorePlan:
    image_dir: Path
    parts: list[str]
    disk_layout_ops: list[DiskLayoutOp]
    partition_ops: list[PartitionRestoreOp]
