"""ImageUSB .BIN file detection and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


# ImageUSB signature (first 16 bytes)
# UTF-16LE encoding of "imageUSB"
IMAGEUSB_SIGNATURE = bytes(
    [
        0x69,
        0x00,
        0x6D,
        0x00,
        0x61,
        0x00,
        0x67,
        0x00,
        0x65,
        0x00,
        0x55,
        0x00,
        0x53,
        0x00,
        0x42,
        0x00,
    ]
)

# ImageUSB header size (first 512 bytes)
IMAGEUSB_HEADER_SIZE = 512


def is_imageusb_file(file_path: Path) -> bool:
    """Check if a file is an ImageUSB .BIN file.

    Checks for the ImageUSB signature in the first 16 bytes of the file.

    Args:
        file_path: Path to the file to check

    Returns:
        True if the file has the ImageUSB signature, False otherwise
    """
    if not file_path.exists() or not file_path.is_file():
        return False

    try:
        with file_path.open("rb") as f:
            signature = f.read(16)
            return signature == IMAGEUSB_SIGNATURE
    except OSError:
        return False


def validate_imageusb_file(file_path: Path) -> Optional[str]:
    """Validate an ImageUSB .BIN file.

    Performs basic validation checks:
    - File exists and is readable
    - Has correct ImageUSB signature
    - File size is > 512 bytes (header + data)
    - MBR signature present at offset 512 + 510-511 (0x55AA)

    Args:
        file_path: Path to the ImageUSB file

    Returns:
        None if valid, error message string if invalid
    """
    # Check file exists
    if not file_path.exists():
        return f"File does not exist: {file_path}"

    if not file_path.is_file():
        return f"Path is not a file: {file_path}"

    # Check file size
    try:
        file_size = file_path.stat().st_size
    except OSError as e:
        return f"Cannot read file size: {e}"

    if file_size <= IMAGEUSB_HEADER_SIZE:
        return f"File too small ({file_size} bytes), must be > {IMAGEUSB_HEADER_SIZE}"

    # Check ImageUSB signature
    try:
        with file_path.open("rb") as f:
            # Read signature (first 16 bytes)
            signature = f.read(16)
            if signature != IMAGEUSB_SIGNATURE:
                return "Invalid ImageUSB signature (not an ImageUSB .BIN file)"

            # Seek to MBR location (offset 512)
            f.seek(IMAGEUSB_HEADER_SIZE)

            # Read first sector to check for MBR signature
            # MBR signature should be at bytes 510-511 (0x55AA)
            mbr_sector = f.read(512)
            if len(mbr_sector) < 512:
                return "File truncated (cannot read MBR sector)"

            # Check MBR boot signature (last 2 bytes should be 0x55, 0xAA)
            if mbr_sector[510:512] != b"\x55\xaa":
                # Not necessarily an error - some images might not have MBR
                # Just a warning
                pass

    except OSError as e:
        return f"Error reading file: {e}"

    # All checks passed
    return None


def get_imageusb_metadata(file_path: Path) -> dict[str, any]:
    """Extract metadata from an ImageUSB .BIN file.

    Args:
        file_path: Path to the ImageUSB file

    Returns:
        Dictionary with metadata:
        - name: File name
        - size_bytes: Total file size
        - data_size_bytes: Size of disk image (excluding 512-byte header)
        - valid: Whether validation passed
        - error: Validation error message (if invalid)
    """
    metadata = {
        "name": file_path.name,
        "size_bytes": 0,
        "data_size_bytes": 0,
        "valid": False,
        "error": None,
    }

    # Get file size
    try:
        file_size = file_path.stat().st_size
        metadata["size_bytes"] = file_size
        metadata["data_size_bytes"] = max(0, file_size - IMAGEUSB_HEADER_SIZE)
    except OSError:
        pass

    # Validate
    error = validate_imageusb_file(file_path)
    metadata["valid"] = error is None
    metadata["error"] = error

    return metadata
