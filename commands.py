import re
import select
import subprocess
import time

_log_debug = lambda message: None
_display_lines = lambda lines: None
_human_size = lambda value: str(value)


def configure_commands(*, log_debug=None, display_lines=None, human_size=None):
    global _log_debug, _display_lines, _human_size
    if log_debug is not None:
        _log_debug = log_debug
    if display_lines is not None:
        _display_lines = display_lines
    if human_size is not None:
        _human_size = human_size


def log_debug(message):
    _log_debug(message)


def display_lines(lines):
    _display_lines(lines)


def human_size(value):
    return _human_size(value)


def run_checked_command(command, input_text=None):
    log_debug(f"Running command: {' '.join(command)}")
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        message = stderr or stdout or "Command failed"
        raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")
    return result.stdout


def format_eta(seconds):
    if seconds is None:
        return None
    seconds = int(seconds)
    if seconds < 0:
        return None
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_progress_display(title, device, mode, bytes_copied, total_bytes, percent, rate, eta, spinner=None):
    lines = []
    if title:
        title_line = title
        if spinner:
            title_line = f"{title} {spinner}"
        lines.append(title_line)
    if device:
        lines.append(device)
    if mode:
        lines.append(f"Mode {mode}")
    if bytes_copied is not None:
        percent_display = ""
        if total_bytes:
            percent_display = f"{(bytes_copied / total_bytes) * 100:.1f}%"
        elif percent is not None:
            percent_display = f"{percent:.1f}%"
        written_line = f"Wrote {human_size(bytes_copied)}"
        if percent_display:
            written_line = f"{written_line} {percent_display}"
        lines.append(written_line)
    elif percent is not None:
        lines.append(f"{percent:.1f}%")
    else:
        lines.append("Working...")
    if rate:
        rate_line = f"{human_size(rate)}/s"
        if eta:
            rate_line = f"{rate_line} ETA {eta}"
        lines.append(rate_line)
    return lines[:6]


def run_progress_command(command, total_bytes=None, title="WORKING", device_label=None, mode_label=None):
    display_lines(format_progress_display(title, device_label, mode_label, 0 if total_bytes else None, total_bytes, None, None, None))
    log_debug(f"Starting command: {' '.join(command)}")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
            log_debug(f"stderr: {line.strip()}")
            bytes_match = re.search(r"(\d+)\s+bytes", line)
            percent_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            rate_match = re.search(r"(\d+(?:\.\d+)?)\s*MiB/s", line)
            bytes_copied = last_bytes
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
                    eta_seconds = (total_bytes - bytes_copied) / rate if rate > 0 else None
                    eta = format_eta(eta_seconds)
                last_bytes = bytes_copied
                last_time = now
                last_rate = rate or last_rate
                last_eta = eta or last_eta
            if percent_match:
                last_percent = float(percent_match.group(1))
            rate_display = rate if rate is not None else last_rate
            eta_display = eta if eta is not None else last_eta
            display_lines(format_progress_display(
                title,
                device_label,
                mode_label,
                bytes_copied,
                total_bytes,
                last_percent,
                rate_display,
                eta_display,
                spinner_frames[spinner_index],
            ))
            last_update = now
        if now - last_update >= refresh_interval:
            spinner_index = (spinner_index + 1) % len(spinner_frames)
            display_lines(format_progress_display(
                title,
                device_label,
                mode_label,
                last_bytes,
                total_bytes,
                last_percent,
                last_rate,
                last_eta,
                spinner_frames[spinner_index],
            ))
            last_update = now
        if process.poll() is not None and not line:
            break
    if process.returncode != 0:
        error_output = process.stderr.read().strip()
        message = error_output.splitlines()[-1] if error_output else "Command failed"
        display_lines(["FAILED", message[:20]])
        log_debug(f"Command failed with code {process.returncode}: {message}")
        return False
    display_lines([title, "Complete"])
    log_debug("Command completed successfully")
    return True


def parse_progress(stderr_output, total_bytes=None, title="WORKING"):
    if not stderr_output:
        return
    for line in stderr_output.splitlines():
        log_debug(f"stderr: {line.strip()}")
        bytes_match = re.search(r"(\d+)\s+bytes", line)
        percent_match = re.search(r"(\d+(?:\.\d+)?)%", line)
        if bytes_match:
            bytes_copied = int(bytes_match.group(1))
            percent = ""
            if total_bytes:
                percent = f"{(bytes_copied / total_bytes) * 100:.1f}%"
            elif percent_match:
                percent = f"{percent_match.group(1)}%"
            display_lines([title, f"{human_size(bytes_copied)} {percent}".strip()])
            continue
        if percent_match and not total_bytes:
            display_lines([title, f"{percent_match.group(1)}%"])


def run_checked_with_progress(command, total_bytes=None, title="WORKING", stdout_target=None):
    display_lines([title, "Starting..."])
    log_debug(f"Running command: {' '.join(command)}")
    result = subprocess.run(
        command,
        stdout=stdout_target or subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    parse_progress(result.stderr, total_bytes=total_bytes, title=title)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip() if result.stdout else ""
        message = stderr or stdout or "Command failed"
        raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")
    display_lines([title, "Complete"])
    return result
