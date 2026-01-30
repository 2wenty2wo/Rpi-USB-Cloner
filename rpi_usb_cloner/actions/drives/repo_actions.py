"""Repository drive actions.

Handles creating and managing image repository drives.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from loguru import logger

from rpi_usb_cloner.services import drives
from rpi_usb_cloner.storage.devices import get_children, list_usb_disks
from rpi_usb_cloner.ui import display, menus, screens
from rpi_usb_cloner.ui.icons import ALERT_ICON, FOLDER_ICON

from ._utils import handle_screenshot




def create_repo_drive(
    *,
    state: app_state.AppState,
    get_selected_usb_name: Callable[[], str | None],
) -> None:
    """Create an image repository on a USB drive by adding flag file.

    This creates the .rpi-usb-cloner-image-repo flag file on the drive,
    which marks it as an image repository for storing backups.
    """
    from rpi_usb_cloner.storage import image_repo
    from rpi_usb_cloner.storage import mount as mount_module

    # Get available drives (not already repos)
    repo_devices = drives._get_repo_device_names()
    available_devices = [
        device for device in list_usb_disks() if device.get("name") not in repo_devices
    ]

    if not available_devices:
        display.display_lines(["CREATE REPO", "No USB found"])
        time.sleep(1)
        return

    available_devices = sorted(available_devices, key=lambda d: d.get("name", ""))

    # Find the selected device, or use the last one
    selected_name = get_selected_usb_name()
    target = None
    if selected_name:
        for device in available_devices:
            if device.get("name") == selected_name:
                target = device
                break

    if not target:
        target = available_devices[-1]

    target_name = target.get("name")

    # Confirmation
    if not _confirm_create_repo(state, target_name):
        return

    # Get the first mountable partition to create the flag file on
    children = get_children(target)
    partitions = [child for child in children if child.get("type") == "part"]

    if not partitions:
        screens.render_error_screen(
            title="CREATE REPO",
            message="No partitions found",
            title_icon=FOLDER_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1)
        return

    mountpoint = _get_or_mount_partition(partitions, target_name, mount_module)

    if not mountpoint:
        screens.render_error_screen(
            title="CREATE REPO",
            message="Could not mount drive",
            title_icon=FOLDER_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1)
        return

    # Create the flag file
    flag_path = Path(mountpoint) / image_repo.REPO_FLAG_FILENAME
    logger.info("Creating repo flag file", device=target_name, path=str(flag_path))
    display.display_lines(["CREATING REPO..."])

    try:
        flag_path.touch(exist_ok=True)
        logger.info(
            "Successfully created repo flag file",
            device=target_name,
            path=str(flag_path),
        )

        # Invalidate the repo cache so the drive is recognized
        drives.invalidate_repo_cache()

        screens.render_status_template(
            "CREATE REPO",
            "Done",
            progress_line=f"{target_name} is now a Repo",
        )
        time.sleep(1.5)

    except OSError as error:
        logger.error(
            "Failed to create repo flag file",
            device=target_name,
            path=str(flag_path),
            error=str(error),
        )
        screens.render_error_screen(
            title="CREATE REPO",
            message="Write failed",
            title_icon=FOLDER_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1)


def _confirm_create_repo(state: app_state.AppState, target_name: str) -> bool:
    """Show create repo confirmation dialog."""
    title = "CREATE REPO"
    prompt = f"Make {target_name} a Repo Drive?"
    selection = [app_state.CONFIRM_NO]  # Default to NO

    def render():
        screens.render_confirmation_screen(
            title,
            [prompt],
            selected_index=selection[0],
            title_icon=FOLDER_ICON,
        )

    render()
    menus.wait_for_buttons_release(
        [gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B, gpio.PIN_C]
    )

    def on_right():
        if selection[0] == app_state.CONFIRM_NO:
            selection[0] = app_state.CONFIRM_YES
            logger.debug("Create repo selection changed: YES")

    def on_left():
        if selection[0] == app_state.CONFIRM_YES:
            selection[0] = app_state.CONFIRM_NO
            logger.debug("Create repo selection changed: NO")

    confirmed = gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel
            gpio.PIN_B: lambda: selection[0] == app_state.CONFIRM_YES,
            gpio.PIN_C: lambda: handle_screenshot() or None,
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render,
    )

    return confirmed if confirmed is not None else False


def _get_or_mount_partition(
    partitions: list[dict],
    target_name: str,
    mount_module,
) -> str | None:
    """Get mountpoint for a partition, mounting if necessary."""
    mountpoint = None
    partition_name = None

    # Prefer a partition that is already mounted; otherwise try mounting each.
    for partition in partitions:
        mountpoint = partition.get("mountpoint")
        partition_name = partition.get("name")
        if not partition_name:
            continue

        if mountpoint:
            logger.debug(
                "Using mounted partition",
                partition=partition_name,
                mountpoint=mountpoint,
            )
            break

        logger.info(
            "Mounting partition for repo creation", partition=partition_name
        )
        display.display_lines(["MOUNTING..."])

        try:
            partition_node = f"/dev/{partition_name}"
            mount_module.mount_partition(partition_node, name=partition_name)
        except (ValueError, RuntimeError) as error:
            logger.warning(
                "Failed to mount partition", partition=partition_name, error=str(error)
            )
            continue

        # Refresh device info to get new mountpoint
        for device in list_usb_disks():
            if device.get("name") == target_name:
                for child in get_children(device):
                    if child.get("name") == partition_name:
                        mountpoint = child.get("mountpoint")
                        break
                break

        if mountpoint:
            logger.info(
                "Mounted partition successfully",
                partition=partition_name,
                mountpoint=mountpoint,
            )
            break

    return mountpoint
