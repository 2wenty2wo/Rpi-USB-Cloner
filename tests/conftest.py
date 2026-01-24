"""
Pytest configuration and shared fixtures for rpi-usb-cloner tests.

This module provides common fixtures and utilities used across all test modules.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock

import pytest


# Mock hardware dependencies before other imports
# This allows tests to run on non-Raspberry Pi systems
sys.modules["RPi"] = MagicMock()
sys.modules["RPi.GPIO"] = MagicMock()
sys.modules["luma"] = MagicMock()
sys.modules["luma.core"] = MagicMock()
sys.modules["luma.core.interface"] = MagicMock()
sys.modules["luma.core.interface.serial"] = MagicMock()
sys.modules["luma.core.render"] = MagicMock()
sys.modules["luma.oled"] = MagicMock()
sys.modules["luma.oled.device"] = MagicMock()


# ==============================================================================
# Device Mock Fixtures
# ==============================================================================


@pytest.fixture
def mock_usb_device() -> Dict[str, Any]:
    """
    Fixture providing a mock USB device dictionary.

    Returns:
        Dict representing a typical USB device as returned by lsblk.
    """
    return {
        "name": "sda",
        "path": "/dev/sda",
        "size": "16106127360",
        "type": "disk",
        "mountpoint": None,
        "label": "USB_DRIVE",
        "uuid": "1234-5678",
        "fstype": "vfat",
        "rm": "1",  # Removable
        "ro": "0",  # Not read-only
        "tran": "usb",
        "model": "USB Flash Drive",
        "serial": "123456789ABC",
        "vendor": "Generic",
        "children": [
            {
                "name": "sda1",
                "path": "/dev/sda1",
                "size": "16105078784",
                "type": "part",
                "mountpoint": "/media/usb",
                "label": "USB_DRIVE",
                "uuid": "1234-5678",
                "fstype": "vfat",
            }
        ],
    }


@pytest.fixture
def mock_usb_device_unmounted(mock_usb_device) -> Dict[str, Any]:
    """Fixture providing an unmounted USB device."""
    device = mock_usb_device.copy()
    device["mountpoint"] = None
    if device.get("children"):
        device["children"][0]["mountpoint"] = None
    return device


@pytest.fixture
def mock_system_disk() -> Dict[str, Any]:
    """
    Fixture providing a mock system disk (non-removable).

    Returns:
        Dict representing a system disk that should NOT be cloned/erased.
    """
    return {
        "name": "mmcblk0",
        "path": "/dev/mmcblk0",
        "size": "31914983424",
        "type": "disk",
        "mountpoint": None,
        "label": None,
        "uuid": None,
        "fstype": None,
        "rm": "0",  # Not removable - CRITICAL!
        "ro": "0",
        "tran": None,
        "model": "SD Card",
        "serial": "0x12345678",
        "children": [
            {
                "name": "mmcblk0p1",
                "path": "/dev/mmcblk0p1",
                "size": "268435456",
                "type": "part",
                "mountpoint": "/boot",
                "label": "boot",
                "uuid": "ABCD-1234",
                "fstype": "vfat",
            },
            {
                "name": "mmcblk0p2",
                "path": "/dev/mmcblk0p2",
                "size": "31646547968",
                "type": "part",
                "mountpoint": "/",
                "label": "rootfs",
                "uuid": "deadbeef-1234-5678-90ab-cdef12345678",
                "fstype": "ext4",
            },
        ],
    }


@pytest.fixture
def mock_lsblk_output(mock_usb_device, mock_system_disk) -> str:
    """
    Fixture providing mock lsblk JSON output.

    Returns:
        JSON string representing lsblk output with multiple devices.
    """
    output = {
        "blockdevices": [
            mock_system_disk,
            mock_usb_device,
        ]
    }
    return json.dumps(output)


@pytest.fixture
def mock_lsblk_empty() -> str:
    """Fixture providing empty lsblk output (no devices)."""
    return json.dumps({"blockdevices": []})


# ==============================================================================
# Subprocess Mock Fixtures
# ==============================================================================


@pytest.fixture
def mock_subprocess_success(mocker) -> Mock:
    """
    Fixture providing a mock subprocess.run that always succeeds.

    Returns:
        Mock object for subprocess.run.
    """
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    return mocker.patch("subprocess.run", return_value=mock_result)


@pytest.fixture
def mock_subprocess_failure(mocker) -> Mock:
    """
    Fixture providing a mock subprocess.run that always fails.

    Returns:
        Mock object for subprocess.run that raises CalledProcessError.
    """

    def raise_error(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="Mock error")

    return mocker.patch("subprocess.run", side_effect=raise_error)


@pytest.fixture
def mock_command_runner(mocker) -> Mock:
    """
    Fixture providing a mock for the custom command runner.

    Returns:
        Mock that can be configured to simulate different command outcomes.
    """
    return mocker.MagicMock()


# ==============================================================================
# File System Mock Fixtures
# ==============================================================================


@pytest.fixture
def temp_settings_file(tmp_path) -> Path:
    """
    Fixture providing a temporary settings file path.

    Args:
        tmp_path: pytest's built-in temporary directory fixture.

    Returns:
        Path to a temporary settings file.
    """
    settings_dir = tmp_path / ".config" / "rpi-usb-cloner"
    settings_dir.mkdir(parents=True, exist_ok=True)
    return settings_dir / "settings.json"


@pytest.fixture
def sample_settings_data() -> Dict[str, Any]:
    """
    Fixture providing sample settings data.

    Returns:
        Dict with typical settings values.
    """
    return {
        "verify_hash": True,
        "verify_hash_timeout": 300,
        "clone_mode": "smart",
        "screensaver_timeout": 300,
        "debug_mode": False,
        "wifi_enabled": True,
    }


@pytest.fixture
def temp_mount_point(tmp_path) -> Path:
    """
    Fixture providing a temporary mount point.

    Args:
        tmp_path: pytest's built-in temporary directory fixture.

    Returns:
        Path to a temporary mount directory.
    """
    mount_dir = tmp_path / "mnt" / "test_mount"
    mount_dir.mkdir(parents=True, exist_ok=True)
    return mount_dir


# ==============================================================================
# Clone Operation Mock Fixtures
# ==============================================================================


@pytest.fixture
def mock_clone_progress() -> List[str]:
    """
    Fixture providing mock progress output from dd/partclone.

    Returns:
        List of progress strings as would be emitted by clone operations.
    """
    return [
        "100+0 records in",
        "100+0 records out",
        "52428800 bytes (52 MB, 50 MiB) copied, 1.5 s, 35 MB/s",
    ]


@pytest.fixture
def mock_partclone_output() -> List[str]:
    """
    Fixture providing mock partclone progress output.

    Returns:
        List of partclone progress messages.
    """
    return [
        "Partclone v0.3.23",
        "Starting to clone device",
        "File system:  VFAT",
        "Device size: 15.0 GB",
        "Space in use: 8.5 GB",
        "Elapsed: 00:00:30, Rate: 283.33 MB/min, Remaining: 00:01:30",
        "current block: 1000, total block: 4000, Complete: 25.00%",
        "current block: 2000, total block: 4000, Complete: 50.00%",
        "current block: 3000, total block: 4000, Complete: 75.00%",
        "current block: 4000, total block: 4000, Complete: 100.00%",
        "Syncing... OK!",
        "Cloned successfully.",
    ]


# ==============================================================================
# Display and UI Mock Fixtures
# ==============================================================================


@pytest.fixture
def mock_oled_device(mocker) -> Mock:
    """
    Fixture providing a mock OLED device.

    Returns:
        Mock for luma.oled device.
    """
    mock_device = mocker.MagicMock()
    mock_device.width = 128
    mock_device.height = 64
    return mock_device


@pytest.fixture
def mock_gpio(mocker) -> Mock:
    """
    Fixture providing mock RPi.GPIO module.

    Returns:
        Mock for RPi.GPIO.
    """
    return mocker.patch("RPi.GPIO")


# ==============================================================================
# Context and State Mock Fixtures
# ==============================================================================


@pytest.fixture
def mock_app_context() -> Mock:
    """
    Fixture providing a mock application context.

    Returns:
        Mock AppContext object.
    """
    context = MagicMock()
    context.device_manager = MagicMock()
    context.display_manager = MagicMock()
    context.settings = MagicMock()
    context.state = MagicMock()
    return context


@pytest.fixture
def mock_error_handler() -> Mock:
    """
    Fixture providing a mock error handler.

    Returns:
        Mock callable for error handling.
    """
    return MagicMock()


@pytest.fixture
def mock_log_debug() -> Mock:
    """
    Fixture providing a mock debug logger.

    Returns:
        Mock callable for debug logging.
    """
    return MagicMock()


# ==============================================================================
# Clonezilla Mock Fixtures
# ==============================================================================


@pytest.fixture
def mock_clonezilla_image_dir(tmp_path) -> Path:
    """
    Fixture providing a mock Clonezilla image directory structure.

    Args:
        tmp_path: pytest's built-in temporary directory fixture.

    Returns:
        Path to mock Clonezilla image directory.
    """
    image_dir = tmp_path / "clonezilla_images" / "test_image"
    image_dir.mkdir(parents=True)

    # Create mock metadata files
    (image_dir / "disk").write_text("sda")
    (image_dir / "parts").write_text("sda1 sda2")
    (image_dir / "dev-fs.list").write_text("sda1 vfat\nsda2 ext4")
    (image_dir / "blkdev.list").write_text("sda")

    # Create mock partition table
    sfdisk_content = """label: dos
label-id: 0x12345678
device: /dev/sda
unit: sectors

/dev/sda1 : start=2048, size=1048576, type=c, bootable
/dev/sda2 : start=1050624, size=29360128, type=83
"""
    (image_dir / "sda-pt.sf").write_text(sfdisk_content)

    # Create mock partition images
    (image_dir / "sda1.vfat-ptcl-img.gz.aa").write_bytes(b"mock compressed data")
    (image_dir / "sda2.ext4-ptcl-img.gz.aa").write_bytes(b"mock compressed data")

    return image_dir


# ==============================================================================
# Utility Fixtures
# ==============================================================================


@pytest.fixture
def capture_subprocess_calls(mocker) -> List[List]:
    """
    Fixture that captures all subprocess.run calls for inspection.

    Returns:
        List that will contain all subprocess command arguments.
    """
    calls = []

    def track_call(cmd, **kwargs):
        calls.append(cmd)
        result = Mock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    mocker.patch("subprocess.run", side_effect=track_call)
    return calls


@pytest.fixture(autouse=True)
def reset_global_state():
    """
    Auto-use fixture that resets any global state before each test.

    This helps ensure test isolation when modules use global variables.
    """
    # This will run before each test
    yield
    # Cleanup after test (if needed)


@pytest.fixture
def mock_subprocess_run(mocker):
    """
    Fixture providing a mock for subprocess.run.

    Returns:
        Mock object for subprocess.run
    """
    return mocker.patch("subprocess.run")


@pytest.fixture(autouse=True)
def mock_display_context(request, mocker):
    """
    Auto-use fixture that mocks display context initialization.

    This prevents tests from failing when display_lines is called
    without proper display context setup.

    Skipped for pure domain model tests that don't need UI/hardware mocking.
    """
    # Skip for domain model tests (no UI/hardware dependencies)
    if "test_domain_models" in request.node.nodeid:
        return None

    mock_context = Mock()
    mock_context.device = Mock()
    mocker.patch(
        "rpi_usb_cloner.ui.display.get_display_context", return_value=mock_context
    )
    mocker.patch("rpi_usb_cloner.ui.display.display_lines")
    # Also patch display_lines where it's imported in command_runners
    mocker.patch("rpi_usb_cloner.storage.clone.command_runners.display_lines")
    return mock_context
