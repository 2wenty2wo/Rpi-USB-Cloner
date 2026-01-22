"""Tests for domain models.

This module provides comprehensive test coverage for the domain model layer,
ensuring type safety and validation logic works correctly.

Note: These tests are for pure domain models with no hardware/UI dependencies.
The conftest.py autouse fixtures are automatically skipped for these tests.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from rpi_usb_cloner.domain import (
    CloneJob,
    CloneMode,
    DiskImage,
    Drive,
    ImageRepo,
    ImageType,
    JobState,
)


# ==============================================================================
# Drive Tests
# ==============================================================================


class TestDrive:
    """Test Drive domain model."""

    def test_create_drive_minimal(self):
        """Test creating a drive with minimal required fields."""
        drive = Drive(name="sda", size_bytes=8_000_000_000)

        assert drive.name == "sda"
        assert drive.size_bytes == 8_000_000_000
        assert drive.vendor is None
        assert drive.model is None
        assert drive.is_removable is True

    def test_create_drive_full(self):
        """Test creating a drive with all fields."""
        drive = Drive(
            name="sdb",
            size_bytes=16_000_000_000,
            vendor="Kingston",
            model="DataTraveler",
            is_removable=True,
        )

        assert drive.name == "sdb"
        assert drive.size_bytes == 16_000_000_000
        assert drive.vendor == "Kingston"
        assert drive.model == "DataTraveler"
        assert drive.is_removable is True

    def test_device_path_property(self):
        """Test device_path property returns correct /dev path."""
        drive = Drive(name="sda", size_bytes=8_000_000_000)
        assert drive.device_path == "/dev/sda"

        drive2 = Drive(name="sdb", size_bytes=16_000_000_000)
        assert drive2.device_path == "/dev/sdb"

    def test_size_gb_property(self):
        """Test size_gb property converts bytes to gigabytes."""
        drive = Drive(name="sda", size_bytes=8_000_000_000)
        assert abs(drive.size_gb - 7.45) < 0.01  # ~7.45 GB

        drive2 = Drive(name="sdb", size_bytes=16_000_000_000)
        assert abs(drive2.size_gb - 14.9) < 0.1  # ~14.9 GB

    def test_format_label_minimal(self):
        """Test format_label with minimal fields."""
        drive = Drive(name="sda", size_bytes=8_000_000_000)
        label = drive.format_label()
        assert label == "sda 7.5GB"

    def test_format_label_with_vendor_and_model(self):
        """Test format_label with vendor and model."""
        drive = Drive(
            name="sdb",
            size_bytes=16_000_000_000,
            vendor="Kingston",
            model="DataTraveler",
        )
        label = drive.format_label()
        assert label == "sdb Kingston DataTraveler (14.9GB)"

    def test_format_label_with_vendor_only(self):
        """Test format_label with vendor but no model."""
        drive = Drive(
            name="sdc",
            size_bytes=32_000_000_000,
            vendor="SanDisk",
        )
        label = drive.format_label()
        assert label == "sdc SanDisk (29.8GB)"

    def test_format_label_with_model_only(self):
        """Test format_label with model but no vendor."""
        drive = Drive(
            name="sdd",
            size_bytes=64_000_000_000,
            model="Ultra USB 3.0",
        )
        label = drive.format_label()
        assert label == "sdd Ultra USB 3.0 (59.6GB)"

    def test_from_lsblk_dict_minimal(self):
        """Test from_lsblk_dict with minimal lsblk output."""
        lsblk_dict = {
            "name": "sda",
            "size": 8000000000,
        }

        drive = Drive.from_lsblk_dict(lsblk_dict)

        assert drive.name == "sda"
        assert drive.size_bytes == 8000000000
        assert drive.vendor is None
        assert drive.model is None
        assert drive.is_removable is False  # No rm or tran specified

    def test_from_lsblk_dict_full(self):
        """Test from_lsblk_dict with complete lsblk output."""
        lsblk_dict = {
            "name": "sdb",
            "size": 16000000000,
            "vendor": "  Kingston  ",  # Test whitespace stripping
            "model": "  DataTraveler  ",
            "rm": 1,
            "tran": "usb",
        }

        drive = Drive.from_lsblk_dict(lsblk_dict)

        assert drive.name == "sdb"
        assert drive.size_bytes == 16000000000
        assert drive.vendor == "Kingston"  # Stripped
        assert drive.model == "DataTraveler"  # Stripped
        assert drive.is_removable is True  # rm=1

    def test_from_lsblk_dict_usb_transport(self):
        """Test from_lsblk_dict identifies USB by tran field."""
        lsblk_dict = {
            "name": "sdc",
            "size": 32000000000,
            "tran": "usb",
            "rm": 0,  # Even if rm=0, tran=usb means removable
        }

        drive = Drive.from_lsblk_dict(lsblk_dict)
        assert drive.is_removable is True

    def test_from_lsblk_dict_removable_flag(self):
        """Test from_lsblk_dict identifies removable by rm field."""
        lsblk_dict = {
            "name": "sdd",
            "size": 64000000000,
            "rm": 1,
        }

        drive = Drive.from_lsblk_dict(lsblk_dict)
        assert drive.is_removable is True

    def test_from_lsblk_dict_missing_name_raises(self):
        """Test from_lsblk_dict raises KeyError if name is missing."""
        lsblk_dict = {
            "size": 8000000000,
        }

        with pytest.raises(KeyError):
            Drive.from_lsblk_dict(lsblk_dict)

    def test_from_lsblk_dict_invalid_size_raises(self):
        """Test from_lsblk_dict raises ValueError if size is invalid."""
        lsblk_dict = {
            "name": "sda",
            "size": "not_a_number",
        }

        with pytest.raises(ValueError):
            Drive.from_lsblk_dict(lsblk_dict)

    def test_drive_is_frozen(self):
        """Test that Drive is immutable (frozen dataclass)."""
        drive = Drive(name="sda", size_bytes=8_000_000_000)

        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            drive.name = "sdb"


# ==============================================================================
# ImageRepo Tests
# ==============================================================================


class TestImageRepo:
    """Test ImageRepo domain model."""

    def test_create_image_repo(self):
        """Test creating an ImageRepo."""
        repo = ImageRepo(path=Path("/mnt/usb"), drive_name="sdb")

        assert repo.path == Path("/mnt/usb")
        assert repo.drive_name == "sdb"

    def test_create_image_repo_no_drive(self):
        """Test creating an ImageRepo without associated drive."""
        repo = ImageRepo(path=Path("/var/images"), drive_name=None)

        assert repo.path == Path("/var/images")
        assert repo.drive_name is None

    def test_contains_flag_file(self, tmp_path):
        """Test contains_flag_file checks for flag file existence."""
        # Create flag file
        flag_file = tmp_path / ".rpi-usb-cloner-image-repo"
        flag_file.touch()

        repo = ImageRepo(path=tmp_path, drive_name="sdb")
        assert repo.contains_flag_file() is True

    def test_contains_flag_file_missing(self, tmp_path):
        """Test contains_flag_file returns False if flag file missing."""
        repo = ImageRepo(path=tmp_path, drive_name="sdb")
        assert repo.contains_flag_file() is False

    def test_contains_flag_file_custom_name(self, tmp_path):
        """Test contains_flag_file with custom flag filename."""
        custom_flag = tmp_path / ".custom-flag"
        custom_flag.touch()

        repo = ImageRepo(path=tmp_path, drive_name="sdb")
        assert repo.contains_flag_file(".custom-flag") is True
        assert repo.contains_flag_file(".rpi-usb-cloner-image-repo") is False

    def test_image_repo_is_frozen(self):
        """Test that ImageRepo is immutable."""
        repo = ImageRepo(path=Path("/mnt/usb"), drive_name="sdb")

        with pytest.raises(Exception):
            repo.drive_name = "sdc"


# ==============================================================================
# DiskImage Tests
# ==============================================================================


class TestDiskImage:
    """Test DiskImage domain model."""

    def test_create_clonezilla_image(self):
        """Test creating a Clonezilla directory image."""
        image = DiskImage(
            name="backup-2024-01-20",
            path=Path("/mnt/images/backup-2024-01-20"),
            image_type=ImageType.CLONEZILLA_DIR,
            size_bytes=4_000_000_000,
        )

        assert image.name == "backup-2024-01-20"
        assert image.path == Path("/mnt/images/backup-2024-01-20")
        assert image.image_type == ImageType.CLONEZILLA_DIR
        assert image.size_bytes == 4_000_000_000
        assert image.is_iso is False

    def test_create_iso_image(self):
        """Test creating an ISO image."""
        image = DiskImage(
            name="ubuntu-20.04.iso",
            path=Path("/mnt/images/ubuntu-20.04.iso"),
            image_type=ImageType.ISO,
            size_bytes=2_800_000_000,
        )

        assert image.name == "ubuntu-20.04.iso"
        assert image.image_type == ImageType.ISO
        assert image.is_iso is True

    def test_create_image_no_size(self):
        """Test creating an image without size."""
        image = DiskImage(
            name="backup",
            path=Path("/mnt/images/backup"),
            image_type=ImageType.CLONEZILLA_DIR,
        )

        assert image.size_bytes is None

    def test_disk_image_is_frozen(self):
        """Test that DiskImage is immutable."""
        image = DiskImage(
            name="test",
            path=Path("/test"),
            image_type=ImageType.ISO,
        )

        with pytest.raises(Exception):
            image.name = "modified"


# ==============================================================================
# CloneJob Tests
# ==============================================================================


class TestCloneJob:
    """Test CloneJob domain model."""

    def test_create_clone_job(self):
        """Test creating a valid clone job."""
        source = Drive(name="sda", size_bytes=8_000_000_000)
        destination = Drive(name="sdb", size_bytes=16_000_000_000)

        job = CloneJob(
            source=source,
            destination=destination,
            mode=CloneMode.SMART,
            job_id="test-job-123",
        )

        assert job.source == source
        assert job.destination == destination
        assert job.mode == CloneMode.SMART
        assert job.job_id == "test-job-123"

    def test_validate_success(self):
        """Test validate passes with valid configuration."""
        source = Drive(name="sda", size_bytes=8_000_000_000)
        destination = Drive(name="sdb", size_bytes=16_000_000_000)

        job = CloneJob(
            source=source,
            destination=destination,
            mode=CloneMode.SMART,
            job_id="test-job",
        )

        # Should not raise
        job.validate()

    def test_validate_same_device_raises(self):
        """Test validate raises if source == destination (CRITICAL BUG FIX)."""
        source = Drive(name="sda", size_bytes=8_000_000_000)
        destination = Drive(name="sda", size_bytes=8_000_000_000)  # Same device!

        job = CloneJob(
            source=source,
            destination=destination,
            mode=CloneMode.SMART,
            job_id="test-job",
        )

        with pytest.raises(ValueError, match="Source and destination cannot be the same"):
            job.validate()

    def test_validate_destination_not_removable_raises(self):
        """Test validate raises if destination is not removable."""
        source = Drive(name="sda", size_bytes=8_000_000_000, is_removable=True)
        destination = Drive(
            name="mmcblk0", size_bytes=16_000_000_000, is_removable=False
        )

        job = CloneJob(
            source=source,
            destination=destination,
            mode=CloneMode.SMART,
            job_id="test-job",
        )

        with pytest.raises(ValueError, match="is not removable"):
            job.validate()

    def test_validate_destination_too_small_raises(self):
        """Test validate raises if destination is smaller than source."""
        source = Drive(name="sda", size_bytes=16_000_000_000)
        destination = Drive(name="sdb", size_bytes=8_000_000_000)  # Too small!

        job = CloneJob(
            source=source,
            destination=destination,
            mode=CloneMode.SMART,
            job_id="test-job",
        )

        with pytest.raises(ValueError, match="smaller than source"):
            job.validate()

    def test_validate_equal_size_allowed(self):
        """Test validate allows destination equal to source size."""
        source = Drive(name="sda", size_bytes=8_000_000_000)
        destination = Drive(name="sdb", size_bytes=8_000_000_000)  # Equal size

        job = CloneJob(
            source=source,
            destination=destination,
            mode=CloneMode.SMART,
            job_id="test-job",
        )

        # Should not raise
        job.validate()

    def test_clone_job_is_frozen(self):
        """Test that CloneJob is immutable."""
        source = Drive(name="sda", size_bytes=8_000_000_000)
        destination = Drive(name="sdb", size_bytes=16_000_000_000)

        job = CloneJob(
            source=source,
            destination=destination,
            mode=CloneMode.SMART,
            job_id="test-job",
        )

        with pytest.raises(Exception):
            job.mode = CloneMode.EXACT


# ==============================================================================
# CloneMode Tests
# ==============================================================================


class TestCloneMode:
    """Test CloneMode enum."""

    def test_clone_mode_values(self):
        """Test CloneMode enum values."""
        assert CloneMode.SMART.value == "smart"
        assert CloneMode.EXACT.value == "exact"
        assert CloneMode.VERIFY.value == "verify"

    def test_clone_mode_from_string(self):
        """Test creating CloneMode from string value."""
        assert CloneMode("smart") == CloneMode.SMART
        assert CloneMode("exact") == CloneMode.EXACT
        assert CloneMode("verify") == CloneMode.VERIFY


# ==============================================================================
# ImageType Tests
# ==============================================================================


class TestImageType:
    """Test ImageType enum."""

    def test_image_type_values(self):
        """Test ImageType enum values."""
        assert ImageType.CLONEZILLA_DIR.value == "clonezilla"
        assert ImageType.ISO.value == "iso"


# ==============================================================================
# JobState Tests
# ==============================================================================


class TestJobState:
    """Test JobState enum."""

    def test_job_state_values(self):
        """Test JobState enum values."""
        assert JobState.PENDING.value == "pending"
        assert JobState.RUNNING.value == "running"
        assert JobState.COMPLETED.value == "completed"
        assert JobState.FAILED.value == "failed"
        assert JobState.CANCELLED.value == "cancelled"

    def test_job_state_from_string(self):
        """Test creating JobState from string value."""
        assert JobState("pending") == JobState.PENDING
        assert JobState("running") == JobState.RUNNING
        assert JobState("completed") == JobState.COMPLETED
        assert JobState("failed") == JobState.FAILED
        assert JobState("cancelled") == JobState.CANCELLED
