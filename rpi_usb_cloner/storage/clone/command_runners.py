"""Command execution utilities with progress tracking."""

import re
import select
import subprocess
import time

from rpi_usb_cloner.ui.display import display_lines

from .progress import (
    _log_debug,
    configure_progress_logger,
    format_eta,
    format_progress_display,
    parse_progress_from_output,
)


def run_checked_command(command, input_text=None):
    """Run a command and raise RuntimeError if it fails."""
    _log_debug(f"Running command: {' '.join(command)}")
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        message = stderr or stdout or "Command failed"
        raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")
    return result.stdout


def run_progress_command(
    command,
    total_bytes=None,
    title="WORKING",
    device_label=None,
    mode_label=None,
):
    """Run a command with real-time progress monitoring (legacy API)."""
    display_lines(
        format_progress_display(
            title,
            device_label,
            mode_label,
            0 if total_bytes else None,
            total_bytes,
            None,
            None,
            None,
        )
    )
    _log_debug(f"Starting command: {' '.join(command)}")
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    last_update = time.time()
    last_bytes = None
    last_time = None
    last_rate = None
    last_eta = None
    last_percent = None
    spinner_frames = ["|", "/", "-", "\\"]
    spinner_index = 0
    refresh_interval = 1.0
    while True:
        ready, _, _ = select.select([process.stderr], [], [], refresh_interval)
        now = time.time()
        line = None
        if ready:
            line = process.stderr.readline()
        if line:
            _log_debug(f"stderr: {line.strip()}")
            bytes_match = re.search(r"(\d+)\s+bytes", line)
            percent_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            rate_match = re.search(r"(\d+(?:\.\d+)?)\s*MiB/s", line)
            # Don't use stale bytes - prevents mixing old bytes with new percentage
            bytes_copied = None
            rate = last_rate
            eta = last_eta
            if bytes_match:
                bytes_copied = int(bytes_match.group(1))
                if rate_match:
                    rate = float(rate_match.group(1)) * 1024 * 1024
                else:
                    rate = None
                    if last_bytes is not None and last_time is not None:
                        delta_bytes = bytes_copied - last_bytes
                        delta_time = now - last_time
                        if delta_bytes >= 0 and delta_time > 0:
                            rate = delta_bytes / delta_time
                if rate and total_bytes and bytes_copied <= total_bytes:
                    eta_seconds = (
                        (total_bytes - bytes_copied) / rate if rate > 0 else None
                    )
                    eta = format_eta(eta_seconds)
                last_bytes = bytes_copied
                last_time = now
                last_rate = rate or last_rate
                last_eta = eta or last_eta
            if percent_match:
                last_percent = float(percent_match.group(1))
            rate_display = rate if rate is not None else last_rate
            eta_display = eta if eta is not None else last_eta
            display_lines(
                format_progress_display(
                    title,
                    device_label,
                    mode_label,
                    bytes_copied,
                    total_bytes,
                    last_percent,
                    rate_display,
                    eta_display,
                    spinner_frames[spinner_index],
                )
            )
            last_update = now
        if now - last_update >= refresh_interval:
            spinner_index = (spinner_index + 1) % len(spinner_frames)
            display_lines(
                format_progress_display(
                    title,
                    device_label,
                    mode_label,
                    last_bytes,
                    total_bytes,
                    last_percent,
                    last_rate,
                    last_eta,
                    spinner_frames[spinner_index],
                )
            )
            last_update = now
        if process.poll() is not None and not line:
            break
    if process.returncode != 0:
        error_output = process.stderr.read().strip()
        message = error_output.splitlines()[-1] if error_output else "Command failed"
        display_lines(["FAILED", message[:20]])
        _log_debug(f"Command failed with code {process.returncode}: {message}")
        return False
    display_lines([title, "Complete"])
    _log_debug("Command completed successfully")
    return True


def run_checked_with_progress(
    command,
    total_bytes=None,
    title="WORKING",
    stdout_target=None,
    stdin_source=None,
):
    """Run a command with progress parsing from stderr (legacy API)."""
    display_lines([title, "Starting..."])
    _log_debug(f"Running command: {' '.join(command)}")
    result = subprocess.run(
        command,
        stdin=stdin_source,
        stdout=stdout_target or subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    parse_progress_from_output(result.stderr, total_bytes=total_bytes, title=title)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip() if result.stdout else ""
        message = stderr or stdout or "Command failed"
        raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")
    display_lines([title, "Complete"])
    return result


def run_checked_with_streaming_progress(
    command,
    total_bytes=None,
    title="WORKING",
    stdout_target=None,
    stdin_source=None,
    progress_callback=None,
    subtitle=None,
):
    """Run a command with streaming progress monitoring and callback support."""

    def emit_progress(lines, ratio=None):
        if progress_callback:
            progress_callback(lines, ratio)
        else:
            display_lines(lines)

    def clamp_ratio(value):
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))

    def compute_ratio(bytes_copied, percent_value):
        if bytes_copied is not None and total_bytes:
            return clamp_ratio(bytes_copied / total_bytes)
        if percent_value is not None:
            return clamp_ratio(percent_value / 100.0)
        return None

    emit_progress(
        format_progress_display(
            title,
            None,
            None,
            0 if total_bytes else None,
            total_bytes,
            None,
            None,
            None,
            subtitle=subtitle,
        ),
        ratio=compute_ratio(0 if total_bytes else None, None),
    )
    _log_debug(f"Running command: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        stdin=stdin_source,
        stdout=stdout_target or subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr_lines = []
    last_update = time.time()
    last_bytes = None
    last_time = None
    last_rate = None
    last_eta = None
    last_percent = None
    spinner_frames = ["|", "/", "-", "\\"]
    spinner_index = 0
    refresh_interval = 1.0
    while True:
        ready, _, _ = select.select([process.stderr], [], [], refresh_interval)
        now = time.time()
        line = None
        if ready:
            line = process.stderr.readline()
        if line:
            stderr_lines.append(line)
            _log_debug(f"stderr: {line.strip()}")
            bytes_match = re.search(r"(\d+)\s+bytes", line)
            percent_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            rate_match = re.search(r"(\d+(?:\.\d+)?)\s*MiB/s", line)
            # Don't use stale bytes - prevents mixing old bytes with new percentage
            bytes_copied = None
            rate = last_rate
            eta = last_eta
            if bytes_match:
                bytes_copied = int(bytes_match.group(1))
                if rate_match:
                    rate = float(rate_match.group(1)) * 1024 * 1024
                else:
                    rate = None
                    if last_bytes is not None and last_time is not None:
                        delta_bytes = bytes_copied - last_bytes
                        delta_time = now - last_time
                        if delta_bytes >= 0 and delta_time > 0:
                            rate = delta_bytes / delta_time
                if rate and total_bytes and bytes_copied <= total_bytes:
                    eta_seconds = (
                        (total_bytes - bytes_copied) / rate if rate > 0 else None
                    )
                    eta = format_eta(eta_seconds)
                last_bytes = bytes_copied
                last_time = now
                last_rate = rate or last_rate
                last_eta = eta or last_eta
            if percent_match:
                last_percent = float(percent_match.group(1))
            rate_display = rate if rate is not None else last_rate
            eta_display = eta if eta is not None else last_eta
            emit_progress(
                format_progress_display(
                    title,
                    None,
                    None,
                    bytes_copied,
                    total_bytes,
                    last_percent,
                    rate_display,
                    eta_display,
                    spinner_frames[spinner_index],
                    subtitle=subtitle,
                ),
                ratio=compute_ratio(bytes_copied, last_percent),
            )
            last_update = now
        if now - last_update >= refresh_interval:
            spinner_index = (spinner_index + 1) % len(spinner_frames)
            emit_progress(
                format_progress_display(
                    title,
                    None,
                    None,
                    last_bytes,
                    total_bytes,
                    last_percent,
                    last_rate,
                    last_eta,
                    spinner_frames[spinner_index],
                    subtitle=subtitle,
                ),
                ratio=compute_ratio(last_bytes, last_percent),
            )
            last_update = now
        if process.poll() is not None and not line:
            break
    remaining_stderr = process.stderr.read() if process.stderr else ""
    if remaining_stderr:
        stderr_lines.append(remaining_stderr)
    stdout_data = ""
    if stdout_target is None and process.stdout:
        stdout_data = process.stdout.read()
    process.wait()
    stderr_output = "".join(stderr_lines)
    if process.returncode != 0:
        stderr = stderr_output.strip()
        stdout = stdout_data.strip()
        message = stderr or stdout or "Command failed"
        raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")
    emit_progress([title, "Complete"], ratio=1.0)
    return subprocess.CompletedProcess(
        command, process.returncode, stdout=stdout_data, stderr=stderr_output
    )


# Export configure function
__all__ = [
    "run_checked_command",
    "run_progress_command",
    "run_checked_with_progress",
    "run_checked_with_streaming_progress",
    "configure_progress_logger",
]
