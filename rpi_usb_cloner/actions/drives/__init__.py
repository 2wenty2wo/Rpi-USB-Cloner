"""Drive actions package.

This package contains modular actions for drive operations:
- clone_actions: Copy/clone drive operations
- erase_actions: Drive erasure operations
- format_actions: Drive formatting operations
- info_actions: Drive information display
- unmount_actions: Drive unmounting and power-off
- repo_actions: Image repository management
"""

from .clone_actions import (
    copy_drive,
    execute_copy_operation,
    prepare_copy_operation,
)
from .erase_actions import erase_drive
from .format_actions import format_drive
from .info_actions import drive_info
from .repo_actions import create_repo_drive
from .unmount_actions import unmount_drive


__all__ = [
    # Clone operations
    "copy_drive",
    "execute_copy_operation",
    "prepare_copy_operation",
    # Erase operations
    "erase_drive",
    # Format operations
    "format_drive",
    # Info operations
    "drive_info",
    # Repo operations
    "create_repo_drive",
    # Unmount operations
    "unmount_drive",
]
