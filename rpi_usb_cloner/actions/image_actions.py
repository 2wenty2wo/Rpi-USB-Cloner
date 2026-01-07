import re
import threading
import time
from typing import Callable, Iterable, Optional

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.config import settings
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.storage import clone, clonezilla, devices, image_repo
from rpi_usb_cloner.ui import display, menus, screens

WRITE_TITLE_ICON = chr(58597)


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
    repos = image_repo.find_image_repos(image_repo.REPO_FLAG_FILENAME)
    if not repos:
        display.display_lines(["IMAGE REPO", "NOT FOUND"])
        time.sleep(1)
        return
    if len(repos) > 1:
        selected_repo = menus.select_list(
            "IMG REPO",
            [repo.name for repo in repos],
        )
        if selected_repo is None:
            return
        repo_path = repos[selected_repo]
    else:
        repo_path = repos[0]
    image_dirs = image_repo.list_clonezilla_images(repo_path)
    if not image_dirs:
        display.display_lines(["NO IMAGES", "FOUND"])
        time.sleep(1)
        return
    selected_index = menus.select_list(
        "CHOOSE IMAGE",
        [path.name for path in image_dirs],
        screen_id="images",
        enable_horizontal_scroll=True,
        scroll_start_delay=1.5,
    )
    if selected_index is None:
        return
    selected_dir = image_dirs[selected_index]
    partition_selection = _prompt_restore_partition_mode()
    if partition_selection is None:
        return
    partition_mode, partition_label = partition_selection
    usb_devices = devices.list_usb_disks()
    if not usb_devices:
        display.display_lines(["NO USB", "DRIVES"])
        time.sleep(1)
        return
    repo_devices = set()
    for device in usb_devices:
        mountpoints = _collect_mountpoints(device)
        if any(str(repo).startswith(mount) for mount in mountpoints for repo in repos):
            repo_devices.add(device.get("name"))
    target_candidates = [device for device in usb_devices if device.get("name") not in repo_devices]
    if not target_candidates:
        display.display_lines(["TARGET IS", "REPO DRIVE"])
        time.sleep(1)
        return
    selected_index = menus.select_usb_drive(
        "TARGET USB",
        target_candidates,
        title_icon=chr(57516),
        selected_name=app_context.active_drive,
    )
    if selected_index is None:
        return
    target = target_candidates[selected_index]
    app_context.active_drive = target.get("name")
    refreshed_target = None
    for device in devices.list_usb_disks():
        if device.get("name") == app_context.active_drive:
            refreshed_target = device
            break
    if refreshed_target is not None:
        target = refreshed_target
    target_mounts = _collect_mountpoints(target)
    if any(str(repo_path).startswith(mount) for mount in target_mounts):
        display.display_lines(["TARGET IS", "REPO DRIVE"])
        time.sleep(1)
        return
    try:
        plan = clonezilla.parse_clonezilla_image(selected_dir)
    except RuntimeError as error:
        _log_debug(log_debug, f"Restore load failed: {error}")
        display.display_lines(["IMAGE", "INVALID"])
        time.sleep(1)
        return
    if not _confirm_destructive_action(log_debug=log_debug):
        return
    if partition_mode == "k2":
        _show_manual_partition_instructions(target)
        if not _wait_for_manual_partitions(plan, target, log_debug=log_debug):
            return
    screens.render_status_template("RESTORE PT", f"Set: {partition_label}")
    time.sleep(1.5)
    done = threading.Event()
    result_holder: dict[str, None] = {}
    error_holder: dict[str, Exception] = {}
    progress_lock = threading.Lock()
    progress_lines = ["Preparing media..."]
    progress_ratio: Optional[float] = 0.0
    progress_written_bytes: Optional[str] = None
    progress_written_percent: Optional[str] = None
    progress_ratio_snapshot: Optional[float] = 0.0
    start_time = time.monotonic()

    def update_progress(lines: list[str], ratio: Optional[float]) -> None:
        nonlocal progress_lines, progress_ratio, progress_written_bytes, progress_written_percent, progress_ratio_snapshot
        clamped = None
        if ratio is not None:
            clamped = max(0.0, min(1.0, float(ratio)))
        with progress_lock:
            progress_lines = lines
            if clamped is not None:
                progress_ratio = clamped
                progress_ratio_snapshot = clamped
            wrote_line = next((line for line in lines if line.startswith("Wrote ")), None)
            if wrote_line:
                match = re.match(r"^Wrote\s+(\S+)(?:\s+(\S+%))?", wrote_line)
                if match:
                    progress_written_bytes = match.group(1)
                    progress_written_percent = match.group(2)

    def current_progress() -> tuple[list[str], Optional[float]]:
        with progress_lock:
            return list(progress_lines), progress_ratio

    def worker() -> None:
        try:
            clonezilla.restore_clonezilla_image(
                plan,
                target.get("name") or "",
                partition_mode=partition_mode,
                progress_callback=update_progress,
            )
            result_holder["result"] = None
        except Exception as exc:
            error_holder["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    while not done.is_set():
        lines, ratio = current_progress()
        screens.render_progress_screen(
            "WRITE",
            lines,
            progress_ratio=ratio,
            animate=False,
            title_icon=WRITE_TITLE_ICON,
        )
        time.sleep(0.1)
    thread.join()
    lines, ratio = current_progress()
    screens.render_progress_screen(
        "WRITE",
        lines,
        progress_ratio=ratio,
        animate=False,
        title_icon=WRITE_TITLE_ICON,
    )
    if "error" in error_holder:
        error = error_holder["error"]
        _log_debug(log_debug, f"Restore failed: {error}")
        screens.wait_for_paginated_input(
            "WRITE",
            ["FAILED", *_format_restore_error_lines(error)],
            title_icon=WRITE_TITLE_ICON,
        )
        return
    elapsed_seconds = time.monotonic() - start_time
    summary_lines = _build_restore_summary_lines(
        image_name=selected_dir.name,
        target=target,
        partition_label=partition_label,
        elapsed_seconds=elapsed_seconds,
        written_bytes=progress_written_bytes,
        written_percent=progress_written_percent,
        ratio=progress_ratio_snapshot,
    )
    screens.render_status_template(
        "WRITE",
        "SUCCESS",
        extra_lines=summary_lines,
    )
    screens.wait_for_ack()


def _prompt_restore_partition_mode() -> Optional[tuple[str, str]]:
    options = [
        ("k0", "USE SOURCE (-k0)"),
        ("k", "SKIP TABLE (-k)"),
        ("k1", "RESIZE TABLE (-k1)"),
    ]
    current_mode = str(settings.get_setting("restore_partition_mode", "k0")).lstrip("-")
    if current_mode not in {value for value, _ in options}:
        options = [("__stored__", "KEEP STORED MODE"), *options]
    selected_index = 0
    for index, (value, _) in enumerate(options):
        if value == current_mode:
            selected_index = index
            break
    selection = menus.render_menu_list(
        "PARTITIONS",
        [label for _, label in options],
        selected_index=selected_index,
        title_icon=chr(57451),
    )
    if selection is None:
        return None
    selected_value, selected_label = options[selection]
    if selected_value == "__stored__":
        selected_value = current_mode
    else:
        settings.set_setting("restore_partition_mode", selected_value)
    return selected_value.lstrip("-"), selected_label


def _confirm_destructive_action(*, log_debug: Optional[Callable[[str], None]]) -> bool:
    return _confirm_prompt(
        log_debug=log_debug,
        title="WARNING!",
        title_icon=chr(57746),
        prompt_lines=["Data will be overwritten!", "All data will lost!"],
        default=app_state.CONFIRM_NO,
    )


def _show_manual_partition_instructions(target: dict) -> None:
    target_label = target.get("name") or devices.format_device_label(target)
    screens.wait_for_paginated_input(
        "MANUAL PT",
        [
            "Manual partitioning",
            "is required.",
            f"Target {target_label}",
            "Use fdisk/parted",
            "to create partitions.",
            "Press A/B to continue.",
        ],
    )


def _confirm_prompt(
    *,
    log_debug: Optional[Callable[[str], None]],
    title: str,
    prompt_lines: Iterable[str],
    default: int,
    title_icon: Optional[str] = None,
) -> bool:
    prompt_lines_list = list(prompt_lines)
    selection = default
    screens.render_confirmation_screen(
        title,
        prompt_lines_list,
        selected_index=selection,
        title_icon=title_icon,
    )
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
                _log_debug(log_debug, f"Confirmation changed: {selection}")
        current_l = gpio.read_button(gpio.PIN_L)
        if prev_states["L"] and not current_l:
            if selection == app_state.CONFIRM_YES:
                selection = app_state.CONFIRM_NO
                _log_debug(log_debug, f"Confirmation changed: {selection}")
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
        screens.render_confirmation_screen(
            title,
            prompt_lines_list,
            selected_index=selection,
            title_icon=title_icon,
        )
        time.sleep(menus.BUTTON_POLL_DELAY)


def _collect_mountpoints(device: dict) -> set[str]:
    mountpoints: set[str] = set()
    stack = [device]
    while stack:
        current = stack.pop()
        mountpoint = current.get("mountpoint")
        if mountpoint:
            mountpoints.add(mountpoint)
        stack.extend(devices.get_children(current))
    return mountpoints


def _wait_for_manual_partitions(
    plan: clonezilla.RestorePlan,
    target: dict,
    *,
    log_debug: Optional[Callable[[str], None]] = None,
) -> bool:
    target_name = target.get("name") or ""
    deadline = time.monotonic() + 10
    last_missing: list[str] = []
    while time.monotonic() < deadline:
        refreshed = devices.get_device_by_name(target_name)
        if not refreshed:
            last_missing = ["target device missing"]
        else:
            last_missing = _find_missing_partitions(plan.parts, refreshed)
            if not last_missing:
                return True
        time.sleep(1)
    _log_debug(log_debug, f"Manual partition check failed: {last_missing}")
    if last_missing and last_missing != ["target device missing"]:
        lines = ["Missing partitions:", ", ".join(last_missing)]
    else:
        lines = ["Target device missing."]
    screens.wait_for_paginated_input(
        "MANUAL PT",
        [*lines, "Create partitions", "and retry."],
    )
    return False


def _find_missing_partitions(required_parts: Iterable[str], target: dict) -> list[str]:
    available_numbers = {
        clone.get_partition_number(child.get("name"))
        for child in devices.get_children(target)
        if child.get("type") == "part"
    }
    missing: list[str] = []
    for part in required_parts:
        number = clone.get_partition_number(part)
        if number is None:
            continue
        if number not in available_numbers:
            missing.append(part)
    return missing


def _format_restore_error_lines(error: Exception) -> list[str]:
    message = str(error).strip()
    if not message:
        return ["Restore failed"]
    lower = message.lower()
    if "partition table apply failed" in lower:
        step_line = "Partition table failed"
    elif "partition restore failed" in lower:
        step_line = "Partition restore failed"
    else:
        step_line = "Restore failed"
    reason = _extract_stderr_message(message) or _short_restore_reason(message)
    if reason and reason != step_line:
        lines = [step_line, reason]
    else:
        lines = [step_line]
    if message not in lines:
        lines.append(message)
    return lines


def _short_restore_reason(message: str) -> str:
    lower = message.lower()
    if "partclone tool not found" in lower or ("partclone." in lower and "not found" in lower):
        fstype_match = re.search(r"filesystem ['\"]?([^'\"]+)['\"]?", message, re.IGNORECASE)
        if fstype_match:
            return f"Missing partclone.{fstype_match.group(1).lower()}"
        return "Missing partclone tool"
    for tool in ("sfdisk", "parted", "sgdisk", "dd", "gzip", "pigz"):
        if f"{tool} not found" in lower:
            return f"Missing {tool} tool"
    if ":" in message:
        prefix, suffix = message.split(":", 1)
        suffix = suffix.strip()
        if suffix:
            return suffix
    return message


def _extract_stderr_message(message: str) -> Optional[str]:
    match = re.search(r"stderr:\s*(.*?)(?:\s*(?:stdout:|$))", message, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    stderr = " ".join(match.group(1).strip().split())
    return stderr or None


def _format_elapsed_duration(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _build_restore_summary_lines(
    *,
    image_name: str,
    target: dict,
    partition_label: str,
    elapsed_seconds: float,
    written_bytes: Optional[str],
    written_percent: Optional[str],
    ratio: Optional[float],
) -> list[str]:
    percent_display = written_percent
    if not percent_display and ratio is not None:
        percent_display = f"{ratio * 100:.1f}%"
    if written_bytes and percent_display:
        written_line = f"Wrote {written_bytes} {percent_display}"
    elif written_bytes:
        written_line = f"Wrote {written_bytes}"
    elif percent_display:
        written_line = f"Wrote {percent_display}"
    else:
        written_line = "Wrote: --"
    target_label = devices.format_device_label(target)
    return [
        f"Image {image_name}",
        f"Target {target_label}",
        f"Mode {partition_label}",
        f"Elapsed {_format_elapsed_duration(elapsed_seconds)}",
        written_line,
        "Press A/B to continue.",
    ]
