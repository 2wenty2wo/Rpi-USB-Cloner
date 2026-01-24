"""Software update management."""

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.logging import LoggerFactory
from rpi_usb_cloner.menu.model import get_screen_icon
from rpi_usb_cloner.ui import display, menus, screens

from .system_power import confirm_action
from .system_utils import (
    format_command_output,
    get_app_version,
    has_dirty_working_tree,
    is_dubious_ownership_error,
    is_git_repo,
    is_running_under_systemd,
    run_command,
    run_git_pull,
)
from .system_utils import (
    restart_service as restart_systemd_service,
)

# Create logger for update operations
log = LoggerFactory.for_system()


def get_update_status(repo_root: Path) -> tuple[str, Optional[int]]:
    """Check if updates are available."""
    if not is_git_repo(repo_root):
        log.debug("Update status check: repo not found", component="update_manager")
        return "Repo not found", None
    fetch = run_command(["git", "fetch", "--quiet"], cwd=repo_root)
    if fetch.returncode != 0:
        log.debug(
            f"Update status check: fetch failed {fetch.returncode}",
            component="update_manager",
        )
        return "Unable to check", None
    upstream = run_command(
        ["git", "rev-parse", "--abbrev-ref", "@{u}"],
        cwd=repo_root,
    )
    upstream_ref = upstream.stdout.strip()
    if upstream.returncode != 0 or not upstream_ref:
        log.debug("Update status check: upstream missing", component="update_manager")
        return "No upstream configured", None
    behind = run_command(
        ["git", "rev-list", "--count", "HEAD..@{u}"],
        cwd=repo_root,
    )
    if behind.returncode != 0:
        log.debug("Update status check: rev-list failed", component="update_manager")
        return "Unable to check", None
    count = behind.stdout.strip()
    log.debug(
        f"Update status check: behind count={count!r}", component="update_manager"
    )
    if count.isdigit():
        behind_count = int(count)
        status = "Update available" if behind_count > 0 else "Up to date"
        return status, behind_count
    return "Up to date", None


def check_update_status(repo_root: Path) -> tuple[str, Optional[int], str]:
    """Check update status and return with timestamp."""
    status, behind_count = get_update_status(repo_root)
    last_checked = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    log.debug(
        f"Update status check complete at {last_checked}: {status}",
        component="update_manager",
    )
    return status, behind_count, last_checked


def build_update_info_lines(
    version: str,
    status: str,
    behind_count: Optional[int],
    last_checked: Optional[str],
) -> list[str]:
    """Build info lines for update display."""
    status_display = status
    if status == "Update available":
        status_display = "Update avail."
    lines = [f"Version: {version}", f"Status: {status_display}"]
    # Always add a third line to prevent layout shift
    if behind_count is not None and behind_count > 0:
        lines.append(f"Commits behind: {behind_count}")
    else:
        lines.append("")  # Empty line to reserve space
    return lines


def run_update_flow(
    title: str,
    *,
    title_icon: Optional[str] = None,
) -> None:
    """Execute the software update process."""
    repo_root = Path(__file__).resolve().parents[3]
    log.debug(f"Repo root detection: {repo_root}", component="update_manager")
    is_repo = is_git_repo(repo_root)
    log.debug(f"Repo root is git repo: {is_repo}", component="update_manager")
    if not is_repo:
        log.debug("Update aborted: repo not found", component="update_manager")
        screens.wait_for_paginated_input(
            title,
            ["Repo not found"],
            title_icon=title_icon,
        )
        return
    dirty_tree = has_dirty_working_tree(repo_root)
    if dirty_tree:
        log.debug("Dirty working tree detected", component="update_manager")
        prompt = "Continue with update?"
    else:
        prompt = "Are you sure you want to update?"
    if not confirm_action(title, prompt, title_icon=title_icon):
        log.debug("Update canceled by confirmation prompt", component="update_manager")
        return

    def run_with_progress(
        lines: list[str],
        action: Callable[[Callable[[float], None]], subprocess.CompletedProcess[str]],
        *,
        running_ratio: Optional[float] = 0.5,
    ):
        done = threading.Event()
        result_holder: dict[str, subprocess.CompletedProcess[str]] = {}
        error_holder: dict[str, Exception] = {}
        progress_lock = threading.Lock()
        progress_ratio = 0.0

        def update_progress(value: float) -> None:
            nonlocal progress_ratio
            clamped = max(0.0, min(1.0, float(value)))
            with progress_lock:
                progress_ratio = clamped

        def current_progress() -> float:
            with progress_lock:
                return progress_ratio

        def worker() -> None:
            try:
                if running_ratio is not None:
                    update_progress(running_ratio)
                result_holder["result"] = action(update_progress)
            except (
                Exception
            ) as exc:  # pragma: no cover - defensive for subprocess errors
                error_holder["error"] = exc
            finally:
                update_progress(1.0)
                done.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        update_progress(0.0)
        while not done.is_set():
            screens.render_progress_screen(
                title,
                lines,
                progress_ratio=current_progress(),
                animate=False,
                title_icon=title_icon,
            )
            time.sleep(0.1)
        thread.join()
        screens.render_progress_screen(
            title,
            lines,
            progress_ratio=current_progress(),
            animate=False,
            title_icon=title_icon,
        )
        if "error" in error_holder:
            raise error_holder["error"]
        return result_holder["result"]

    pull_result = run_with_progress(
        ["Updating...", "Pulling..."],
        lambda update_progress: run_git_pull(
            repo_root,
            progress_callback=update_progress,
        ),
        running_ratio=None,
    )
    dubious_ownership = is_dubious_ownership_error(pull_result.stderr)
    if dubious_ownership and is_running_under_systemd():
        log.debug(
            f"Dubious ownership detected; adding safe.directory for {repo_root}",
            component="update_manager",
        )
        run_command(
            ["git", "config", "--global", "--add", "safe.directory", str(repo_root)],
        )
        pull_result = run_with_progress(
            ["Updating...", "Pulling again..."],
            lambda update_progress: run_git_pull(
                repo_root,
                progress_callback=update_progress,
            ),
            running_ratio=None,
        )
    output_lines = format_command_output(pull_result.stdout, pull_result.stderr)
    if dubious_ownership:
        output_lines = [
            "Dubious ownership detected.",
            "Service User= should own repo.",
            f"Or run: git config --global --add safe.directory {repo_root}",
        ] + output_lines
    if pull_result.returncode != 0:
        log.debug(
            f"Git pull failed with return code {pull_result.returncode}",
            component="update_manager",
        )
        if dubious_ownership:
            output_lines = ["Git safety check failed."] + output_lines
        display.render_paginated_lines(
            title,
            ["Update failed"] + output_lines,
            page_index=0,
            title_icon=title_icon,
        )
        time.sleep(2)
        return
    screens.render_progress_screen(
        title,
        ["Update complete"],
        progress_ratio=1.0,
        animate=False,
        title_icon=title_icon,
    )
    if output_lines:
        display.render_paginated_lines(
            title,
            ["Update complete"] + output_lines,
            page_index=0,
            title_icon=title_icon,
        )
    time.sleep(1)
    if is_running_under_systemd():
        restart_result = run_with_progress(
            ["Restarting...", "rpi-usb-cloner.service"],
            lambda update_progress: restart_systemd_service(),
        )
        if restart_result.returncode != 0:
            log.debug(
                f"Service restart failed with return code {restart_result.returncode}",
                component="update_manager",
            )
            display.render_paginated_lines(
                title,
                ["Restart failed"]
                + format_command_output(restart_result.stdout, restart_result.stderr),
                page_index=0,
                title_icon=title_icon,
            )
            time.sleep(2)
            return
        sys.exit(0)
    display.render_paginated_lines(
        title,
        ["Restart needed", "Please restart"],
        page_index=0,
        title_icon=title_icon,
    )
    time.sleep(2)


def update_version() -> None:
    """Main update version interface."""
    title = "UPDATE"
    title_icon = get_screen_icon("update")
    repo_root = Path(__file__).resolve().parents[3]
    status = "Checking..."
    behind_count: Optional[int] = None
    last_checked: Optional[str] = None
    version = get_app_version()
    check_done = threading.Event()
    git_lock = threading.Lock()
    results_applied = False
    result_holder: dict[str, tuple[str, Optional[int], str]] = {}
    error_holder: dict[str, Exception] = {}
    header_lines: list[str] = []
    selection = 0

    def apply_check_results() -> tuple[str, Optional[int], Optional[str]]:
        if "result" in result_holder:
            return (
                result_holder["result"][0],
                result_holder["result"][1],
                result_holder["result"][2],
            )
        if "error" in error_holder:
            log.debug(
                f"Update status check failed: {error_holder['error']}",
                component="update_manager",
            )
            return (
                "Unable to check",
                None,
                time.strftime("%Y-%m-%d %H:%M", time.localtime()),
            )
        return status, behind_count, last_checked

    def apply_check_results_to_state() -> None:
        nonlocal status, behind_count, last_checked, results_applied
        status, behind_count, last_checked = apply_check_results()
        results_applied = True

    def update_header_lines() -> None:
        header_lines[:] = build_update_info_lines(
            version, status, behind_count, last_checked
        )

    def refresh_update_menu() -> bool:
        if check_done.is_set() and not results_applied:
            apply_check_results_to_state()
            update_header_lines()
            return True
        return False

    def run_check_in_background() -> None:
        try:
            with git_lock:
                result_holder["result"] = check_update_status(repo_root)
        except Exception as exc:  # pragma: no cover - defensive for subprocess errors
            error_holder["error"] = exc
        finally:
            check_done.set()

    thread = threading.Thread(target=run_check_in_background, daemon=True)
    thread.start()
    menus.wait_for_buttons_release(
        [gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D, gpio.PIN_A, gpio.PIN_B]
    )
    prev_states = {
        "L": gpio.is_pressed(gpio.PIN_L),
        "R": gpio.is_pressed(gpio.PIN_R),
        "U": gpio.is_pressed(gpio.PIN_U),
        "D": gpio.is_pressed(gpio.PIN_D),
        "A": gpio.is_pressed(gpio.PIN_A),
        "B": gpio.is_pressed(gpio.PIN_B),
    }
    while True:
        if check_done.is_set():
            apply_check_results_to_state()
        update_header_lines()
        screens.render_update_buttons_screen(
            title,
            header_lines,
            selected_index=selection,
            title_icon=title_icon,
        )
        refresh_needed = False
        if refresh_update_menu():
            refresh_needed = True
        current_l = gpio.is_pressed(gpio.PIN_L)
        if not prev_states["L"] and current_l and selection == 1:
            selection = 0
            refresh_needed = True
        current_r = gpio.is_pressed(gpio.PIN_R)
        if not prev_states["R"] and current_r and selection == 0:
            selection = 1
            refresh_needed = True
        current_u = gpio.is_pressed(gpio.PIN_U)
        if not prev_states["U"] and current_u and selection == 1:
            selection = 0
            refresh_needed = True
        current_d = gpio.is_pressed(gpio.PIN_D)
        if not prev_states["D"] and current_d and selection == 0:
            selection = 1
            refresh_needed = True
        current_a = gpio.is_pressed(gpio.PIN_A)
        if not prev_states["A"] and current_a:
            return
        current_b = gpio.is_pressed(gpio.PIN_B)
        if not prev_states["B"] and current_b:
            if selection == 0:
                if not check_done.is_set():
                    status = "Checking..."
                    behind_count = None
                    update_header_lines()
                    while not check_done.is_set():
                        screens.render_update_buttons_screen(
                            title,
                            header_lines,
                            selected_index=selection,
                            title_icon=title_icon,
                        )
                        time.sleep(menus.BUTTON_POLL_DELAY)
                    apply_check_results_to_state()
                    update_header_lines()
                else:
                    status = "Checking..."
                    behind_count = None
                    update_header_lines()
                    screens.render_update_buttons_screen(
                        title,
                        header_lines,
                        selected_index=selection,
                        title_icon=title_icon,
                    )
                    with git_lock:
                        status, behind_count, last_checked = check_update_status(
                            repo_root
                        )
                    update_header_lines()
                    screens.render_update_buttons_screen(
                        title,
                        header_lines,
                        selected_index=selection,
                        title_icon=title_icon,
                    )
                    version = get_app_version()
                    result_holder["result"] = (status, behind_count, last_checked)
                    check_done.set()
                    results_applied = True
                refresh_needed = True
            if selection == 1:
                if not check_done.is_set():
                    status = "Waiting on check..."
                    update_header_lines()
                    while not check_done.is_set():
                        screens.render_update_buttons_screen(
                            title,
                            header_lines,
                            selected_index=selection,
                            title_icon=title_icon,
                        )
                        time.sleep(menus.BUTTON_POLL_DELAY)
                    apply_check_results_to_state()
                with git_lock:
                    run_update_flow(title, title_icon=title_icon)
                    status, behind_count, last_checked = check_update_status(repo_root)
                version = get_app_version()
                result_holder["result"] = (status, behind_count, last_checked)
                check_done.set()
                results_applied = True
                refresh_needed = True
            menus.wait_for_buttons_release(
                [gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D, gpio.PIN_A, gpio.PIN_B]
            )
            prev_states = {
                "L": gpio.is_pressed(gpio.PIN_L),
                "R": gpio.is_pressed(gpio.PIN_R),
                "U": gpio.is_pressed(gpio.PIN_U),
                "D": gpio.is_pressed(gpio.PIN_D),
                "A": gpio.is_pressed(gpio.PIN_A),
                "B": gpio.is_pressed(gpio.PIN_B),
            }
            if refresh_needed:
                apply_check_results_to_state()
                update_header_lines()
            time.sleep(menus.BUTTON_POLL_DELAY)
            continue
        if refresh_needed:
            screens.render_update_buttons_screen(
                title,
                header_lines,
                selected_index=selection,
                title_icon=title_icon,
            )
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        time.sleep(menus.BUTTON_POLL_DELAY)
