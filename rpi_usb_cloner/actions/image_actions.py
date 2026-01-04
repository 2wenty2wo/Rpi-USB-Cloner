import time
from typing import Callable, Optional

from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.storage import clonezilla, devices
from rpi_usb_cloner.ui import display, menus, screens


def _log_debug(log_debug: Optional[Callable[[str], None]], message: str) -> None:
    if log_debug:
        log_debug(message)


def coming_soon() -> None:
    screens.show_coming_soon(title="IMAGES")


def backup_image() -> None:
    screens.render_status_template("BACKUP", "Running...", progress_line="Preparing image...")
    time.sleep(1)
    screens.render_status_template("BACKUP", "Done", progress_line="Image saved.")
    time.sleep(1)


def write_image(*, app_context: AppContext, log_debug: Optional[Callable[[str], None]] = None) -> None:
    if not app_context.active_drive:
        display.display_lines(["NO DRIVE", "SELECTED"])
        time.sleep(1)
        return
    usb_devices = devices.list_usb_disks()
    target = None
    for device in usb_devices:
        if device.get("name") == app_context.active_drive:
            target = device
            break
    if not target:
        display.display_lines(["TARGET", "MISSING"])
        time.sleep(1)
        return
    repo_path = None
    for device in usb_devices:
        if device.get("name") == target.get("name"):
            continue
        repo_path = clonezilla.find_image_repository(device)
        if repo_path:
            break
    if not repo_path:
        display.display_lines(["IMAGE REPO", "NOT FOUND"])
        time.sleep(1)
        return
    image_dirs = clonezilla.list_clonezilla_image_dirs(repo_path)
    if not image_dirs:
        display.display_lines(["NO IMAGES", "FOUND"])
        time.sleep(1)
        return
    selected_index = menus.select_list(
        "RESTORE IMG",
        [path.name for path in image_dirs],
        footer=["BACK", "OK"],
    )
    if selected_index is None:
        return
    selected_dir = image_dirs[selected_index]
    try:
        image = clonezilla.load_image(selected_dir)
    except RuntimeError as error:
        _log_debug(log_debug, f"Restore load failed: {error}")
        display.display_lines(["IMAGE", "INVALID"])
        time.sleep(1)
        return
    screens.render_status_template("WRITE", "Running...", progress_line="Preparing media...")
    try:
        clonezilla.restore_image(
            image,
            target,
            progress_callback=lambda line: screens.render_status_template(
                "WRITE", "Running...", progress_line=line
            ),
        )
    except RuntimeError as error:
        _log_debug(log_debug, f"Restore failed: {error}")
        screens.render_status_template("WRITE", "Failed", progress_line="Check logs.")
        time.sleep(1)
        return
    screens.render_status_template("WRITE", "Done", progress_line="Image written.")
    time.sleep(1)
