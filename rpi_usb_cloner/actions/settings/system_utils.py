"""System utility functions for settings operations."""
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence


_SERVICE_NAME = "rpi-usb-cloner.service"
_GIT_PROGRESS_STAGES = {
    "Receiving objects": 0,
    "Resolving deltas": 1,
    "Updating files": 2,
}


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    log_debug: Optional[Callable[[str], None]] = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and capture output."""
    cwd_display = str(cwd) if cwd else None
    log_debug_msg(log_debug, f"Running command: {args} cwd={cwd_display}")
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    log_debug_msg(log_debug, f"Command return code: {result.returncode}")
    log_debug_msg(log_debug, f"Command stdout: {result.stdout.strip()!r}")
    log_debug_msg(log_debug, f"Command stderr: {result.stderr.strip()!r}")
    return result


def log_debug_msg(
    log_debug: Optional[Callable[..., None]],
    message: str,
    *,
    tags: Optional[Sequence[str]] = None,
    timestamp: Optional[datetime] = None,
    level: str = "debug",
    source: Optional[str] = None,
) -> None:
    """Log a debug message if logger is provided."""
    if log_debug:
        entry_tags = list(tags) if tags else ["settings", "system"]
        log_debug(
            message,
            level=level,
            tags=entry_tags,
            timestamp=timestamp or datetime.now(),
            source=source,
        )


def get_git_version(
    repo_root: Path, *, log_debug: Optional[Callable[[str], None]]
) -> str | None:
    """Get git version string from repository."""
    describe = run_command(
        ["git", "-C", str(repo_root), "describe", "--tags", "--always", "--dirty"],
        log_debug=log_debug,
    )
    if describe.returncode == 0:
        value = describe.stdout.strip()
        if value:
            return value
    rev_parse = run_command(
        ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
        log_debug=log_debug,
    )
    if rev_parse.returncode == 0:
        value = rev_parse.stdout.strip()
        if value:
            return value
    return None


def get_app_version(*, log_debug: Optional[Callable[[str], None]] = None) -> str:
    """Get application version from git or VERSION file."""
    repo_root = Path(__file__).resolve().parents[3]
    log_debug_msg(log_debug, f"Repo root detection (version): {repo_root}")
    version = get_git_version(repo_root, log_debug=log_debug)
    if version:
        return version
    version_file = repo_root / "VERSION"
    if version_file.exists():
        value = version_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    return "unknown"


def is_git_repo(repo_root: Path) -> bool:
    """Check if directory is a git repository."""
    return repo_root.is_dir() and (repo_root / ".git").exists()


def has_dirty_working_tree(repo_root: Path, *, log_debug: Optional[Callable[[str], None]]) -> bool:
    """Check if git working tree has uncommitted changes."""
    status = run_command(["git", "status", "--porcelain"], cwd=repo_root, log_debug=log_debug)
    dirty = bool(status.stdout.strip())
    log_debug_msg(log_debug, f"Dirty working tree: {dirty}")
    return dirty


def is_dubious_ownership_error(stderr: str) -> bool:
    """Check if stderr contains git dubious ownership error."""
    return "detected dubious ownership" in stderr.lower()


def is_running_under_systemd(*, log_debug: Optional[Callable[[str], None]]) -> bool:
    """Detect if running under systemd."""
    invocation_id = os.environ.get("INVOCATION_ID")
    log_debug_msg(log_debug, f"Systemd detection: INVOCATION_ID={invocation_id!r}")
    if invocation_id:
        log_debug_msg(log_debug, "Systemd detection: running under systemd via INVOCATION_ID")
        return True
    if Path("/proc/1/comm").exists():
        comm = Path("/proc/1/comm").read_text(encoding="utf-8").strip()
        log_debug_msg(log_debug, f"Systemd detection: /proc/1/comm={comm!r}")
        if comm != "systemd":
            log_debug_msg(log_debug, "Systemd detection: init is not systemd")
            return False
    else:
        log_debug_msg(log_debug, "Systemd detection: /proc/1/comm missing")
    if not shutil.which("systemctl"):
        log_debug_msg(log_debug, "Systemd detection: systemctl not found")
        return False
    show = run_command(
        ["systemctl", "show", _SERVICE_NAME, "--property=ActiveState", "--value"],
        log_debug=log_debug,
    )
    if show.returncode == 0 and show.stdout.strip():
        active_state = show.stdout.strip()
        is_active = active_state in {"active", "activating", "reloading"}
        log_debug_msg(log_debug, f"Systemd detection: ActiveState={active_state!r} active={is_active}")
        return is_active
    log_debug_msg(log_debug, "Systemd detection: systemctl show returned no active state")
    return False


def run_systemctl_command(
    args: list[str], *, log_debug: Optional[Callable[[str], None]]
) -> subprocess.CompletedProcess[str]:
    """Run systemctl command."""
    if not shutil.which("systemctl"):
        log_debug_msg(log_debug, f"systemctl command failed: {' '.join(args)} (systemctl missing)")
        return subprocess.CompletedProcess(
            args=["systemctl"], returncode=1, stdout="", stderr="systemctl missing"
        )
    return run_command(["systemctl", *args], log_debug=log_debug)


def restart_service(*, log_debug: Optional[Callable[[str], None]]) -> subprocess.CompletedProcess[str]:
    """Restart the service."""
    return run_systemctl_command(["restart", _SERVICE_NAME], log_debug=log_debug)


def stop_service(*, log_debug: Optional[Callable[[str], None]]) -> subprocess.CompletedProcess[str]:
    """Stop the service."""
    return run_systemctl_command(["stop", _SERVICE_NAME], log_debug=log_debug)


def reboot_system(*, log_debug: Optional[Callable[[str], None]]) -> subprocess.CompletedProcess[str]:
    """Reboot the system."""
    return run_systemctl_command(["reboot"], log_debug=log_debug)


def poweroff_system(*, log_debug: Optional[Callable[[str], None]]) -> subprocess.CompletedProcess[str]:
    """Power off the system."""
    return run_systemctl_command(["poweroff"], log_debug=log_debug)


def format_command_output(stdout: str, stderr: str) -> list[str]:
    """Format command output for display."""
    lines: list[str] = []
    for chunk in [stdout, stderr]:
        if not chunk:
            continue
        for line in chunk.splitlines():
            cleaned = line.strip()
            if cleaned:
                lines.append(cleaned)
    return lines or ["No output"]


def parse_git_progress_ratio(line: str) -> float | None:
    """Parse git progress percentage from stderr line."""
    match = re.search(
        r"^(Receiving objects|Resolving deltas|Updating files):\s+(\d+)%", line
    )
    if not match:
        return None
    stage, percent_text = match.groups()
    if not percent_text.isdigit():
        return None
    percent = int(percent_text)
    total_stages = len(_GIT_PROGRESS_STAGES)
    stage_index = _GIT_PROGRESS_STAGES[stage]
    return (stage_index + percent / 100.0) / total_stages


def run_git_pull(
    repo_root: Path,
    *,
    log_debug: Optional[Callable[[str], None]],
    progress_callback: Optional[Callable[[float], None]] = None,
) -> subprocess.CompletedProcess[str]:
    """Run git pull with optional progress monitoring."""
    if progress_callback is None:
        return run_command(["git", "pull"], cwd=repo_root, log_debug=log_debug)
    process = subprocess.Popen(
        ["git", "pull", "--progress"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def read_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            stdout_lines.append(line)

    def read_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            stderr_lines.append(line)
            ratio = parse_git_progress_ratio(line)
            if ratio is not None:
                progress_callback(ratio)

    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    return_code = process.wait()
    stdout_thread.join()
    stderr_thread.join()
    return subprocess.CompletedProcess(
        process.args,
        return_code,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )
