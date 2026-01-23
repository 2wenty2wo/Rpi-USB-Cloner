"""ImageUSB .BIN file support.

This module provides support for restoring ImageUSB .BIN files to USB drives.
ImageUSB is a tool from OSForensics that creates forensically sound USB images.

Format structure:
- First 512 bytes: ImageUSB header containing checksums/hashes
- Remaining bytes: Raw disk image (MBR + partitions)

The first 16 bytes contain the UTF-16LE signature "imageUSB".
"""
from .detection import is_imageusb_file, validate_imageusb_file
from .restore import restore_imageusb_file

__all__ = [
    "is_imageusb_file",
    "validate_imageusb_file",
    "restore_imageusb_file",
]
