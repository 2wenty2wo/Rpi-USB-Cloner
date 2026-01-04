import time
from typing import Callable, Optional

from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.storage import clonezilla, devices, image_repo
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
    repos = image_repo.find_image_repos(image_repo.REPO_FLAG_FILENAME)
    target_mounts = {
        mountpoint
        for mountpoint in [
            target.get("mountpoint"),
            *[child.get("mountpoint") for child in devices.get_children(target)],
        ]
        if mountpoint
    }
    filtered_repos = [
        repo for repo in repos if not any(str(repo).startswith(mount) for mount in target_mounts)
    ]
    if not filtered_repos:
        display.display_lines(["IMAGE REPO", "NOT FOUND"])
        time.sleep(1)
        return
    if len(filtered_repos) > 1:
        selected_repo = menus.select_list(
            "IMG REPO",
            [repo.name for repo in filtered_repos],
            footer=["BACK", "OK"],
        )
        if selected_repo is None:
            return
        repo_path = filtered_repos[selected_repo]
    else:
        repo_path = filtered_repos[0]
    image_dirs = image_repo.list_clonezilla_images(repo_path)
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
