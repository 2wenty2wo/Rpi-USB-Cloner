"""System utility functions for settings operations."""

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

from loguru import logger


_SERVICE_NAME = "rpi-usb-cloner.service"
_GIT_PROGRESS_STAGES = {
    "Receiving objects": 0,
    "Resolving deltas": 1,
    "Updating files": 2,
}



def _escape_braces(text: str) -> str:
    """Escape curly braces for loguru formatting."""
    return text.replace("{", "{{").replace("}", "}}")


def validate_command_args(args: list[str]) -> None:
    """Validate command arguments before executing."""
    if not args or not all(isinstance(arg, str) and arg for arg in args):
        raise ValueError("Command args must be a non-empty list of strings.")


def run_command(
    args: list[str],
    *,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and capture output."""
    validate_command_args(args)
    cwd_display = str(cwd) if cwd else None
    logger.debug(
        f"Running command: {_escape_braces(repr(args))} cwd={cwd_display}",
        component="system",
    )
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    logger.debug(f"Command return code: {result.returncode}", component="system")
    logger.debug(
        f"Command stdout: {_escape_braces(repr(result.stdout.strip()))}",
        component="system",
    )
    logger.debug(
        f"Command stderr: {_escape_braces(repr(result.stderr.strip()))}",
        component="system",
    )
    return result


def get_git_version(repo_root: Path) -> Optional[str]:
    """Get git version string from repository."""
    describe = run_command(
        ["git", "-C", str(repo_root), "describe", "--tags", "--always", "--dirty"]
    )
    if describe.returncode == 0:
        value = describe.stdout.strip()
        if value:
            return value
    rev_parse = run_command(
        ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"]
    )
    if rev_parse.returncode == 0:
        value = rev_parse.stdout.strip()
        if value:
            return value
    return None


def get_app_version() -> str:
    """Get application version from git or VERSION file."""
    repo_root = Path(__file__).resolve().parents[3]
    logger.debug(f"Repo root detection (version): {repo_root}", component="system")
    version = get_git_version(repo_root)
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


def has_dirty_working_tree(repo_root: Path) -> bool:
    """Check if git working tree has uncommitted changes."""
    status = run_command(["git", "status", "--porcelain"], cwd=repo_root)
    dirty = bool(status.stdout.strip())
    logger.debug(f"Dirty working tree: {dirty}", component="system")
    return dirty


def is_dubious_ownership_error(stderr: str) -> bool:
    """Check if stderr contains git dubious ownership error."""
    return "detected dubious ownership" in stderr.lower()


def is_running_under_systemd() -> bool:
    """Detect if running under systemd."""
    invocation_id = os.environ.get("INVOCATION_ID")
    logger.debug(f"Systemd detection: INVOCATION_ID={invocation_id!r}", component="system")
    if invocation_id:
        logger.debug(
            "Systemd detection: running under systemd via INVOCATION_ID",
            component="system",
        )
        return True
    if Path("/proc/1/comm").exists():
        comm = Path("/proc/1/comm").read_text(encoding="utf-8").strip()
        logger.debug(f"Systemd detection: /proc/1/comm={comm!r}", component="system")
        if comm != "systemd":
            logger.debug("Systemd detection: init is not systemd", component="system")
            return False
    else:
        logger.debug("Systemd detection: /proc/1/comm missing", component="system")
    if not shutil.which("systemctl"):
        logger.debug("Systemd detection: systemctl not found", component="system")
        return False
    show = run_command(
        ["systemctl", "show", _SERVICE_NAME, "--property=ActiveState", "--value"]
    )
    if show.returncode == 0 and show.stdout.strip():
        active_state = show.stdout.strip()
        is_active = active_state in {"active", "activating", "reloading"}
        logger.debug(
            f"Systemd detection: ActiveState={active_state!r} active={is_active}",
            component="system",
        )
        return is_active
    logger.debug(
        "Systemd detection: systemctl show returned no active state", component="system"
    )
    return False


def run_systemctl_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run systemctl command."""
    if not shutil.which("systemctl"):
        logger.debug(
            f"systemctl command failed: {' '.join(args)} (systemctl missing)",
            component="system",
        )
        return subprocess.CompletedProcess(
            args=["systemctl"], returncode=1, stdout="", stderr="systemctl missing"
        )
    return run_command(["systemctl", *args])


def restart_service() -> subprocess.CompletedProcess[str]:
    """Restart the service."""
    return run_systemctl_command(["restart", _SERVICE_NAME])


def stop_service() -> subprocess.CompletedProcess[str]:
    """Stop the service."""
    return run_systemctl_command(["stop", _SERVICE_NAME])


def reboot_system() -> subprocess.CompletedProcess[str]:
    """Reboot the system."""
    return run_systemctl_command(["reboot"])


def poweroff_system() -> subprocess.CompletedProcess[str]:
    """Power off the system."""
    return run_systemctl_command(["poweroff"])


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


def parse_git_progress_ratio(line: str) -> Optional[float]:
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
    progress_callback: Optional[Callable[[float], None]] = None,
) -> subprocess.CompletedProcess[str]:
    """Run git pull with optional progress monitoring."""
    if progress_callback is None:
        return run_command(["git", "pull"], cwd=repo_root)
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
