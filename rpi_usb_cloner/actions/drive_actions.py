"""Drive actions module.

This module has been refactored into the `drives` subpackage for better modularity.
All public functions are re-exported here for backward compatibility.

New code should import directly from the specific submodules:
    from rpi_usb_cloner.actions.drives.clone_actions import copy_drive
    from rpi_usb_cloner.actions.drives.erase_actions import erase_drive
    # etc.

Or from the package:
    from rpi_usb_cloner.actions.drives import copy_drive, erase_drive
"""

from __future__ import annotations

# Re-export all public functions for backward compatibility
from rpi_usb_cloner.actions.drives import (
    copy_drive,
    create_repo_drive,
    drive_info,
    erase_drive,
    execute_copy_operation,
    format_drive,
    prepare_copy_operation,
    unmount_drive,
)

__all__ = [
    "copy_drive",
    "create_repo_drive",
    "drive_info",
    "erase_drive",
    "execute_copy_operation",
    "format_drive",
    "prepare_copy_operation",
    "unmount_drive",
]
