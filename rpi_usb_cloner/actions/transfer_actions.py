"""Transfer-related actions for copying images between repositories.

This module provides high-level actions for the image transfer feature,
combining UI flows with the transfer service logic.
"""

from __future__ import annotations

import threading
import time
from typing import cast

from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.domain import DiskImage
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.logging import get_logger
from rpi_usb_cloner.services import transfer
from rpi_usb_cloner.storage import devices, image_repo
from rpi_usb_cloner.ui import display, menus, screens
from rpi_usb_cloner.ui.icons import ALERT_ICON, FOLDER_ICON


log = get_logger(source=__name__)


def copy_images_to_usb(*, app_context: AppContext) -> None:
    """USB-to-USB image transfer flow.

    Flow:
    1. Find source repo (from available repos)
    2. Find destination repo drives (excluding source)
    3. If no destination, show error
    4. Multi-select images from source
    5. Show progress during copy
    6. Show success/failure summary
    """
    # Step 1: Find and select source repository
    source_repos = image_repo.find_image_repos()

    if not source_repos:
        screens.render_error_screen(
            "COPY IMAGES",
            message="No image repo found",
            title_icon=FOLDER_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1.5)
        return

    # If multiple repos, let user select source
    if len(source_repos) > 1:
        source_index = menus.select_list(
            "SOURCE REPO",
            [repo.path.name for repo in source_repos],
            title_icon=FOLDER_ICON,
            transition_direction="forward",
        )
        if source_index is None:
            return
        source_repo = source_repos[source_index]
    else:
        source_repo = source_repos[0]

    # Step 2: Find destination repos (excluding source)
    dest_repos = transfer.find_destination_repos(exclude_drive=source_repo.drive_name)

    if not dest_repos:
        screens.render_error_screen(
            "COPY IMAGES",
            message="No destination repo\nPlug in another USB",
            title_icon=FOLDER_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(2)
        return

    # If multiple destinations, let user select
    if len(dest_repos) > 1:
        dest_index = menus.select_list(
            "DESTINATION",
            [f"{repo.path.name} ({repo.drive_name})" for repo in dest_repos],
            title_icon=FOLDER_ICON,
            transition_direction="forward",
        )
        if dest_index is None:
            return
        dest_repo = dest_repos[dest_index]
    else:
        dest_repo = dest_repos[0]

    # Step 3: Get images from source repo
    all_images = image_repo.list_clonezilla_images(source_repo.path)

    if not all_images:
        screens.render_error_screen(
            "COPY IMAGES",
            message="No images found\nin source repo",
            title_icon=FOLDER_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1.5)
        return

    # Step 4: Multi-select images
    selected_flags = _select_images_checklist([img.name for img in all_images])

    if selected_flags is None:
        # User cancelled
        return

    # Build list of selected images
    selected_images = [img for i, img in enumerate(all_images) if selected_flags[i]]

    if not selected_images:
        screens.render_error_screen(
            "COPY IMAGES",
            message="No images selected",
            title_icon=FOLDER_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1.5)
        return

    # Step 5: Check available space
    total_size = transfer.estimate_transfer_size(selected_images)
    dest_usage = image_repo.get_repo_usage(dest_repo)
    available_space = cast(int, dest_usage["free_bytes"])

    if total_size > available_space:
        size_gb = total_size / (1024**3)
        free_gb = available_space / (1024**3)
        screens.render_error_screen(
            "COPY IMAGES",
            message=f"Insufficient space\nNeed {size_gb:.1f}GB, have {free_gb:.1f}GB",
            title_icon=FOLDER_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(2.5)
        return

    # Step 6: Show confirmation
    if not _confirm_copy(selected_images, dest_repo.path.name):
        return

    # Step 7: Perform copy with progress
    _execute_copy(selected_images, dest_repo)


def _select_images_checklist(image_names: list[str]) -> list[bool] | None:
    """Show a checklist for image selection.

    Args:
        image_names: List of image name strings

    Returns:
        List of booleans (True if selected), or None if cancelled
    """
    selected = [False] * len(image_names)  # None selected by default
    cursor_index = 0

    def render_screen():
        lines = []
        for idx, name in enumerate(image_names):
            checkbox = "☑" if selected[idx] else "☐"
            marker = ">" if idx == cursor_index else " "
            # Truncate long names
            display_name = name[:18] if len(name) > 18 else name
            lines.append(f"{marker}{checkbox} {display_name}")

        # Show up to 4 images at a time
        visible_start = max(0, cursor_index - 1)
        visible_lines = lines[visible_start : visible_start + 4]

        display.display_lines(["SELECT IMAGES", "L/R:Toggle B:Copy", *visible_lines])

    render_screen()
    menus.wait_for_buttons_release(
        [gpio.PIN_U, gpio.PIN_D, gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B]
    )

    while True:
        render_screen()

        # Poll for button events
        if gpio.is_pressed(gpio.PIN_U):
            cursor_index = max(0, cursor_index - 1)
            time.sleep(0.15)
        elif gpio.is_pressed(gpio.PIN_D):
            cursor_index = min(len(image_names) - 1, cursor_index + 1)
            time.sleep(0.15)
        elif gpio.is_pressed(gpio.PIN_L) or gpio.is_pressed(gpio.PIN_R):
            # Toggle current selection
            selected[cursor_index] = not selected[cursor_index]
            time.sleep(0.15)
        elif gpio.is_pressed(gpio.PIN_B):
            # Confirm
            return selected
        elif gpio.is_pressed(gpio.PIN_A):
            # Cancel
            return None

        time.sleep(0.05)


def _confirm_copy(images: list[DiskImage], dest_name: str) -> bool:
    """Show confirmation screen for copy operation.

    Args:
        images: List of images to copy
        dest_name: Destination repo name

    Returns:
        True if user confirmed, False if cancelled
    """
    image_count = len(images)
    total_size = transfer.estimate_transfer_size(images)
    size_label = devices.human_size(total_size) if total_size > 0 else "Unknown"

    prompt_lines = [
        f"Copy {image_count} image(s)",
        f"to {dest_name}?",
        f"Size: {size_label}",
    ]

    selection = [1]  # Default to NO

    def render():
        screens.render_confirmation_screen(
            "COPY IMAGES",
            prompt_lines,
            selected_index=selection[0],
            title_icon=FOLDER_ICON,
        )

    render()
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B])

    def on_right():
        if selection[0] == 0:
            selection[0] = 1

    def on_left():
        if selection[0] == 1:
            selection[0] = 0

    result = gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel
            gpio.PIN_B: lambda: selection[0] == 0,  # Confirm YES
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render,
    )

    return result if result is not None else False


def _execute_copy(images: list[DiskImage], dest_repo) -> None:
    """Execute the copy operation with progress display.

    Args:
        images: List of images to copy
        dest_repo: Destination ImageRepo
    """
    done = threading.Event()
    progress_lock = threading.Lock()
    current_image = [""]
    progress_ratio = [0.0]
    success_count = [0]
    failure_count = [0]

    def progress_callback(image_name: str, ratio: float):
        """Called by transfer service to report progress."""
        with progress_lock:
            current_image[0] = image_name
            progress_ratio[0] = ratio

    def worker():
        """Background thread for copy operation."""
        try:
            success, failure = transfer.copy_images_to_repo(
                images, dest_repo, progress_callback=progress_callback
            )
            success_count[0] = success
            failure_count[0] = failure
        except Exception as e:
            log.error(f"Copy operation failed: {e}")
            failure_count[0] = len(images)
        finally:
            done.set()

    # Start background thread
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    # Show progress
    while not done.is_set():
        with progress_lock:
            img_name = current_image[0] or "Preparing..."
            ratio = progress_ratio[0]

        # Truncate long image names
        if len(img_name) > 20:
            img_name = img_name[:17] + "..."

        screens.render_progress_screen(
            "COPYING",
            [img_name],
            progress_ratio=ratio,
            animate=False,
            title_icon=FOLDER_ICON,
        )
        time.sleep(0.1)

    thread.join()

    # Show final result
    success = success_count[0]
    failure = failure_count[0]

    if failure == 0:
        # All succeeded
        screens.render_status_template(
            "COPY IMAGES",
            "SUCCESS",
            extra_lines=[
                f"Copied {success} image(s)",
                "to destination repo.",
                "Press A/B to continue.",
            ],
            title_icon=FOLDER_ICON,
        )
    elif success == 0:
        # All failed
        screens.render_status_template(
            "COPY IMAGES",
            "FAILED",
            extra_lines=[
                f"Failed to copy {failure} image(s).",
                "Check logs for details.",
                "Press A/B to continue.",
            ],
            title_icon=FOLDER_ICON,
        )
    else:
        # Partial success
        screens.render_status_template(
            "COPY IMAGES",
            "PARTIAL",
            extra_lines=[
                f"Copied: {success}",
                f"Failed: {failure}",
                "Check logs for details.",
                "Press A/B to continue.",
            ],
            title_icon=FOLDER_ICON,
        )

    screens.wait_for_ack()
