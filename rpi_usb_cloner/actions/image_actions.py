import os
import re
import threading
import time
from typing import Callable, Iterable, Optional
from uuid import uuid4

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.config import settings
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.logging import get_logger
from rpi_usb_cloner.storage import clone, clonezilla, devices, image_repo, imageusb, iso
from rpi_usb_cloner.storage.clonezilla.backup import check_tool_available
from rpi_usb_cloner.ui import display, menus, screens
from rpi_usb_cloner.ui.icons import (
    ALERT_ICON,
    INFO_ICON,
    KEYBOARD_ICON,
    SETTINGS_ICON,
    USB_ICON,
    WRITE_ICON,
)


def _log_debug(log_debug: Optional[Callable[[str], None]], message: str) -> None:
    if log_debug:
        log_debug(message)


def coming_soon() -> None:
    screens.show_coming_soon(title="IMAGES")


def backup_image(
    *, app_context: AppContext, log_debug: Optional[Callable[[str], None]] = None
) -> None:
    """Create a Clonezilla-compatible backup of a USB drive."""
    from rpi_usb_cloner.ui import keyboard

    backup_title_icon = WRITE_ICON

    # Step 1: Select backup mode (full/partial)
    backup_modes = [
        ("full", "FULL DISK"),
        ("partial", "SELECT PARTS"),
    ]
    mode_labels = [label for _, label in backup_modes]

    selected_mode_index = menus.render_menu_list(
        "BACKUP MODE",
        mode_labels,
        selected_index=0,
        title_icon=SETTINGS_ICON,
    )

    if selected_mode_index is None:
        return

    backup_mode, _ = backup_modes[selected_mode_index]
    _log_debug(log_debug, f"Backup mode selected: {backup_mode}")

    # Step 2: Select source drive
    usb_devices = devices.list_usb_disks()
    if not usb_devices:
        display.display_lines(["NO USB", "DRIVES"])
        time.sleep(1)
        return

    # Find repos to filter them out as source candidates
    repos = image_repo.find_image_repos(image_repo.REPO_FLAG_FILENAME)
    repo_devices = set()
    for device in usb_devices:
        mountpoints = _collect_mountpoints(device)
        if any(
            str(repo.path).startswith(mount) for mount in mountpoints for repo in repos
        ):
            repo_devices.add(device.get("name"))

    source_candidates = [
        device for device in usb_devices if device.get("name") not in repo_devices
    ]
    if not source_candidates:
        display.display_lines(["NO SOURCE", "AVAILABLE"])
        time.sleep(1)
        return

    selected_source_index = menus.select_usb_drive(
        "SOURCE USB",
        source_candidates,
        title_icon=USB_ICON,
        selected_name=app_context.active_drive,
    )

    if selected_source_index is None:
        return

    source = source_candidates[selected_source_index]
    source_name = source.get("name")
    if not source_name:
        display.display_lines(["SOURCE", "MISSING"])
        time.sleep(1)
        return
    app_context.active_drive = source_name
    _log_debug(log_debug, f"Source device selected: {source_name}")

    # Refresh source device info
    refreshed_source = devices.get_device_by_name(source_name)
    if refreshed_source:
        source = refreshed_source

    # Step 3: Select partitions (if partial mode)
    selected_partition_names: Optional[list[str]] = None

    if backup_mode == "partial":
        partitions = clonezilla.get_partition_info(source)
        if not partitions:
            display.display_lines(["NO PARTITIONS", "FOUND"])
            time.sleep(1)
            return

        # Build partition labels
        partition_labels = []
        for part in partitions:
            fstype_str = part.fstype or "unknown"
            size_str = devices.human_size(part.size_bytes)
            partition_labels.append(f"{part.name} {fstype_str} {size_str}")

        # Show partition selection checklist
        selected_partitions = _select_partitions_checklist(partition_labels)

        if selected_partitions is None:
            return

        if not selected_partitions:
            display.display_lines(["NO PARTITIONS", "SELECTED"])
            time.sleep(1)
            return

        selected_partition_names = [
            partitions[i].name
            for i, selected in enumerate(selected_partitions)
            if selected
        ]
        _log_debug(log_debug, f"Selected partitions: {selected_partition_names}")

    # Step 4: Select image repository
    if not repos:
        display.display_lines(["IMAGE REPO", "NOT FOUND"])
        time.sleep(1)
        return

    if len(repos) > 1:
        selected_repo = menus.select_list(
            "IMG REPO",
            [repo.path.name for repo in repos],
        )
        if selected_repo is None:
            return
        repo_path = repos[selected_repo].path
    else:
        repo_path = repos[0].path

    _log_debug(log_debug, f"Repository selected: {repo_path}")

    # Verify source is not the repo drive
    source_mounts = _collect_mountpoints(source)
    if any(str(repo_path).startswith(mount) for mount in source_mounts):
        display.display_lines(["CANNOT BACKUP", "REPO DRIVE"])
        time.sleep(1)
        return

    # Step 5: Enter image name (manual entry only)
    image_name = keyboard.prompt_text(
        title="IMAGE NAME",
        initial="",
        masked=False,
        title_icon=KEYBOARD_ICON,
    )

    if image_name is None or not image_name.strip():
        return

    image_name = image_name.strip()
    _log_debug(log_debug, f"Image name entered: {image_name}")

    # Validate image name (alphanumeric, dash, underscore only)
    if not re.match(r"^[a-zA-Z0-9_-]+$", image_name):
        display.display_lines(["INVALID NAME", "Use A-Z 0-9 - _"])
        time.sleep(1)
        return

    # Check if image already exists
    image_dir = repo_path / image_name
    if image_dir.exists():
        display.display_lines(["IMAGE EXISTS", image_name])
        time.sleep(1)
        return

    # Step 6: Select compression
    compression_options = []

    # Check which compression tools are available
    if check_tool_available("pigz") or check_tool_available("gzip"):
        compression_options.append(("gzip", "GZIP"))

    if check_tool_available("pzstd") or check_tool_available("zstd"):
        compression_options.append(("zstd", "ZSTD"))

    compression_options.append(("none", "NONE"))

    # Get last used compression from settings
    from rpi_usb_cloner.config import settings as config_settings

    last_compression = str(config_settings.get_setting("backup_compression", "gzip"))

    compression_labels = [label for _, label in compression_options]
    default_compression_index = 0
    for idx, (comp_type, _) in enumerate(compression_options):
        if comp_type == last_compression:
            default_compression_index = idx
            break

    selected_compression_index = menus.render_menu_list(
        "COMPRESSION",
        compression_labels,
        selected_index=default_compression_index,
        title_icon=SETTINGS_ICON,
    )

    if selected_compression_index is None:
        return

    compression_type, compression_label = compression_options[
        selected_compression_index
    ]
    config_settings.set_setting("backup_compression", compression_type)
    _log_debug(log_debug, f"Compression selected: {compression_type}")

    # Step 7: Estimate size and show confirmation
    try:
        estimated_size = clonezilla.estimate_backup_size(
            source_name, selected_partition_names
        )
    except Exception as e:
        _log_debug(log_debug, f"Failed to estimate size: {e}")
        estimated_size = 0

    # Check available space
    try:
        stat = os.statvfs(str(repo_path))
        available_space = stat.f_bavail * stat.f_frsize
    except Exception as e:
        _log_debug(log_debug, f"Failed to check available space: {e}")
        available_space = 0

    # Build confirmation summary
    source_label = devices.format_device_label(source)
    partition_info = "All partitions"
    if selected_partition_names:
        partition_info = f"{len(selected_partition_names)} partition(s)"

    summary_lines = [
        f"Source: {source_label}",
        f"Parts: {partition_info}",
        f"Repo: {repo_path.name}",
        f"Image: {image_name}",
        f"Compress: {compression_label}",
    ]

    if estimated_size > 0:
        summary_lines.append(f"Est: ~{devices.human_size(estimated_size)}")

    if (
        available_space > 0
        and estimated_size > 0
        and estimated_size > available_space
    ):
        display.display_lines(
            [
                "NOT ENOUGH",
                "SPACE",
                f"Need: {devices.human_size(estimated_size)}",
                f"Avail: {devices.human_size(available_space)}",
            ]
        )
        time.sleep(2)
        return

    summary_lines.append("Drive will unmount")

    # Show confirmation
    if not _confirm_prompt(
        log_debug=log_debug,
        title="BACKUP?",
        title_icon=INFO_ICON,
        prompt_lines=summary_lines,
        default=app_state.CONFIRM_NO,
    ):
        return

    # Step 8: Execute backup with progress
    job_id = f"backup-{uuid4().hex}"
    op_log = get_logger(job_id=job_id, tags=["backup"], source="backup")
    op_log.info(
        "Starting backup: %s -> %s (%s)",
        source_name,
        image_dir,
        compression_type,
    )
    done = threading.Event()
    error_holder: dict[str, Exception] = {}
    progress_lock = threading.Lock()
    progress_lines = ["Preparing backup..."]
    progress_ratio: Optional[float] = 0.0
    start_time = time.monotonic()
    result_holder: dict[str, clonezilla.BackupResult] = {}

    def update_progress(lines: list[str], ratio: Optional[float]) -> None:
        nonlocal progress_lines, progress_ratio
        with progress_lock:
            progress_lines = lines[:2]  # Limit to 2 lines
            if ratio is not None:
                progress_ratio = max(0.0, min(1.0, float(ratio)))

    def current_progress() -> tuple[list[str], Optional[float]]:
        with progress_lock:
            return list(progress_lines), progress_ratio

    def worker() -> None:
        try:
            result = clonezilla.create_clonezilla_backup(
                source_device=source_name,
                output_dir=image_dir,
                partitions=selected_partition_names,
                compression=compression_type,
                split_size_mb=4096,  # 4GB default
                progress_callback=update_progress,
            )
            result_holder["result"] = result
        except Exception as exc:
            error_holder["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while not done.is_set():
        lines, ratio = current_progress()
        screens.render_progress_screen(
            "BACKUP",
            lines,
            progress_ratio=ratio,
            animate=False,
            title_icon=backup_title_icon,
        )
        time.sleep(0.1)

    thread.join()

    # Show final progress state
    lines, ratio = current_progress()
    screens.render_progress_screen(
        "BACKUP",
        lines,
        progress_ratio=ratio,
        animate=False,
        title_icon=backup_title_icon,
    )

    # Check for errors
    if "error" in error_holder:
        error = error_holder["error"]
        _log_debug(log_debug, f"Backup failed: {error}")
        error_message = str(error)
        screens.wait_for_paginated_input(
            "BACKUP",
            ["FAILED", error_message],
            title_icon=backup_title_icon,
        )
        return

    # Step 9: Show success summary
    if "result" not in result_holder:
        _log_debug(log_debug, "Backup completed but no result")
        screens.render_status_template("BACKUP", "COMPLETED")
        time.sleep(1)
        return

    result = result_holder["result"]
    elapsed_seconds = time.monotonic() - start_time

    summary_lines = [
        "SUCCESS",
        f"Image: {image_name}",
        f"Source: {source_label}",
        f"Location: {repo_path.name}",
        f"Compress: {compression_label}",
        f"Elapsed: {_format_elapsed_duration(elapsed_seconds)}",
        f"Size: {devices.human_size(result.total_bytes_written)}",
    ]

    # Show success with Verify/Finish buttons
    selection = [1]  # Default to FINISH (right button)

    def render_screen():
        screens.render_verify_finish_buttons_screen(
            "BACKUP",
            summary_lines,
            selected_index=selection[0],
            title_icon=backup_title_icon,
        )

    render_screen()
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B])

    def on_left():
        if selection[0] == 1:
            selection[0] = 0
            _log_debug(log_debug, "Selection changed: VERIFY")

    def on_right():
        if selection[0] == 0:
            selection[0] = 1
            _log_debug(log_debug, "Selection changed: FINISH")

    def on_button_a():
        # A button = cancel/back, treat as Finish
        return True

    def on_button_b():
        # B button = confirm selection
        if selection[0] == 0:
            # VERIFY selected
            _log_debug(log_debug, "Starting verification")
            _verify_backup(source_name, image_dir, log_debug)
        return True

    gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: on_button_a,
            gpio.PIN_B: on_button_b,
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render_screen,
    )


def write_image(
    *, app_context: AppContext, log_debug: Optional[Callable[[str], None]] = None
) -> None:
    repos = image_repo.find_image_repos(image_repo.REPO_FLAG_FILENAME)
    if not repos:
        display.display_lines(["IMAGE REPO", "NOT FOUND"])
        time.sleep(1)
        return
    if len(repos) > 1:
        selected_repo = menus.select_list(
            "IMG REPO",
            [repo.path.name for repo in repos],
        )
        if selected_repo is None:
            return
        repo_path = repos[selected_repo].path
    else:
        repo_path = repos[0].path
    images = image_repo.list_clonezilla_images(repo_path)
    if not images:
        display.display_lines(["NO IMAGES", "FOUND"])
        time.sleep(1)
        return
    selected_index = menus.select_list(
        "CHOOSE IMAGE",
        [img.name for img in images],
        screen_id="images",
        enable_horizontal_scroll=True,
        scroll_start_delay=1.5,
    )
    if selected_index is None:
        return
    selected_image = images[selected_index]

    # Check if the selected image is an ISO or ImageUSB file
    is_iso = selected_image.is_iso
    is_imageusb = selected_image.is_imageusb

    # For Clonezilla images, prompt for partition mode
    if not is_iso and not is_imageusb:
        partition_selection = _prompt_restore_partition_mode()
        if partition_selection is None:
            return
        partition_mode, partition_label = partition_selection
    else:
        # ISOs and ImageUSB files don't need partition mode selection
        partition_mode = None
        partition_label = None
    usb_devices = devices.list_usb_disks()
    if not usb_devices:
        display.display_lines(["NO USB", "DRIVES"])
        time.sleep(1)
        return
    repo_devices = set()
    for device in usb_devices:
        mountpoints = _collect_mountpoints(device)
        if any(
            str(repo.path).startswith(mount) for mount in mountpoints for repo in repos
        ):
            repo_devices.add(device.get("name"))
    target_candidates = [
        device for device in usb_devices if device.get("name") not in repo_devices
    ]
    if not target_candidates:
        display.display_lines(["TARGET IS", "REPO DRIVE"])
        time.sleep(1)
        return
    selected_index = menus.select_usb_drive(
        "TARGET USB",
        target_candidates,
        title_icon=USB_ICON,
        selected_name=app_context.active_drive,
    )
    if selected_index is None:
        return
    target = target_candidates[selected_index]
    target_name = target.get("name")
    if not target_name:
        display.display_lines(["TARGET", "MISSING"])
        time.sleep(1)
        return
    app_context.active_drive = target_name
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

    # Handle ISOs and ImageUSB files differently from Clonezilla images
    if is_iso:
        if not _confirm_destructive_action(log_debug=log_debug):
            return
        _write_iso_image(selected_image.path, target, log_debug=log_debug)
        return

    # Handle ImageUSB .BIN files
    if is_imageusb:
        if not _confirm_destructive_action(log_debug=log_debug):
            return
        _write_imageusb_image(selected_image.path, target, log_debug=log_debug)
        return

    # Continue with Clonezilla image flow
    try:
        plan = clonezilla.parse_clonezilla_image(selected_image.path)
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
    assert partition_mode is not None
    assert partition_label is not None
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
    job_id = f"restore-{uuid4().hex}"
    op_log = get_logger(job_id=job_id, tags=["restore"], source="restore")
    op_log.info(
        "Starting restore: %s -> %s (mode %s)",
        selected_image.name,
        target_name,
        partition_mode,
    )

    def update_progress(lines: list[str], ratio: Optional[float]) -> None:
        nonlocal progress_lines, progress_ratio, progress_written_bytes, progress_written_percent, progress_ratio_snapshot
        clamped = None
        if ratio is not None:
            clamped = max(0.0, min(1.0, float(ratio)))
        trimmed_lines = [line for line in lines if line.strip() != "Working..."]
        if len(trimmed_lines) > 2:
            trimmed_lines = trimmed_lines[:2]
        with progress_lock:
            progress_lines = trimmed_lines
            if clamped is not None:
                progress_ratio = clamped
                progress_ratio_snapshot = clamped
            wrote_line = next(
                (line for line in lines if line.startswith("Wrote ")), None
            )
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
                target_name,
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
            title_icon=WRITE_ICON,
        )
        time.sleep(0.1)
    thread.join()
    lines, ratio = current_progress()
    screens.render_progress_screen(
        "WRITE",
        lines,
        progress_ratio=ratio,
        animate=False,
        title_icon=WRITE_ICON,
    )
    if "error" in error_holder:
        restore_error = error_holder["error"]
        _log_debug(log_debug, f"Restore failed: {restore_error}")
        screens.wait_for_paginated_input(
            "WRITE",
            ["FAILED", *_format_restore_error_lines(restore_error)],
            title_icon=WRITE_ICON,
        )
        return
    elapsed_seconds = time.monotonic() - start_time
    summary_lines = _build_restore_summary_lines(
        image_name=selected_image.name,
        target=target,
        partition_label=partition_label,
        elapsed_seconds=elapsed_seconds,
        written_bytes=progress_written_bytes,
        written_percent=progress_written_percent,
        ratio=progress_ratio_snapshot,
    )

    # Show confirmation screen with Verify and Finish buttons
    selection = [1]  # Default to FINISH (right button)

    def render_screen():
        screens.render_verify_finish_buttons_screen(
            "WRITE",
            summary_lines,
            selected_index=selection[0],
            title_icon=WRITE_ICON,
        )

    render_screen()
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B])

    def on_left():
        if selection[0] == 1:
            selection[0] = 0
            _log_debug(log_debug, "Selection changed: VERIFY")

    def on_right():
        if selection[0] == 0:
            selection[0] = 1
            _log_debug(log_debug, "Selection changed: FINISH")

    def on_button_a():
        # A button = cancel/back, treat as Finish
        return True

    def on_button_b():
        # B button = confirm selection
        if selection[0] == 0:
            # VERIFY selected
            _log_debug(log_debug, "Starting verification")
            _verify_restore(plan, target, log_debug)
        return True

    gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: on_button_a,
            gpio.PIN_B: on_button_b,
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render_screen,
    )


def _select_partitions_checklist(partition_labels: list[str]) -> Optional[list[bool]]:
    """Show a checklist for partition selection.

    Args:
        partition_labels: List of partition label strings

    Returns:
        List of booleans (True if selected), or None if cancelled
    """
    selected = [True] * len(partition_labels)  # All selected by default
    cursor_index = 0

    def render_screen():
        # For now, use a simple menu-based approach
        # TODO: Implement proper checklist UI with checkboxes
        lines = []
        for idx, label in enumerate(partition_labels):
            checkbox = "☑" if selected[idx] else "☐"
            marker = ">" if idx == cursor_index else " "
            lines.append(f"{marker}{checkbox} {label}")

        display.display_lines(["SELECT PARTS", "L/R=Toggle B=OK", *lines[:4]])

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
            cursor_index = min(len(partition_labels) - 1, cursor_index + 1)
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


def _verify_backup(
    source_device: str,
    image_dir,
    log_debug: Optional[Callable[[str], None]],
) -> None:
    """Verify a backup image against the source device."""
    _log_debug(log_debug, f"Verifying backup in {image_dir}")

    # Show progress screen during verification
    done = threading.Event()
    result_holder: dict[str, bool] = {}
    progress_lock = threading.Lock()
    progress_lines = ["Starting verification..."]
    progress_ratio: Optional[float] = 0.0

    def update_progress(lines: list[str], ratio: Optional[float]) -> None:
        nonlocal progress_lines, progress_ratio
        with progress_lock:
            progress_lines = lines
            if ratio is not None:
                progress_ratio = max(0.0, min(1.0, float(ratio)))

    def current_progress() -> tuple[list[str], Optional[float]]:
        with progress_lock:
            return list(progress_lines), progress_ratio

    def worker() -> None:
        try:
            success = clonezilla.verify_backup_image(
                source_device,
                image_dir,
                progress_callback=update_progress,
            )
            result_holder["success"] = success
        except Exception as exc:
            _log_debug(log_debug, f"Verification error: {exc}")
            result_holder["success"] = False
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while not done.is_set():
        lines, ratio = current_progress()
        screens.render_progress_screen(
            "VERIFY",
            lines,
            progress_ratio=ratio,
            animate=False,
            title_icon=INFO_ICON,
        )
        time.sleep(0.1)

    thread.join()

    # Show result
    success = result_holder.get("success", False)
    if success:
        _log_debug(log_debug, "Backup verification successful")
        screens.render_status_template(
            "VERIFY",
            "SUCCESS",
            extra_lines=[
                "Backup verification",
                "completed successfully.",
                "Press A/B to continue.",
            ],
        )
    else:
        _log_debug(log_debug, "Backup verification failed")
        screens.render_status_template(
            "VERIFY",
            "FAILED",
            extra_lines=[
                "Verification failed.",
                "Backup may be corrupt.",
                "Press A/B to continue.",
            ],
        )

    screens.wait_for_ack()


def _verify_restore(
    plan: clonezilla.RestorePlan,
    target: dict,
    log_debug: Optional[Callable[[str], None]],
) -> None:
    """Verify the restored image against the target disk."""
    target_name = target.get("name", "")
    _log_debug(log_debug, f"Verifying restore to {target_name}")

    # Show progress screen during verification
    done = threading.Event()
    result_holder: dict[str, bool] = {}
    progress_lock = threading.Lock()
    progress_lines = ["Starting verification..."]
    progress_ratio: Optional[float] = 0.0

    def update_progress(lines: list[str], ratio: Optional[float]) -> None:
        nonlocal progress_lines, progress_ratio
        with progress_lock:
            progress_lines = lines
            if ratio is not None:
                progress_ratio = max(0.0, min(1.0, float(ratio)))

    def current_progress() -> tuple[list[str], Optional[float]]:
        with progress_lock:
            return list(progress_lines), progress_ratio

    def worker() -> None:
        try:
            success = clonezilla.verify_restored_image(
                plan,
                target_name,
                progress_callback=update_progress,
            )
            result_holder["success"] = success
        except Exception as exc:
            _log_debug(log_debug, f"Verification error: {exc}")
            result_holder["success"] = False
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while not done.is_set():
        lines, ratio = current_progress()
        screens.render_progress_screen(
            "VERIFY",
            lines,
            progress_ratio=ratio,
            animate=False,
            title_icon=INFO_ICON,
        )
        time.sleep(0.1)

    thread.join()

    # Show result
    success = result_holder.get("success", False)
    if success:
        _log_debug(log_debug, "Verification successful")
        screens.render_status_template(
            "VERIFY",
            "SUCCESS",
            extra_lines=[
                "Image verification",
                "completed successfully.",
                "Press A/B to continue.",
            ],
        )
    else:
        _log_debug(log_debug, "Verification failed")
        screens.render_status_template(
            "VERIFY",
            "FAILED",
            extra_lines=[
                "Verification failed.",
                "Data may not match",
                "source image.",
                "Press A/B to continue.",
            ],
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
        title_icon=SETTINGS_ICON,
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
        title_icon=ALERT_ICON,
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
    selection = [default]  # Use list for mutability in closures

    def render():
        screens.render_confirmation_screen(
            title,
            prompt_lines_list,
            selected_index=selection[0],
            title_icon=title_icon,
        )

    render()
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B])

    def on_right():
        if selection[0] == app_state.CONFIRM_NO:
            selection[0] = app_state.CONFIRM_YES
            _log_debug(log_debug, f"Confirmation changed: {selection[0]}")

    def on_left():
        if selection[0] == app_state.CONFIRM_YES:
            selection[0] = app_state.CONFIRM_NO
            _log_debug(log_debug, f"Confirmation changed: {selection[0]}")

    result = gpio.poll_button_events(
        {
            gpio.PIN_R: on_right,
            gpio.PIN_L: on_left,
            gpio.PIN_A: lambda: False,  # Cancel
            gpio.PIN_B: lambda: selection[0] == app_state.CONFIRM_YES,  # Confirm
        },
        poll_interval=menus.BUTTON_POLL_DELAY,
        loop_callback=render,
    )

    return result if result is not None else False


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
    lines = [step_line, reason] if reason and reason != step_line else [step_line]
    if message not in lines:
        lines.append(message)
    return lines


def _short_restore_reason(message: str) -> str:
    lower = message.lower()
    if "partclone tool not found" in lower or (
        "partclone." in lower and "not found" in lower
    ):
        fstype_match = re.search(
            r"filesystem ['\"]?([^'\"]+)['\"]?", message, re.IGNORECASE
        )
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
    match = re.search(
        r"stderr:\s*(.*?)(?:\s*(?:stdout:|$))", message, re.IGNORECASE | re.DOTALL
    )
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
        "SUCCESS",
        f"Image {image_name}",
        f"Target {target_label}",
        f"Mode {partition_label}",
        f"Elapsed {_format_elapsed_duration(elapsed_seconds)}",
        written_line,
    ]


def _write_iso_image(
    iso_path,
    target: dict,
    *,
    log_debug: Optional[Callable[[str], None]] = None,
) -> None:
    """Write an ISO file directly to a USB device."""
    done = threading.Event()
    error_holder: dict[str, Exception] = {}
    progress_lock = threading.Lock()
    progress_lines = ["Preparing..."]
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
            wrote_line = next(
                (line for line in lines if line.startswith("Wrote ")), None
            )
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
            iso.restore_iso_image(
                iso_path,
                target.get("name") or "",
                progress_callback=update_progress,
            )
        except Exception as exc:
            error_holder["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    while not done.is_set():
        lines, ratio = current_progress()
        screens.render_progress_screen(
            "WRITE ISO",
            lines,
            progress_ratio=ratio,
            animate=False,
            title_icon=WRITE_ICON,
        )
        time.sleep(0.1)
    thread.join()
    lines, ratio = current_progress()
    screens.render_progress_screen(
        "WRITE ISO",
        lines,
        progress_ratio=ratio,
        animate=False,
        title_icon=WRITE_ICON,
    )
    if "error" in error_holder:
        error = error_holder["error"]
        _log_debug(log_debug, f"ISO write failed: {error}")
        screens.wait_for_paginated_input(
            "WRITE ISO",
            ["FAILED", str(error)],
            title_icon=WRITE_ICON,
        )
        return
    elapsed_seconds = time.monotonic() - start_time
    target_label = devices.format_device_label(target)
    summary_lines = [
        "SUCCESS",
        f"ISO {iso_path.name}",
        f"Target {target_label}",
        f"Elapsed {_format_elapsed_duration(elapsed_seconds)}",
    ]
    if progress_written_bytes and progress_written_percent:
        summary_lines.append(
            f"Wrote {progress_written_bytes} {progress_written_percent}"
        )
    elif progress_written_bytes:
        summary_lines.append(f"Wrote {progress_written_bytes}")
    elif progress_ratio_snapshot is not None:
        summary_lines.append(f"Wrote {progress_ratio_snapshot * 100:.1f}%")

    screens.render_status_template(
        "WRITE ISO",
        "SUCCESS",
        extra_lines=summary_lines,
    )
    screens.wait_for_ack()


def verify_clone(
    *, app_context: AppContext, log_debug: Optional[Callable[[str], None]] = None
) -> None:
    """Verify a previously created backup image against a device."""
    # Step 1: Find image repositories
    repos = image_repo.find_image_repos(image_repo.REPO_FLAG_FILENAME)
    if not repos:
        display.display_lines(["IMAGE REPO", "NOT FOUND"])
        time.sleep(1)
        return

    # Step 2: Select repository if multiple
    if len(repos) > 1:
        selected_repo = menus.select_list(
            "IMG REPO",
            [repo.path.name for repo in repos],
        )
        if selected_repo is None:
            return
        repo_path = repos[selected_repo].path
    else:
        repo_path = repos[0].path

    # Step 3: List images in repository
    images = image_repo.list_clonezilla_images(repo_path)
    if not images:
        display.display_lines(["NO IMAGES", "FOUND"])
        time.sleep(1)
        return

    # Step 4: Select image to verify
    selected_index = menus.select_list(
        "VERIFY IMAGE",
        [img.name for img in images],
        screen_id="verify_images",
        enable_horizontal_scroll=True,
        scroll_start_delay=1.5,
    )
    if selected_index is None:
        return

    selected_image = images[selected_index]

    # Skip ISOs and ImageUSB - they don't have verification support
    if selected_image.is_iso or selected_image.is_imageusb:
        display.display_lines(["VERIFY NOT", "SUPPORTED"])
        time.sleep(1)
        return

    # Step 5: Parse the Clonezilla image
    try:
        plan = clonezilla.parse_clonezilla_image(selected_image.path)
    except RuntimeError as error:
        _log_debug(log_debug, f"Image load failed: {error}")
        display.display_lines(["IMAGE", "INVALID"])
        time.sleep(1)
        return

    # Step 6: Select device to verify against
    usb_devices = devices.list_usb_disks()
    if not usb_devices:
        display.display_lines(["NO USB", "DRIVES"])
        time.sleep(1)
        return

    # Filter out repository devices
    repo_devices = set()
    for device in usb_devices:
        mountpoints = _collect_mountpoints(device)
        if any(
            str(repo.path).startswith(mount) for mount in mountpoints for repo in repos
        ):
            repo_devices.add(device.get("name"))

    target_candidates = [
        device for device in usb_devices if device.get("name") not in repo_devices
    ]
    if not target_candidates:
        display.display_lines(["NO TARGET", "AVAILABLE"])
        time.sleep(1)
        return

    selected_target_index = menus.select_usb_drive(
        "VERIFY DEVICE",
        target_candidates,
        title_icon=USB_ICON,
        selected_name=app_context.active_drive,
    )
    if selected_target_index is None:
        return

    target = target_candidates[selected_target_index]
    target_name = target.get("name")
    if not target_name:
        display.display_lines(["TARGET", "MISSING"])
        time.sleep(1)
        return

    app_context.active_drive = target_name
    _log_debug(log_debug, f"Verifying {selected_image.name} against {target_name}")

    # Step 7: Run verification
    _verify_restore(plan, target, log_debug)


def _write_imageusb_image(
    bin_path,
    target: dict,
    *,
    log_debug: Optional[Callable[[str], None]] = None,
) -> None:
    """Write an ImageUSB .BIN file directly to a USB device."""
    done = threading.Event()
    error_holder: dict[str, Exception] = {}
    progress_lock = threading.Lock()
    progress_lines = ["Preparing..."]
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
            wrote_line = next(
                (line for line in lines if line.startswith("Wrote ")), None
            )
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
            imageusb.restore_imageusb_file(
                bin_path,
                target.get("name") or "",
                progress_callback=update_progress,
            )
        except Exception as exc:
            error_holder["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    while not done.is_set():
        lines, ratio = current_progress()
        screens.render_progress_screen(
            "WRITE BIN",
            lines,
            progress_ratio=ratio,
            animate=False,
            title_icon=WRITE_ICON,
        )
        time.sleep(0.1)
    thread.join()
    lines, ratio = current_progress()
    screens.render_progress_screen(
        "WRITE BIN",
        lines,
        progress_ratio=ratio,
        animate=False,
        title_icon=WRITE_ICON,
    )
    if "error" in error_holder:
        error = error_holder["error"]
        _log_debug(log_debug, f"ImageUSB write failed: {error}")
        screens.wait_for_paginated_input(
            "WRITE BIN",
            ["FAILED", str(error)],
            title_icon=WRITE_ICON,
        )
        return
    elapsed_seconds = time.monotonic() - start_time
    target_label = devices.format_device_label(target)
    summary_lines = [
        "SUCCESS",
        f"ImageUSB {bin_path.name}",
        f"Target {target_label}",
        f"Elapsed {_format_elapsed_duration(elapsed_seconds)}",
    ]
    if progress_written_bytes and progress_written_percent:
        summary_lines.append(
            f"Wrote {progress_written_bytes} {progress_written_percent}"
        )
    elif progress_written_bytes:
        summary_lines.append(f"Wrote {progress_written_bytes}")
    elif progress_ratio_snapshot is not None:
        summary_lines.append(f"Wrote {progress_ratio_snapshot * 100:.1f}%")

    screens.render_status_template(
        "WRITE BIN",
        "SUCCESS",
        extra_lines=summary_lines,
    )
    screens.wait_for_ack()
