from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from rpi_usb_cloner.storage.devices import format_device_label, list_usb_disks
from rpi_usb_cloner.storage.mount import get_device_name, get_size, list_media_devices


@dataclass
class DriveSnapshot:
    discovered: List[str]
    active: Optional[str]


def list_media_drive_names() -> List[str]:
    return [get_device_name(device) for device in list_media_devices()]


def list_media_drive_labels() -> List[str]:
    labels = []
    for device in list_media_devices():
        label = f"{get_device_name(device)} {get_size(device) / 1024 ** 3:.2f}GB"
        labels.append(label)
    return labels


def list_usb_disk_names() -> List[str]:
    return [device.get("name") for device in list_usb_disks() if device.get("name")]


def list_usb_disk_labels() -> List[str]:
    return [format_device_label(device) for device in list_usb_disks()]


def refresh_drives(active_drive: Optional[str]) -> DriveSnapshot:
    discovered = list_media_drive_names()
    active = active_drive if active_drive in discovered else None
    return DriveSnapshot(discovered=discovered, active=active)


def select_active_drive(
    discovered: List[str],
    selected_index: int,
) -> Optional[str]:
    if not discovered:
        return None
    if selected_index < 0:
        return discovered[0]
    if selected_index >= len(discovered):
        return discovered[-1]
    return discovered[selected_index]


def get_active_drive_label(active_drive: Optional[str]) -> Optional[str]:
    if not active_drive:
        return None
    for device in list_media_devices():
        if get_device_name(device) == active_drive:
            return f"{get_device_name(device)} {get_size(device) / 1024 ** 3:.2f}GB"
    return active_drive
