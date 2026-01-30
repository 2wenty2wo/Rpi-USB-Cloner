"""Progress monitoring and formatting for clone operations."""

import re

from loguru import logger

from rpi_usb_cloner.storage.devices import human_size


def format_eta(seconds):
    """Format ETA in HH:MM:SS or MM:SS format."""
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


def format_progress_lines(title, device, mode, bytes_copied, total_bytes, rate, eta):
    """Format progress information into display lines (legacy format)."""
    lines = []
    if title:
        lines.append(title)
    if device:
        lines.append(device)
    if mode:
        lines.append(f"Mode {mode}")
    if bytes_copied is not None:
        percent = ""
        if total_bytes:
            percent = f"{(bytes_copied / total_bytes) * 100:.1f}%"
        written_line = f"Wrote {human_size(bytes_copied)}"
        if percent:
            written_line = f"{written_line} {percent}"
        lines.append(written_line)
    else:
        lines.append("Working...")
    if rate:
        rate_line = f"{human_size(rate)}/s"
        if eta:
            rate_line = f"{rate_line} ETA {eta}"
        lines.append(rate_line)
    return lines[:6]


def format_progress_display(
    title,
    device,
    mode,
    bytes_copied,
    total_bytes,
    percent,
    rate,
    eta,
    spinner=None,
    subtitle=None,
):
    """Format progress information into display lines with modern features."""
    lines = []
    if title:
        title_line = title
        if spinner:
            title_line = f"{title} {spinner}"
        lines.append(title_line)
    if subtitle:
        lines.append(subtitle)
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
    else:
        # Don't show standalone percentage - it's now displayed in the progress bar
        lines.append("Working...")
    if rate:
        rate_line = f"{human_size(rate)}/s"
        if eta:
            rate_line = f"{rate_line} ETA {eta}"
        lines.append(rate_line)
    return lines[:6]


def parse_progress_from_output(stderr_output, total_bytes=None, title="WORKING"):
    """Parse progress information from command stderr output."""
    from rpi_usb_cloner.ui.display import display_lines

    if not stderr_output:
        return
    for line in stderr_output.splitlines():
        logger.debug(f"stderr: {line.strip()}")
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
