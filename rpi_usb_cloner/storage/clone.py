"""USB drive cloning operations (compatibility layer).

This module provides backwards compatibility by re-exporting functionality
from the refactored clone package.

For new code, prefer importing directly from:
    rpi_usb_cloner.storage.clone.*
"""
# Re-export all public APIs from the clone package
from rpi_usb_cloner.storage.clone import (
    clone_dd,
    clone_device,
    clone_device_smart,
    clone_partclone,
    compute_sha256,
    configure_clone_helpers,
    configure_progress_logger,
    copy_partition_table,
    erase_device,
    format_filesystem_type,
    get_partition_display_name,
    get_partition_number,
    normalize_clone_mode,
    resolve_device_node,
    run_checked_command,
    run_checked_with_progress,
    run_checked_with_streaming_progress,
    run_progress_command,
    verify_clone,
    verify_clone_device,
)

__all__ = [
    "clone_dd",
    "clone_device",
    "clone_device_smart",
    "clone_partclone",
    "compute_sha256",
    "configure_clone_helpers",
    "configure_progress_logger",
    "copy_partition_table",
    "erase_device",
    "format_filesystem_type",
    "get_partition_display_name",
    "get_partition_number",
    "normalize_clone_mode",
    "resolve_device_node",
    "run_checked_command",
    "run_checked_with_progress",
    "run_checked_with_streaming_progress",
    "run_progress_command",
    "verify_clone",
    "verify_clone_device",
]
