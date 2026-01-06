import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.config import settings
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.menu.model import get_screen_icon
from rpi_usb_cloner.ui import display, keyboard, menus, screens, screensaver


_SERVICE_NAME = "rpi-usb-cloner.service"


def coming_soon() -> None:
    screens.show_coming_soon(title="SETTINGS")


def wifi_settings() -> None:
    screens.show_wifi_settings(title="WIFI")


def select_restore_partition_mode() -> None:
    options = [
        ("k0", "USE SOURCE (-k0)"),
        ("k", "SKIP TABLE (-k)"),
        ("k1", "RESIZE TABLE (-k1)"),
        ("k2", "MANUAL TABLE (-k2)"),
    ]
    current_mode = str(settings.get_setting("restore_partition_mode", "k0")).lstrip("-")
    selected_index = 0
    for index, (value, _) in enumerate(options):
        if value == current_mode:
            selected_index = index
            break
    selection = menus.render_menu_list(
        "RESTORE PT",
        [label for _, label in options],
        footer=["BACK", "OK"],
        selected_index=selected_index,
        header_lines=["Partition table mode"],
    )
    if selection is None:
        return
    selected_value, selected_label = options[selection]
    settings.set_setting("restore_partition_mode", selected_value)
    screens.render_status_template("RESTORE PT", f"Set: {selected_label}")
    time.sleep(1.5)


def screensaver_settings() -> None:
    toggle_screensaver_enabled()


def toggle_screensaver_enabled() -> None:
    enabled = settings.get_bool("screensaver_enabled", default=app_state.ENABLE_SLEEP)
    enabled = not enabled
    settings.set_bool("screensaver_enabled", enabled)
    app_state.ENABLE_SLEEP = enabled
    status = "ENABLED" if enabled else "DISABLED"
    screens.render_status_template("SCREENSAVER", f"Screensaver {status}")
    time.sleep(1.5)


def toggle_screensaver_mode() -> None:
    mode = settings.get_setting("screensaver_mode", "random")
    new_mode = "selected" if mode == "random" else "random"
    settings.set_setting("screensaver_mode", new_mode)
    status = "SELECTED" if new_mode == "selected" else "RANDOM"
    screens.render_status_template("SCREENSAVER", f"Mode: {status}")
    time.sleep(1.5)


def select_screensaver_gif() -> None:
    gif_paths = screensaver.list_available_gifs()
    if not gif_paths:
        screens.render_status_template("SCREENSAVER", "No GIFs found")
        time.sleep(1.5)
        return
    gif_names = [path.name for path in gif_paths]
    current_selection = settings.get_setting("screensaver_gif")
    selected_index = 0
    if current_selection in gif_names:
        selected_index = gif_names.index(current_selection)
    selection = menus.render_menu_list(
        "SELECT GIF",
        gif_names,
        selected_index=selected_index,
    )
    if selection is None:
        return
    selected_name = gif_names[selection]
    settings.set_setting("screensaver_gif", selected_name)
    screens.render_status_template("SCREENSAVER", f"Selected {selected_name}")
    time.sleep(1.5)


def keyboard_test() -> None:
    text = keyboard.prompt_text(title="KEYBOARD", masked=False)
    if text is None:
        return
    screens.render_status_template("KEYBOARD", "Entry captured")
    time.sleep(1.5)


def font_awesome_demo() -> None:
    screens.show_font_awesome_demo()


def lucide_demo() -> None:
    screens.show_lucide_demo()


def heroicons_demo() -> None:
    screens.show_heroicons_demo()


def update_version(*, log_debug: Optional[Callable[[str], None]] = None) -> None:
    title = "UPDATE"
    title_icon = get_screen_icon("update")
    repo_root = Path(__file__).resolve().parents[2]
    status = "Checking..."
    last_checked: str | None = None
    version = _get_app_version(log_debug=log_debug)
    check_done = threading.Event()
    git_lock = threading.Lock()
    results_applied = False
    result_holder: dict[str, tuple[str, str]] = {}
    error_holder: dict[str, Exception] = {}
    menu_items = ["CHECK FOR UPDATES", "UPDATE"]
    header_lines: list[str] = []

    def apply_check_results() -> tuple[str, str | None]:
        if "result" in result_holder:
            return result_holder["result"][0], result_holder["result"][1]
        if "error" in error_holder:
            _log_debug(
                log_debug,
                f"Update status check failed: {error_holder['error']}",
            )
            return "Unable to check", time.strftime("%Y-%m-%d %H:%M", time.localtime())
        return status, last_checked

    def apply_check_results_to_state() -> None:
        nonlocal status, last_checked, results_applied
        status, last_checked = apply_check_results()
        results_applied = True

    def update_header_lines() -> None:
        header_lines[:] = _build_update_info_lines(version, status, last_checked)

    def refresh_update_menu() -> Optional[list[str]]:
        if check_done.is_set() and not results_applied:
            apply_check_results_to_state()
            update_header_lines()
            return list(menu_items)
        return None

    def run_check_in_background() -> None:
        try:
            with git_lock:
                result_holder["result"] = _check_update_status(repo_root, log_debug=log_debug)
        except Exception as exc:  # pragma: no cover - defensive for subprocess errors
            error_holder["error"] = exc
        finally:
            check_done.set()

    thread = threading.Thread(target=run_check_in_background, daemon=True)
    thread.start()
    while True:
        if check_done.is_set():
            apply_check_results_to_state()
        update_header_lines()
        content_top = _get_update_menu_top(title, header_lines, title_icon=title_icon)
        selection = menus.render_menu_list(
            title,
            menu_items,
            content_top=content_top,
            header_lines=header_lines,
            title_icon=title_icon,
            refresh_callback=refresh_update_menu,
        )
        if selection is None:
            return
        if selection == 0:
            checking_lines = _build_update_info_lines(version, "Checking...", last_checked)
            display.render_paginated_lines(
                title,
                checking_lines,
                page_index=0,
                title_icon=title_icon,
            )
            if not check_done.is_set():
                check_done.wait()
                apply_check_results_to_state()
            else:
                with git_lock:
                    status, last_checked = _check_update_status(repo_root, log_debug=log_debug)
                version = _get_app_version(log_debug=log_debug)
                result_holder["result"] = (status, last_checked)
                check_done.set()
                results_applied = True
            continue
        if selection == 1:
            if not check_done.is_set():
                waiting_lines = _build_update_info_lines(version, "Waiting on check...", last_checked)
                display.render_paginated_lines(
                    title,
                    waiting_lines,
                    page_index=0,
                    title_icon=title_icon,
                )
                check_done.wait()
                apply_check_results_to_state()
            with git_lock:
                _run_update_flow(title, log_debug=log_debug, title_icon=title_icon)
                status, last_checked = _check_update_status(repo_root, log_debug=log_debug)
            version = _get_app_version(log_debug=log_debug)
            result_holder["result"] = (status, last_checked)
            check_done.set()
            results_applied = True
            continue


def restart_service(*, log_debug: Optional[Callable[[str], None]] = None) -> None:
    title = "POWER"
    screens.render_status_template(title, "Restarting...", progress_line=_SERVICE_NAME)
    display.clear_display()
    restart_result = _restart_systemd_service(log_debug=log_debug)
    if restart_result.returncode != 0:
        _log_debug(log_debug, f"Service restart failed with return code {restart_result.returncode}")
        screens.wait_for_paginated_input(
            title,
            ["Service restart failed"]
            + _format_command_output(restart_result.stdout, restart_result.stderr),
        )
        return
    display.clear_display()
    sys.exit(0)


def stop_service(*, log_debug: Optional[Callable[[str], None]] = None) -> None:
    title = "POWER"
    screens.render_status_template(title, "Stopping...", progress_line=_SERVICE_NAME)
    display.clear_display()
    stop_result = _stop_systemd_service(log_debug=log_debug)
    if stop_result.returncode != 0:
        _log_debug(log_debug, f"Service stop failed with return code {stop_result.returncode}")
        screens.wait_for_paginated_input(
            title,
            ["Service stop failed"] + _format_command_output(stop_result.stdout, stop_result.stderr),
        )
        return
    display.clear_display()
    sys.exit(0)


def restart_system(*, log_debug: Optional[Callable[[str], None]] = None) -> None:
    title = "POWER"
    if not _confirm_power_action(title, "RESTART SYSTEM", log_debug=log_debug):
        return
    screens.render_status_template(title, "Restarting...", progress_line="System reboot")
    display.clear_display()
    reboot_result = _reboot_system(log_debug=log_debug)
    if reboot_result.returncode != 0:
        _log_debug(log_debug, f"System reboot failed with return code {reboot_result.returncode}")
        screens.wait_for_paginated_input(
            title,
            ["System reboot failed"] + _format_command_output(reboot_result.stdout, reboot_result.stderr),
        )


def shutdown_system(*, log_debug: Optional[Callable[[str], None]] = None) -> None:
    title = "POWER"
    if not _confirm_power_action(title, "SHUTDOWN SYSTEM", log_debug=log_debug):
        return
    screens.render_status_template(title, "Shutting down...", progress_line="System poweroff")
    display.clear_display()
    shutdown_result = _poweroff_system(log_debug=log_debug)
    if shutdown_result.returncode != 0:
        _log_debug(log_debug, f"System poweroff failed with return code {shutdown_result.returncode}")
        screens.wait_for_paginated_input(
            title,
            ["System poweroff failed"]
            + _format_command_output(shutdown_result.stdout, shutdown_result.stderr),
        )
        return
    display.clear_display()
    display.display_lines(["Shutdown initiated", "Safe to remove power"])
    while True:
        time.sleep(1)


def _run_update_flow(
    title: str,
    *,
    log_debug: Optional[Callable[[str], None]],
    title_icon: Optional[str] = None,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _log_debug(log_debug, f"Repo root detection: {repo_root}")
    is_repo = _is_git_repo(repo_root)
    _log_debug(log_debug, f"Repo root is git repo: {is_repo}")
    if not is_repo:
        _log_debug(log_debug, "Update aborted: repo not found")
        screens.wait_for_paginated_input(
            title,
            ["Repo not found"],
            title_icon=title_icon,
        )
        return
    dirty_tree = _has_dirty_working_tree(repo_root, log_debug=log_debug)
    if dirty_tree:
        _log_debug(log_debug, "Dirty working tree detected")
        prompt = "Continue with update?"
    else:
        prompt = "Are you sure you want to update?"
    if not _confirm_action(title, prompt, log_debug=log_debug):
        _log_debug(log_debug, "Update canceled by confirmation prompt")
        return

    def run_with_progress(lines: list[str], action: Callable[[], subprocess.CompletedProcess[str]]):
        done = threading.Event()
        result_holder: dict[str, subprocess.CompletedProcess[str]] = {}
        error_holder: dict[str, Exception] = {}

        def worker() -> None:
            try:
                result_holder["result"] = action()
            except Exception as exc:  # pragma: no cover - defensive for subprocess errors
                error_holder["error"] = exc
            finally:
                done.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        screens.render_progress_screen(
            title,
            lines,
            progress_ratio=lambda: 1.0 if done.is_set() else None,
            animate=True,
            title_icon=title_icon,
        )
        thread.join()
        if "error" in error_holder:
            raise error_holder["error"]
        return result_holder["result"]

    pull_result = run_with_progress(
        ["Updating...", "Pulling..."],
        lambda: _run_git_pull(repo_root, log_debug=log_debug),
    )
    dubious_ownership = _is_dubious_ownership_error(pull_result.stderr)
    if dubious_ownership and _is_running_under_systemd(log_debug=log_debug):
        _log_debug(
            log_debug,
            f"Dubious ownership detected; adding safe.directory for {repo_root}",
        )
        _run_command(
            ["git", "config", "--global", "--add", "safe.directory", str(repo_root)],
            log_debug=log_debug,
        )
        pull_result = run_with_progress(
            ["Updating...", "Pulling again..."],
            lambda: _run_git_pull(repo_root, log_debug=log_debug),
        )
    output_lines = _format_command_output(pull_result.stdout, pull_result.stderr)
    if dubious_ownership:
        output_lines = (
            [
                "Dubious ownership detected.",
                "Service User= should own repo.",
                f"Or run: git config --global --add safe.directory {repo_root}",
            ]
            + output_lines
        )
    if pull_result.returncode != 0:
        _log_debug(log_debug, f"Git pull failed with return code {pull_result.returncode}")
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
    if _is_running_under_systemd(log_debug=log_debug):
        restart_result = run_with_progress(
            ["Restarting...", _SERVICE_NAME],
            lambda: _restart_systemd_service(log_debug=log_debug),
        )
        if restart_result.returncode != 0:
            _log_debug(log_debug, f"Service restart failed with return code {restart_result.returncode}")
            display.render_paginated_lines(
                title,
                ["Restart failed"]
                + _format_command_output(restart_result.stdout, restart_result.stderr),
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


def _is_git_repo(repo_root: Path) -> bool:
    return repo_root.is_dir() and (repo_root / ".git").exists()


def _has_dirty_working_tree(repo_root: Path, *, log_debug: Optional[Callable[[str], None]]) -> bool:
    status = _run_command(["git", "status", "--porcelain"], cwd=repo_root, log_debug=log_debug)
    dirty = bool(status.stdout.strip())
    _log_debug(log_debug, f"Dirty working tree: {dirty}")
    return dirty


def _run_git_pull(
    repo_root: Path, *, log_debug: Optional[Callable[[str], None]]
) -> subprocess.CompletedProcess[str]:
    return _run_command(["git", "pull"], cwd=repo_root, log_debug=log_debug)


def _get_update_status(repo_root: Path, *, log_debug: Optional[Callable[[str], None]]) -> str:
    if not _is_git_repo(repo_root):
        _log_debug(log_debug, "Update status check: repo not found")
        return "Repo not found"
    fetch = _run_command(["git", "fetch", "--quiet"], cwd=repo_root, log_debug=log_debug)
    if fetch.returncode != 0:
        _log_debug(log_debug, f"Update status check: fetch failed {fetch.returncode}")
        return "Unable to check"
    upstream = _run_command(
        ["git", "rev-parse", "--abbrev-ref", "@{u}"],
        cwd=repo_root,
        log_debug=log_debug,
    )
    upstream_ref = upstream.stdout.strip()
    if upstream.returncode != 0 or not upstream_ref:
        _log_debug(log_debug, "Update status check: upstream missing")
        return "No upstream configured"
    behind = _run_command(
        ["git", "rev-list", "--count", "HEAD..@{u}"],
        cwd=repo_root,
        log_debug=log_debug,
    )
    if behind.returncode != 0:
        _log_debug(log_debug, "Update status check: rev-list failed")
        return "Unable to check"
    count = behind.stdout.strip()
    _log_debug(log_debug, f"Update status check: behind count={count!r}")
    return "Update available" if count.isdigit() and int(count) > 0 else "Up to date"


def _check_update_status(
    repo_root: Path, *, log_debug: Optional[Callable[[str], None]]
) -> tuple[str, str]:
    status = _get_update_status(repo_root, log_debug=log_debug)
    last_checked = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    _log_debug(log_debug, f"Update status check complete at {last_checked}: {status}")
    return status, last_checked


def _build_update_info_lines(version: str, status: str, last_checked: str | None) -> list[str]:
    return [f"Version: {version}", f"Status: {status}"]


def _get_update_menu_top(
    title: str,
    info_lines: list[str],
    *,
    title_icon: Optional[str] = None,
) -> int:
    context = display.get_display_context()
    items_font = context.fontdisks
    left_margin = context.x - 11
    available_width = max(0, context.width - left_margin)
    wrapped_lines = display._wrap_lines_to_width(info_lines, items_font, available_width)
    line_height = display._get_line_height(items_font)
    line_step = line_height + 2
    base_top = menus.get_standard_content_top(title, title_icon=title_icon)
    return base_top + (line_step * len(wrapped_lines)) + line_step


def _format_command_output(stdout: str, stderr: str) -> list[str]:
    lines: list[str] = []
    for chunk in [stdout, stderr]:
        if not chunk:
            continue
        for line in chunk.splitlines():
            cleaned = line.strip()
            if cleaned:
                lines.append(cleaned)
    return lines or ["No output"]


def _is_dubious_ownership_error(stderr: str) -> bool:
    return "detected dubious ownership" in stderr.lower()


def _is_running_under_systemd(*, log_debug: Optional[Callable[[str], None]]) -> bool:
    invocation_id = os.environ.get("INVOCATION_ID")
    _log_debug(log_debug, f"Systemd detection: INVOCATION_ID={invocation_id!r}")
    if invocation_id:
        _log_debug(log_debug, "Systemd detection: running under systemd via INVOCATION_ID")
        return True
    if Path("/proc/1/comm").exists():
        comm = Path("/proc/1/comm").read_text(encoding="utf-8").strip()
        _log_debug(log_debug, f"Systemd detection: /proc/1/comm={comm!r}")
        if comm != "systemd":
            _log_debug(log_debug, "Systemd detection: init is not systemd")
            return False
    else:
        _log_debug(log_debug, "Systemd detection: /proc/1/comm missing")
    if not shutil.which("systemctl"):
        _log_debug(log_debug, "Systemd detection: systemctl not found")
        return False
    show = _run_command(
        ["systemctl", "show", _SERVICE_NAME, "--property=ActiveState", "--value"],
        log_debug=log_debug,
    )
    if show.returncode == 0 and show.stdout.strip():
        active_state = show.stdout.strip()
        is_active = active_state in {"active", "activating", "reloading"}
        _log_debug(log_debug, f"Systemd detection: ActiveState={active_state!r} active={is_active}")
        return is_active
    _log_debug(log_debug, "Systemd detection: systemctl show returned no active state")
    return False


def _restart_systemd_service(
    *, log_debug: Optional[Callable[[str], None]]
) -> subprocess.CompletedProcess[str]:
    return _restart_service(log_debug=log_debug)


def _stop_systemd_service(
    *, log_debug: Optional[Callable[[str], None]]
) -> subprocess.CompletedProcess[str]:
    return _stop_service(log_debug=log_debug)


def _confirm_power_action(
    title: str,
    action_label: str,
    *,
    log_debug: Optional[Callable[[str], None]],
) -> bool:
    prompt = f"Are you sure you want to {action_label.lower()}?"
    confirmed = _confirm_action(title, prompt, log_debug=log_debug)
    _log_debug(log_debug, f"Power action confirmation {action_label}: confirmed={confirmed}")
    return confirmed


def _confirm_action(
    title: str,
    prompt: str,
    *,
    log_debug: Optional[Callable[[str], None]],
) -> bool:
    selection = app_state.CONFIRM_NO
    screens.render_confirmation_screen(title, [prompt], selected_index=selection)
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
                _log_debug(log_debug, f"Confirmation selection changed: {selection}")
        current_l = gpio.read_button(gpio.PIN_L)
        if prev_states["L"] and not current_l:
            if selection == app_state.CONFIRM_YES:
                selection = app_state.CONFIRM_NO
                _log_debug(log_debug, f"Confirmation selection changed: {selection}")
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
        screens.render_confirmation_screen(title, [prompt], selected_index=selection)
        time.sleep(menus.BUTTON_POLL_DELAY)


def _run_systemctl_command(
    args: list[str], *, log_debug: Optional[Callable[[str], None]]
) -> subprocess.CompletedProcess[str]:
    if not shutil.which("systemctl"):
        _log_debug(log_debug, f"systemctl command failed: {' '.join(args)} (systemctl missing)")
        return subprocess.CompletedProcess(
            args=["systemctl"], returncode=1, stdout="", stderr="systemctl missing"
        )
    return _run_command(["systemctl", *args], log_debug=log_debug)


def _restart_service(*, log_debug: Optional[Callable[[str], None]]) -> subprocess.CompletedProcess[str]:
    return _run_systemctl_command(["restart", _SERVICE_NAME], log_debug=log_debug)


def _stop_service(*, log_debug: Optional[Callable[[str], None]]) -> subprocess.CompletedProcess[str]:
    return _run_systemctl_command(["stop", _SERVICE_NAME], log_debug=log_debug)


def _reboot_system(*, log_debug: Optional[Callable[[str], None]]) -> subprocess.CompletedProcess[str]:
    return _run_systemctl_command(["reboot"], log_debug=log_debug)


def _poweroff_system(*, log_debug: Optional[Callable[[str], None]]) -> subprocess.CompletedProcess[str]:
    return _run_systemctl_command(["poweroff"], log_debug=log_debug)


def _get_git_version(
    repo_root: Path, *, log_debug: Optional[Callable[[str], None]]
) -> str | None:
    describe = _run_command(
        ["git", "-C", str(repo_root), "describe", "--tags", "--always", "--dirty"],
        log_debug=log_debug,
    )
    if describe.returncode == 0:
        value = describe.stdout.strip()
        if value:
            return value
    rev_parse = _run_command(
        ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
        log_debug=log_debug,
    )
    if rev_parse.returncode == 0:
        value = rev_parse.stdout.strip()
        if value:
            return value
    return None


def _run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    log_debug: Optional[Callable[[str], None]] = None,
) -> subprocess.CompletedProcess[str]:
    cwd_display = str(cwd) if cwd else None
    _log_debug(log_debug, f"Running command: {args} cwd={cwd_display}")
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    _log_debug(log_debug, f"Command return code: {result.returncode}")
    _log_debug(log_debug, f"Command stdout: {result.stdout.strip()!r}")
    _log_debug(log_debug, f"Command stderr: {result.stderr.strip()!r}")
    return result


def _log_debug(log_debug: Optional[Callable[[str], None]], message: str) -> None:
    if log_debug:
        log_debug(message)


def _get_app_version(*, log_debug: Optional[Callable[[str], None]] = None) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    _log_debug(log_debug, f"Repo root detection (version): {repo_root}")
    version = _get_git_version(repo_root, log_debug=log_debug)
    if version:
        return version
    version_file = repo_root / "VERSION"
    if version_file.exists():
        value = version_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    return "unknown"
