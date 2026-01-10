"""USB drive cloning operations with verification and progress tracking.

This package implements core USB drive cloning functionality supporting multiple
modes with real-time progress display and verification.

Main Functions:
    - clone_device(): Main entry point for cloning with mode selection
    - clone_dd(): Raw block-level copy with progress tracking
    - clone_partclone(): Filesystem-aware partition cloning
    - copy_partition_table(): Copy partition table between devices
    - verify_clone(): SHA256 verification
    - erase_device(): Quick or full disk erasure

Helper Functions:
    - get_partition_display_name(): Get friendly partition name
    - format_filesystem_type(): Format filesystem type for display
    - get_partition_number(): Extract partition number from name
    - resolve_device_node(): Convert device name to node path

Command Execution:
    - run_checked_command(): Run command and check result
    - run_checked_with_streaming_progress(): Run with progress tracking
"""
from .command_runners import (
    configure_progress_logger,
    run_checked_command,
    run_checked_with_progress,
    run_checked_with_streaming_progress,
    run_progress_command,
)
from .erase import erase_device
from .models import (
    format_filesystem_type,
    get_partition_display_name,
    get_partition_number,
    normalize_clone_mode,
    resolve_device_node,
)
from .operations import clone_dd, clone_device, clone_device_smart, clone_partclone, copy_partition_table
from .progress import (
    configure_progress_logger as configure_clone_helpers,
    format_eta,
    format_progress_display,
    format_progress_lines,
)
from .verification import compute_sha256, verify_clone, verify_clone_device

# Import internal functions for test compatibility
from .progress import _log_debug as _progress_log_debug
from .operations import _log_debug as _operations_log_debug

# Unified log_debug function for backwards compatibility
def log_debug(message: str) -> None:
    """Log debug message (for backwards compatibility with tests)."""
    _progress_log_debug(message)

# Expose _log_debug for test access
_log_debug = _progress_log_debug

__all__ = [
    # Main operations
    "clone_device",
    "clone_device_smart",
    "clone_dd",
    "clone_partclone",
    "copy_partition_table",
    "erase_device",
    # Verification
    "verify_clone",
    "verify_clone_device",
    "compute_sha256",
    # Helper functions
    "get_partition_display_name",
    "format_filesystem_type",
    "get_partition_number",
    "normalize_clone_mode",
    "resolve_device_node",
    # Progress formatting
    "format_eta",
    "format_progress_lines",
    "format_progress_display",
    # Command runners
    "run_checked_command",
    "run_checked_with_progress",
    "run_checked_with_streaming_progress",
    "run_progress_command",
    # Configuration
    "configure_clone_helpers",
    "configure_progress_logger",
    # Internal (for tests)
    "log_debug",
    "_log_debug",
]
