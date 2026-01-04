import time
from typing import Callable, Iterable, Optional

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.hardware import gpio
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
    usb_devices = devices.list_usb_disks()
    if not usb_devices:
        display.display_lines(["NO USB", "DRIVES"])
        time.sleep(1)
        return
    target = None
    if app_context.active_drive:
        for device in usb_devices:
            if device.get("name") == app_context.active_drive:
                target = device
                break
    if not target:
        selected_index = menus.select_usb_drive(
            "TARGET USB",
            usb_devices,
            footer=["BACK", "OK"],
            selected_name=app_context.active_drive,
        )
        if selected_index is None:
            return
        target = usb_devices[selected_index]
        app_context.active_drive = target.get("name")
    repos = image_repo.find_image_repos(image_repo.REPO_FLAG_FILENAME)
    refreshed_target = None
    for device in devices.list_usb_disks():
        if device.get("name") == app_context.active_drive:
            refreshed_target = device
            break
    if refreshed_target is not None:
        target = refreshed_target
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
        plan = clonezilla.parse_clonezilla_image(selected_dir)
    except RuntimeError as error:
        _log_debug(log_debug, f"Restore load failed: {error}")
        display.display_lines(["IMAGE", "INVALID"])
        time.sleep(1)
        return
    source_size = _estimate_source_size(plan)
    target_size = _get_target_size(target)
    if not _confirm_destructive_action(
        log_debug=log_debug,
        prompt_lines=[
            f"IMG {selected_dir.name}",
            f"SRC {_format_size(source_size)}",
            f"DEV {devices.format_device_label(target)}",
            f"TGT {_format_size(target_size)}",
        ],
    ):
        return
    screens.render_status_template("WRITE", "Running...", progress_line="Preparing media...")
    try:
        clonezilla.restore_clonezilla_image(plan, target.get("name") or "")
    except RuntimeError as error:
        _log_debug(log_debug, f"Restore failed: {error}")
        screens.render_status_template("WRITE", "Failed", progress_line="Check logs.")
        time.sleep(1)
        return
    screens.render_status_template("WRITE", "Done", progress_line="Image written.")
    time.sleep(1)


def _estimate_source_size(plan: clonezilla.RestorePlan) -> Optional[int]:
    return clonezilla._estimate_required_size_bytes(plan.disk_layout_ops)


def _get_target_size(target: dict) -> Optional[int]:
    size = target.get("size")
    if size is None:
        return None
    try:
        return int(size)
    except (TypeError, ValueError):
        return None


def _format_size(size_bytes: Optional[int]) -> str:
    if size_bytes is None:
        return "Unknown"
    return devices.human_size(size_bytes)


def _confirm_destructive_action(
    *,
    log_debug: Optional[Callable[[str], None]],
    prompt_lines: Iterable[str],
) -> bool:
    title = "⚠ DATA LOST"
    prompt = " | ".join(prompt_lines)
    selection = app_state.CONFIRM_NO
    screens.render_confirmation_screen(title, prompt, selected_index=selection)
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B])
    prev_states = {
        "L": gpio.read_button(gpio.PIN_L),
        "R": gpio.read_button(gpio.PIN_R),
        "A": gpio.read_button(gpio.PIN_A),
        "B": gpio.read_button(gpio.PIN_B),
    }
    while True:
        current_r = gpio.read_button(gpio.PIN_R)
        if prev_states["R"] and not current_r:
            if selection == app_state.CONFIRM_NO:
                selection = app_state.CONFIRM_YES
                _log_debug(log_debug, f"Write confirmation changed: {selection}")
        current_l = gpio.read_button(gpio.PIN_L)
        if prev_states["L"] and not current_l:
            if selection == app_state.CONFIRM_YES:
                selection = app_state.CONFIRM_NO
                _log_debug(log_debug, f"Write confirmation changed: {selection}")
        current_a = gpio.read_button(gpio.PIN_A)
        if prev_states["A"] and not current_a:
            return False
        current_b = gpio.read_button(gpio.PIN_B)
        if prev_states["B"] and not current_b:
            return selection == app_state.CONFIRM_YES
        prev_states["R"] = current_r
        prev_states["L"] = current_l
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        screens.render_confirmation_screen(title, prompt, selected_index=selection)
        time.sleep(menus.BUTTON_POLL_DELAY)
