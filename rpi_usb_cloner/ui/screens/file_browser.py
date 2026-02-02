"""File browser screen for viewing files on USB drives and image repo."""

import time
from pathlib import Path
from typing import List, Optional, Tuple

from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.menu.model import get_screen_icon
from rpi_usb_cloner.storage import devices as storage_devices
from rpi_usb_cloner.storage.image_repo import find_image_repos
from rpi_usb_cloner.ui import display, menus
from rpi_usb_cloner.ui.icons import FILE_ICON, FOLDER_ICON


class FileItem:
    """Represents a file or directory in the browser."""

    def __init__(
        self, path: Path, is_dir: bool = False, display_name: Optional[str] = None
    ):
        self.path = path
        self.is_dir = is_dir
        self.display_name = display_name or path.name

    def __str__(self) -> str:
        if self.is_dir:
            return f"{FOLDER_ICON} {self.display_name}"
        return f"{FILE_ICON} {self.display_name}"


def _get_line_height(font, min_height=8):
    """Calculate line height for a given font."""
    line_height = min_height
    try:
        bbox = font.getbbox("Ag")
        if isinstance(bbox, tuple) and len(bbox) >= 4:
            line_height = max(bbox[3] - bbox[1], line_height)
        else:
            raise TypeError("Invalid bbox")
    except (AttributeError, TypeError, ValueError):
        if hasattr(font, "getmetrics"):
            try:
                ascent, descent = font.getmetrics()
                if isinstance(ascent, (int, float)) and isinstance(
                    descent, (int, float)
                ):
                    line_height = max(ascent + descent, line_height)
            except (AttributeError, TypeError, ValueError):
                pass
    return line_height


def _get_usb_mountpoints() -> List[Path]:
    """Get all USB drive mountpoints."""
    mountpoints: List[Path] = []
    seen: set[Path] = set()

    for device in storage_devices.list_usb_disks():
        # Recursively find all partitions
        stack = [device]
        while stack:
            current = stack.pop()
            mountpoint = current.get("mountpoint")
            if mountpoint:
                mount_path = Path(mountpoint)
                if mount_path not in seen:
                    mountpoints.append(mount_path)
                    seen.add(mount_path)
            stack.extend(storage_devices.get_children(current))

    return sorted(mountpoints, key=lambda p: str(p))


def _get_available_locations() -> List[FileItem]:
    """Get list of available browsable locations (USB drives and image repos)."""
    locations: List[FileItem] = []

    # Add USB drive mountpoints
    usb_mounts = _get_usb_mountpoints()
    for mount in usb_mounts:
        # Get device name from path
        device_name = mount.name or str(mount)
        locations.append(
            FileItem(mount, is_dir=True, display_name=f"USB: {device_name}")
        )

    # Add image repo locations
    repos = find_image_repos()
    for repo in repos:
        repo_path = repo.path
        repo_name = repo_path.name or str(repo_path)
        locations.append(
            FileItem(repo_path, is_dir=True, display_name=f"REPO: {repo_name}")
        )

    return locations


def _list_directory(path: Path) -> List[FileItem]:
    """List contents of a directory, sorted with directories first."""
    try:
        items: List[FileItem] = []

        # Add parent directory link if not at root
        if path.parent != path:
            items.append(FileItem(path.parent, is_dir=True, display_name=".."))

        # List directory contents
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))

        for entry in entries:
            # Skip hidden files
            if entry.name.startswith("."):
                continue

            is_dir = entry.is_dir()
            items.append(FileItem(entry, is_dir=is_dir))

        return items
    except (PermissionError, OSError):
        # Return empty list if directory is not accessible
        return []


def _render_browser_screen(
    title: str,
    items: List[FileItem],
    selected_index: int,
    current_path: Optional[Path] = None,
    title_icon: Optional[str] = None,
) -> None:
    """Render the file browser screen with selectable items."""
    ctx = display.get_display_context()
    draw = ctx.draw
    fonts = ctx.fonts
    width = ctx.width
    height = ctx.height

    # Clear display
    draw.rectangle((0, 0, width, height), outline=0, fill=0)

    # Draw title with icon
    display.set_animated_icon(title_icon)
    layout = display.draw_title_with_icon(title, icon=title_icon)
    content_top = layout.content_top
    if not isinstance(content_top, int):
        content_top = 0

    # Calculate available space for items
    items_font = fonts.get("items")
    line_height = _get_line_height(items_font)
    available_height = height - content_top - 2
    max_visible_items = max(1, available_height // line_height)

    # Calculate scroll offset to keep selected item visible
    if len(items) <= max_visible_items:
        start_index = 0
    else:
        # Keep selected item in middle when possible
        start_index = max(
            0,
            min(
                selected_index - max_visible_items // 2, len(items) - max_visible_items
            ),
        )

    # Render visible items
    for i in range(max_visible_items):
        item_index = start_index + i
        if item_index >= len(items):
            break

        item = items[item_index]
        is_selected = item_index == selected_index

        y_pos = content_top + (i * line_height)

        # Draw selection indicator
        if is_selected:
            draw.text((2, y_pos), ">", font=items_font, fill=255)

        # Draw item text (with icon)
        item_text = str(item)
        # Truncate if too long (rough estimate for 128px width)
        max_chars = 18
        if len(item_text) > max_chars:
            item_text = item_text[: max_chars - 1] + "…"

        draw.text((12, y_pos), item_text, font=items_font, fill=255)

    # Show scroll indicator if needed
    if len(items) > max_visible_items:
        # Show which page we're on
        total_pages = (len(items) + max_visible_items - 1) // max_visible_items
        current_page = start_index // max_visible_items + 1
        indicator = f"{current_page}/{total_pages}"

        # Draw in bottom right corner
        indicator_font = fonts.get("footer")
        draw.text((width - 30, height - 12), indicator, font=indicator_font, fill=255)

    # Display the rendered screen
    ctx.disp.display(ctx.image)


def show_file_browser(app_context, *, title: str = "FILE BROWSER") -> None:
    """Show the file browser interface."""
    title_icon = get_screen_icon("file_browser")

    # Navigation state
    current_items: List[FileItem] = []
    selected_index = 0
    path_stack: List[Tuple[List[FileItem], int]] = (
        []
    )  # Stack of (items, selected_index)
    current_path: Optional[Path] = None

    # Load initial locations
    current_items = _get_available_locations()

    if not current_items:
        # No drives available
        display.display_lines([title, "No drives", "available"])
        time.sleep(2)
        return

    def render() -> None:
        _render_browser_screen(
            title,
            current_items,
            selected_index,
            current_path=current_path,
            title_icon=title_icon,
        )

    # Initial render
    render()

    # Wait for buttons to be released
    menus.wait_for_buttons_release(
        [gpio.PIN_A, gpio.PIN_B, gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D]
    )

    prev_states = {
        "A": gpio.is_pressed(gpio.PIN_A),
        "B": gpio.is_pressed(gpio.PIN_B),
        "L": gpio.is_pressed(gpio.PIN_L),
        "R": gpio.is_pressed(gpio.PIN_R),
        "U": gpio.is_pressed(gpio.PIN_U),
        "D": gpio.is_pressed(gpio.PIN_D),
    }

    while True:
        # Button A - Exit
        current_a = gpio.is_pressed(gpio.PIN_A)
        if not prev_states["A"] and current_a:
            return

        # Button B - Go back (same as left)
        current_b = gpio.is_pressed(gpio.PIN_B)
        if not prev_states["B"] and current_b and path_stack:
            # Pop from stack and restore previous state
            current_items, selected_index = path_stack.pop()
            if path_stack:
                # Update current_path to parent
                prev_item = path_stack[-1][0][0] if path_stack[-1][0] else None
                current_path = prev_item.path if prev_item else None
            else:
                current_path = None
            render()

        # Button UP - Move selection up
        current_u = gpio.is_pressed(gpio.PIN_U)
        if not prev_states["U"] and current_u and current_items:
            selected_index = (selected_index - 1) % len(current_items)
            render()

        # Button DOWN - Move selection down
        current_d = gpio.is_pressed(gpio.PIN_D)
        if not prev_states["D"] and current_d and current_items:
            selected_index = (selected_index + 1) % len(current_items)
            render()

        # Button LEFT - Go back to parent directory
        current_l = gpio.is_pressed(gpio.PIN_L)
        if not prev_states["L"] and current_l and path_stack:
            # Pop from stack and restore previous state
            current_items, selected_index = path_stack.pop()
            if path_stack:
                # Update current_path to parent
                prev_item = path_stack[-1][0][0] if path_stack[-1][0] else None
                current_path = prev_item.path if prev_item else None
            else:
                current_path = None
            render()

        # Button RIGHT - Enter directory or view file
        current_r = gpio.is_pressed(gpio.PIN_R)
        if (
            not prev_states["R"]
            and current_r
            and current_items
            and 0 <= selected_index < len(current_items)
        ):
            selected_item = current_items[selected_index]

            if selected_item.is_dir:
                # Save current state to stack
                path_stack.append((current_items, selected_index))

                # Navigate into directory
                new_items = _list_directory(selected_item.path)
                if new_items:
                    current_items = new_items
                    selected_index = 0
                    current_path = selected_item.path
                    render()
                else:
                    # Directory is empty or not accessible
                    path_stack.pop()  # Remove from stack
                    display.display_lines([title, "Cannot access", "directory"])
                    time.sleep(1)
                    render()
            else:
                # File selected - show file info
                file_path = selected_item.path
                file_name = file_path.name

                try:
                    file_size = file_path.stat().st_size
                    if file_size < 1024:
                        size_str = f"{file_size}B"
                    elif file_size < 1024 * 1024:
                        size_str = f"{file_size / 1024:.1f}KB"
                    elif file_size < 1024 * 1024 * 1024:
                        size_str = f"{file_size / (1024 * 1024):.1f}MB"
                    else:
                        size_str = f"{file_size / (1024 * 1024 * 1024):.1f}GB"

                    # Show file info
                    display.display_lines(
                        [
                            "FILE INFO",
                            file_name[:20],
                            size_str,
                        ]
                    )
                    time.sleep(2)
                    render()
                except (OSError, PermissionError):
                    display.display_lines([title, "Cannot read", "file info"])
                    time.sleep(1)
                    render()

        # Update button states
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["U"] = current_u
        prev_states["D"] = current_d

        time.sleep(0.05)
