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
    title = "UPDATE / VERSION"
    version = _get_app_version()
    version_lines = [f"Version: {version}"]
    display.render_paginated_lines(title, version_lines, page_index=0)
    while True:
        selection = menus.select_list(title, ["UPDATE", "BACK"])
        if selection is None or selection == 1:
            return
        if selection == 0:
            _run_update_flow(title, log_debug=log_debug)
            version = _get_app_version()
            version_lines = [f"Version: {version}"]
            display.render_paginated_lines(title, version_lines, page_index=0)


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
    output_lines = _format_command_output(pull_result.stdout, pull_result.stderr)
    if pull_result.returncode != 0:
        _log_debug(log_debug, f"Git pull failed with return code {pull_result.returncode}")
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
    if not shutil.which("systemctl"):
        _log_debug(log_debug, "Service restart failed: systemctl missing")
        return subprocess.CompletedProcess(
            args=["systemctl"], returncode=1, stdout="", stderr="systemctl missing"
        )
    return _run_command(
        ["systemctl", "restart", _SERVICE_NAME],
        log_debug=log_debug,
    )


def _get_git_version(repo_root: Path) -> str | None:
    describe = _run_command(["git", "-C", str(repo_root), "describe", "--tags", "--always", "--dirty"])
    if describe.returncode == 0:
        value = describe.stdout.strip()
        if value:
            return value
    rev_parse = _run_command(["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"])
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


def _get_app_version() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    version = _get_git_version(repo_root)
    if version:
        return version
    version_file = repo_root / "VERSION"
    if version_file.exists():
        value = version_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    return "unknown"
