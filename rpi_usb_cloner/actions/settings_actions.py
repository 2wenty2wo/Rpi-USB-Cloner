import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rpi_usb_cloner.ui import display, menus, screens


_SERVICE_NAME = "rpi-usb-cloner.service"


def coming_soon() -> None:
    screens.show_coming_soon(title="SETTINGS")


def wifi_settings() -> None:
    screens.show_wifi_settings(title="WIFI")


def update_version() -> None:
    title = "UPDATE / VERSION"
    version = _get_app_version()
    version_lines = [f"Version: {version}"]
    display.render_paginated_lines(title, version_lines, page_index=0)
    while True:
        selection = menus.select_list(title, ["UPDATE", "BACK"])
        if selection is None or selection == 1:
            return
        if selection == 0:
            _run_update_flow(title)
            version = _get_app_version()
            version_lines = [f"Version: {version}"]
            display.render_paginated_lines(title, version_lines, page_index=0)


def _run_update_flow(title: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    if not _is_git_repo(repo_root):
        display.display_lines(["UPDATE", "Repo not found"])
        time.sleep(2)
        return
    if _has_dirty_working_tree(repo_root):
        display.render_paginated_lines(
            title,
            ["Uncommitted", "changes found"],
            page_index=0,
        )
        selection = menus.select_list(title, ["CANCEL", "CONTINUE"])
        if selection is None or selection == 0:
            return
    screens.render_status_screen(title, "Updating...", progress_line="Pulling...")
    pull_result = _run_git_pull(repo_root)
    output_lines = _format_command_output(pull_result.stdout, pull_result.stderr)
    if pull_result.returncode != 0:
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
    if _is_running_under_systemd():
        screens.render_status_screen(title, "Restarting...", progress_line=_SERVICE_NAME)
        restart_result = _restart_systemd_service()
        if restart_result.returncode != 0:
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


def _has_dirty_working_tree(repo_root: Path) -> bool:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(status.stdout.strip())


def _run_git_pull(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "pull"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


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


def _is_running_under_systemd() -> bool:
    if os.environ.get("INVOCATION_ID"):
        return True
    if Path("/proc/1/comm").exists():
        comm = Path("/proc/1/comm").read_text(encoding="utf-8").strip()
        if comm != "systemd":
            return False
    if not shutil.which("systemctl"):
        return False
    show = subprocess.run(
        ["systemctl", "show", _SERVICE_NAME, "--property=ActiveState", "--value"],
        capture_output=True,
        text=True,
        check=False,
    )
    if show.returncode == 0 and show.stdout.strip():
        return show.stdout.strip() in {"active", "activating", "reloading"}
    return False


def _restart_systemd_service() -> subprocess.CompletedProcess[str]:
    if not shutil.which("systemctl"):
        return subprocess.CompletedProcess(args=["systemctl"], returncode=1, stdout="", stderr="systemctl missing")
    return subprocess.run(
        ["systemctl", "restart", _SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )


def _get_git_version(repo_root: Path) -> str | None:
    describe = subprocess.run(
        ["git", "-C", str(repo_root), "describe", "--tags", "--always", "--dirty"],
        capture_output=True,
        text=True,
        check=False,
    )
    if describe.returncode == 0:
        value = describe.stdout.strip()
        if value:
            return value
    rev_parse = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if rev_parse.returncode == 0:
        value = rev_parse.stdout.strip()
        if value:
            return value
    return None


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
