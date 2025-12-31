import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from rpi_usb_cloner.ui import display, menus, screens


_SERVICE_NAME = "rpi-usb-cloner.service"


def coming_soon() -> None:
    screens.show_coming_soon(title="SETTINGS")


def wifi_settings() -> None:
    screens.show_wifi_settings(title="WIFI")


def update_version(*, log_debug: Optional[Callable[[str], None]] = None) -> None:
    title = "UPDATE"
    repo_root = Path(__file__).resolve().parents[2]
    status, last_checked = _check_update_status(repo_root, log_debug=log_debug)
    version = _get_app_version(log_debug=log_debug)
    while True:
        version_lines = _build_update_info_lines(version, status, last_checked)
        content_top = _get_update_menu_top(title, version_lines)
        selection = menus.select_list(
            title,
            ["CHECK FOR UPDATES", "UPDATE"],
            content_top=content_top,
            header_lines=version_lines,
        )
        if selection is None:
            return
        if selection == 0:
            checking_lines = _build_update_info_lines(version, "Checking...", last_checked)
            display.render_paginated_lines(title, checking_lines, page_index=0)
            status, last_checked = _check_update_status(repo_root, log_debug=log_debug)
            version = _get_app_version(log_debug=log_debug)
            continue
        if selection == 1:
            _run_update_flow(title, log_debug=log_debug)
            status, last_checked = _check_update_status(repo_root, log_debug=log_debug)
            version = _get_app_version(log_debug=log_debug)
            continue


def restart_service(*, log_debug: Optional[Callable[[str], None]] = None) -> None:
    title = "POWER"
    screens.render_status_screen(title, "Restarting...", progress_line=_SERVICE_NAME)
    display.clear_display()
    restart_result = _restart_systemd_service(log_debug=log_debug)
    if restart_result.returncode != 0:
        _log_debug(log_debug, f"Service restart failed with return code {restart_result.returncode}")
        display.render_paginated_lines(
            title,
            ["Service restart failed"]
            + _format_command_output(restart_result.stdout, restart_result.stderr),
            page_index=0,
        )
        time.sleep(2)
        return
    display.clear_display()
    sys.exit(0)


def stop_service(*, log_debug: Optional[Callable[[str], None]] = None) -> None:
    title = "POWER"
    screens.render_status_screen(title, "Stopping...", progress_line=_SERVICE_NAME)
    display.clear_display()
    stop_result = _stop_systemd_service(log_debug=log_debug)
    if stop_result.returncode != 0:
        _log_debug(log_debug, f"Service stop failed with return code {stop_result.returncode}")
        display.render_paginated_lines(
            title,
            ["Service stop failed"] + _format_command_output(stop_result.stdout, stop_result.stderr),
            page_index=0,
        )
        time.sleep(2)
        return
    display.clear_display()
    sys.exit(0)


def restart_system(*, log_debug: Optional[Callable[[str], None]] = None) -> None:
    title = "POWER"
    if not _confirm_power_action(title, "RESTART SYSTEM", log_debug=log_debug):
        return
    screens.render_status_screen(title, "Restarting...", progress_line="System reboot")
    display.clear_display()
    reboot_result = _reboot_system(log_debug=log_debug)
    if reboot_result.returncode != 0:
        _log_debug(log_debug, f"System reboot failed with return code {reboot_result.returncode}")
        display.render_paginated_lines(
            title,
            ["System reboot failed"] + _format_command_output(reboot_result.stdout, reboot_result.stderr),
            page_index=0,
        )
        time.sleep(2)


def shutdown_system(*, log_debug: Optional[Callable[[str], None]] = None) -> None:
    title = "POWER"
    if not _confirm_power_action(title, "SHUTDOWN SYSTEM", log_debug=log_debug):
        return
    screens.render_status_screen(title, "Shutting down...", progress_line="System poweroff")
    display.clear_display()
    shutdown_result = _poweroff_system(log_debug=log_debug)
    if shutdown_result.returncode != 0:
        _log_debug(log_debug, f"System poweroff failed with return code {shutdown_result.returncode}")
        display.render_paginated_lines(
            title,
            ["System poweroff failed"]
            + _format_command_output(shutdown_result.stdout, shutdown_result.stderr),
            page_index=0,
        )
        time.sleep(2)


def _run_update_flow(title: str, *, log_debug: Optional[Callable[[str], None]]) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _log_debug(log_debug, f"Repo root detection: {repo_root}")
    is_repo = _is_git_repo(repo_root)
    _log_debug(log_debug, f"Repo root is git repo: {is_repo}")
    if not is_repo:
        _log_debug(log_debug, "Update aborted: repo not found")
        display.display_lines(["UPDATE", "Repo not found"])
        time.sleep(2)
        return
    if _has_dirty_working_tree(repo_root, log_debug=log_debug):
        _log_debug(log_debug, "Dirty working tree detected")
        display.render_paginated_lines(
            title,
            ["Uncommitted", "changes found"],
            page_index=0,
        )
        selection = menus.select_list(title, ["CANCEL", "CONTINUE"])
        if selection is None or selection == 0:
            _log_debug(log_debug, "Update canceled due to dirty tree")
            return
    screens.render_status_screen(title, "Updating...", progress_line="Pulling...")
    pull_result = _run_git_pull(repo_root, log_debug=log_debug)
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
        pull_result = _run_git_pull(repo_root, log_debug=log_debug)
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
        )
        time.sleep(2)
        return
    display.render_paginated_lines(
        title,
        ["Update complete"] + output_lines,
        page_index=0,
    )
    time.sleep(1)
    if _is_running_under_systemd(log_debug=log_debug):
        screens.render_status_screen(title, "Restarting...", progress_line=_SERVICE_NAME)
        restart_result = _restart_systemd_service(log_debug=log_debug)
        if restart_result.returncode != 0:
            _log_debug(log_debug, f"Service restart failed with return code {restart_result.returncode}")
            display.render_paginated_lines(
                title,
                ["Restart failed"]
                + _format_command_output(restart_result.stdout, restart_result.stderr),
                page_index=0,
            )
            time.sleep(2)
            return
        sys.exit(0)
    display.render_paginated_lines(
        title,
        ["Restart needed", "Please restart"],
        page_index=0,
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


def _get_update_menu_top(title: str, info_lines: list[str]) -> int:
    context = display.get_display_context()
    items_font = context.fontdisks
    left_margin = context.x - 11
    available_width = max(0, context.width - left_margin)
    wrapped_lines = display._wrap_lines_to_width(info_lines, items_font, available_width)
    line_height = display._get_line_height(items_font)
    line_step = line_height + 2
    base_top = menus.get_standard_content_top(title)
    return base_top + (line_step * len(wrapped_lines)) + 2


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
    selection = menus.select_list(title, ["CANCEL", action_label], header_lines=["Are you sure?"])
    _log_debug(log_debug, f"Power action confirmation {action_label}: selection={selection}")
    return selection == 1


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
