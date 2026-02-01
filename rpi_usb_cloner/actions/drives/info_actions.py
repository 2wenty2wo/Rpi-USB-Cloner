"""Drive info/view actions.

Handles viewing device information and disk usage.
"""

from __future__ import annotations

import os
import time
from typing import Callable

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.logging import LoggerFactory
from rpi_usb_cloner.storage.devices import (
    get_children,
    human_size,
    list_usb_disks,
)
from rpi_usb_cloner.ui import display
from rpi_usb_cloner.ui.icons import DRIVES_ICON

from ._utils import handle_screenshot


log_system = LoggerFactory.for_system()


def drive_info(
    *,
    state: app_state.AppState,
    get_selected_usb_name: Callable[[], str | None],
) -> None:
    """Show detailed drive information with pagination."""
    page_index = 0
    total_pages, page_index = _view_devices(
        get_selected_usb_name=get_selected_usb_name,
        page_index=page_index,
    )

    from rpi_usb_cloner.ui import menus

    menus.wait_for_buttons_release(
        [gpio.PIN_A, gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D, gpio.PIN_C]
    )

    last_selected_name = get_selected_usb_name()
    prev_states = {
        "A": gpio.is_pressed(gpio.PIN_A),
        "L": gpio.is_pressed(gpio.PIN_L),
        "R": gpio.is_pressed(gpio.PIN_R),
        "U": gpio.is_pressed(gpio.PIN_U),
        "D": gpio.is_pressed(gpio.PIN_D),
        "C": gpio.is_pressed(gpio.PIN_C),
    }

    while True:
        current_a = gpio.is_pressed(gpio.PIN_A)
        if prev_states["A"] and not current_a:
            return

        current_l = gpio.is_pressed(gpio.PIN_L)
        if prev_states["L"] and not current_l:
            page_index = max(0, page_index - 1)
            total_pages, page_index = _view_devices(
                get_selected_usb_name=get_selected_usb_name,
                page_index=page_index,
            )

        current_r = gpio.is_pressed(gpio.PIN_R)
        if prev_states["R"] and not current_r:
            page_index = min(total_pages - 1, page_index + 1)
            total_pages, page_index = _view_devices(
                get_selected_usb_name=get_selected_usb_name,
                page_index=page_index,
            )

        current_u = gpio.is_pressed(gpio.PIN_U)
        if prev_states["U"] and not current_u:
            page_index = max(0, page_index - 1)
            total_pages, page_index = _view_devices(
                get_selected_usb_name=get_selected_usb_name,
                page_index=page_index,
            )

        current_d = gpio.is_pressed(gpio.PIN_D)
        if prev_states["D"] and not current_d:
            page_index = min(total_pages - 1, page_index + 1)
            total_pages, page_index = _view_devices(
                get_selected_usb_name=get_selected_usb_name,
                page_index=page_index,
            )

        current_c = gpio.is_pressed(gpio.PIN_C)
        if prev_states["C"] and not current_c and handle_screenshot():
            total_pages, page_index = _view_devices(
                get_selected_usb_name=get_selected_usb_name,
                page_index=page_index,
            )

        current_selected_name = get_selected_usb_name()
        if current_selected_name != last_selected_name:
            page_index = 0
            total_pages, page_index = _view_devices(
                get_selected_usb_name=get_selected_usb_name,
                page_index=page_index,
            )
            last_selected_name = current_selected_name

        prev_states["A"] = current_a
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        prev_states["C"] = current_c
        time.sleep(0.05)


def _view_devices(
    *,
    get_selected_usb_name: Callable[[], str | None],
    page_index: int,
) -> tuple[int, int]:
    """Render device info pages. Returns (total_pages, current_page_index)."""
    selected_name = get_selected_usb_name()
    if not selected_name:
        display.display_lines(["NO SELECTED USB"])
        return 1, 0

    devices_list = [
        device for device in list_usb_disks() if device.get("name") == selected_name
    ]
    if not devices_list:
        display.display_lines(["NO SELECTED USB"])
        return 1, 0

    device = devices_list[0]

    # Calculate total pages:
    # Page 0: Disk usage
    # Page 1: Device info (identity)
    # Page 2: Drive info (metadata)
    # Pages 3+: Partition info (may be multiple pages)
    context = display.get_display_context()
    items_font = context.fontdisks
    title_font = context.fontcopy
    title_icon = DRIVES_ICON

    # Simulate partition info layout to calculate pages
    layout = display.draw_title_with_icon(
        "PARTITION INFO",
        title_font=title_font,
        icon=title_icon,
        extra_gap=2,
        left_margin=context.x - 11,
    )
    available_height = context.height - layout.content_top - 2 - 12
    line_step = display._get_line_height(items_font) + 2
    lines_per_page = max(1, available_height // line_step)

    # Count partition lines (3 lines per partition: name+fs, mount, blank)
    children = get_children(device)
    partition_line_count = len(children) * 3 if children else 0
    partition_pages = (
        max(1, (partition_line_count + lines_per_page - 1) // lines_per_page)
        if children
        else 1
    )

    total_pages = (
        3 + partition_pages
    )  # disk usage + device info + drive info + partitions

    # Route to appropriate renderer based on page index
    if page_index == 0:
        _render_disk_usage_page(device, page_index=page_index, total_pages=total_pages)
    elif page_index == 1:
        _render_device_identity_page(
            device, page_index=page_index, total_pages=total_pages
        )
    elif page_index == 2:
        _render_drive_metadata_page(
            device, page_index=page_index, total_pages=total_pages
        )
    else:
        partition_page_index = page_index - 3
        _render_partition_info_page(
            device,
            partition_page_index=partition_page_index,
            page_index=page_index,
            total_pages=total_pages,
        )

    return total_pages, page_index


def _render_disk_usage_page(
    device: dict,
    *,
    page_index: int,
    total_pages: int,
) -> None:
    """Render disk usage page with pie chart."""
    context = display.get_display_context()
    draw = context.draw

    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    title = "DISK USAGE"
    title_font = context.fontcopy
    title_icon = DRIVES_ICON
    layout = display.draw_title_with_icon(
        title,
        title_font=title_font,
        icon=title_icon,
        extra_gap=2,
        left_margin=context.x - 11,
    )

    current_y = layout.content_top + 2
    items_font = context.fontdisks
    left_margin = context.x - 11

    # Pie chart configuration
    pie_size = 36
    pie_x = context.width - pie_size - 6
    pie_y = layout.content_top

    # Collect disk usage from all mounted partitions
    total_bytes = 0
    used_bytes = 0
    partition_count = 0

    for child in get_children(device):
        mountpoint = child.get("mountpoint")
        if not mountpoint:
            continue

        try:
            usage = os.statvfs(mountpoint)
            total = usage.f_blocks * usage.f_frsize
            free = usage.f_bavail * usage.f_frsize
            used = total - free

            total_bytes += total
            used_bytes += used
            partition_count += 1
        except (FileNotFoundError, PermissionError, OSError) as error:
            log_system.debug(
                "Disk usage check failed", mountpoint=mountpoint, error=str(error)
            )

    if partition_count == 0 or total_bytes == 0:
        lines = ["No mounted", "partitions"]
        for line in lines:
            draw.text((left_margin, current_y), line, font=items_font, fill=255)
            current_y += display._get_line_height(items_font) + 2
    else:
        free_bytes = total_bytes - used_bytes
        used_percent = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0

        text_lines = [
            f"Used: {human_size(used_bytes)}",
            f"Free: {human_size(free_bytes)}",
            f"Total: {human_size(total_bytes)}",
            f"({used_percent:.1f}% used)",
        ]

        for line in text_lines:
            draw.text((left_margin, current_y), line, font=items_font, fill=255)
            current_y += display._get_line_height(items_font) + 2

        # Draw pie chart
        draw.ellipse(
            [(pie_x, pie_y), (pie_x + pie_size, pie_y + pie_size)],
            outline=255,
            fill=0,
        )

        if used_percent > 0:
            start_angle = 90
            end_angle = start_angle - (used_percent / 100 * 360)
            draw.pieslice(
                (
                    (pie_x + 1, pie_y + 1),
                    (pie_x + pie_size - 1, pie_y + pie_size - 1),
                ),
                start=start_angle,
                end=end_angle,
                fill=255,
                outline=255,
            )

    _draw_page_indicator(context, page_index, total_pages, items_font)
    context.disp.display(context.image)


def _render_device_identity_page(
    device: dict,
    *,
    page_index: int,
    total_pages: int,
) -> None:
    """Render page 2: DEVICE INFO - name, model, serial."""
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    title_font = context.fontcopy
    items_font = context.fontdisks
    title_icon = DRIVES_ICON
    layout = display.draw_title_with_icon(
        "DEVICE INFO",
        title_font=title_font,
        icon=title_icon,
        extra_gap=2,
        left_margin=context.x - 11,
    )

    current_y = layout.content_top + 2
    left_margin = context.x - 11

    device_name = device.get("name") or ""
    size_bytes = device.get("size") or 0
    size_gb = size_bytes / (1024**3)
    draw.text(
        (left_margin, current_y),
        f"{device_name.upper()} {size_gb:.1f}GB",
        font=items_font,
        fill=255,
    )
    current_y += display._get_line_height(items_font) + 2

    vendor = (device.get("vendor") or "").strip()
    model = (device.get("model") or "").strip()
    vendor_model = " ".join(part for part in [vendor, model] if part)
    if vendor_model:
        available_width = context.width - left_margin
        wrapped = display._wrap_lines_to_width(
            [vendor_model], items_font, available_width
        )
        for line in wrapped:
            draw.text((left_margin, current_y), line, font=items_font, fill=255)
            current_y += display._get_line_height(items_font) + 2

    serial = (device.get("serial") or "").strip()
    if serial:
        available_width = context.width - left_margin
        wrapped = display._wrap_lines_to_width(
            [f"SERIAL:{serial}"], items_font, available_width
        )
        for line in wrapped:
            draw.text((left_margin, current_y), line.upper(), font=items_font, fill=255)
            current_y += display._get_line_height(items_font) + 2

    _draw_page_indicator(context, page_index, total_pages, items_font)
    context.disp.display(context.image)


def _render_drive_metadata_page(
    device: dict,
    *,
    page_index: int,
    total_pages: int,
) -> None:
    """Render page 3: DRIVE INFO - type, table, uuid."""
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    title_font = context.fontcopy
    items_font = context.fontdisks
    title_icon = DRIVES_ICON
    layout = display.draw_title_with_icon(
        "DRIVE INFO",
        title_font=title_font,
        icon=title_icon,
        extra_gap=2,
        left_margin=context.x - 11,
    )

    current_y = layout.content_top + 2
    left_margin = context.x - 11

    rota = device.get("rota")
    if rota is not None:
        device_type = "HDD" if rota == "1" or rota == 1 else "SSD"
        draw.text(
            (left_margin, current_y), f"TYPE: {device_type}", font=items_font, fill=255
        )
        current_y += display._get_line_height(items_font) + 2

    pttype = (device.get("pttype") or "").strip()
    if pttype:
        draw.text(
            (left_margin, current_y),
            f"TABLE: {pttype.upper()}",
            font=items_font,
            fill=255,
        )
        current_y += display._get_line_height(items_font) + 2

    ptuuid = (device.get("ptuuid") or "").strip()
    if ptuuid:
        draw.text(
            (left_margin, current_y),
            f"UUID: {ptuuid.upper()}",
            font=items_font,
            fill=255,
        )
        current_y += display._get_line_height(items_font) + 2

    _draw_page_indicator(context, page_index, total_pages, items_font)
    context.disp.display(context.image)


def _render_partition_info_page(
    device: dict,
    *,
    partition_page_index: int,
    page_index: int,
    total_pages: int,
) -> None:
    """Render pages 4+: PARTITION INFO - partition details (paginated)."""
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    title_font = context.fontcopy
    items_font = context.fontdisks
    title_icon = DRIVES_ICON
    layout = display.draw_title_with_icon(
        "PARTITION INFO",
        title_font=title_font,
        icon=title_icon,
        extra_gap=2,
        left_margin=context.x - 11,
    )

    current_y = layout.content_top + 2
    left_margin = context.x - 11
    available_height = context.height - current_y - 12
    line_height = display._get_line_height(items_font)
    line_step = line_height + 2

    # Build partition lines
    partition_lines = []
    children = get_children(device)
    for child in children:
        name = child.get("name") or ""
        fstype = child.get("fstype") or "RAW"
        label = (child.get("label") or "").strip()
        mountpoint = child.get("mountpoint")

        label_suffix = f" ({label})" if label else ""
        partition_lines.append(f"{name.upper()} - {fstype.upper()}{label_suffix}")

        if mountpoint:
            partition_lines.append(f"MOUNT: {mountpoint.upper()}")
        else:
            partition_lines.append("MOUNT: NOT MOUNTED")

        partition_lines.append("")  # Spacing

    # Paginate partition lines
    lines_per_page = max(1, available_height // line_step)
    start = partition_page_index * lines_per_page
    end = start + lines_per_page
    page_lines = partition_lines[start:end]

    for line in page_lines:
        if line:
            draw.text((left_margin, current_y), line, font=items_font, fill=255)
        current_y += line_step

    _draw_page_indicator(context, page_index, total_pages, items_font)
    context.disp.display(context.image)


def _draw_page_indicator(context, page_index: int, total_pages: int, font) -> None:
    """Helper to draw page indicator in bottom right."""
    if total_pages > 1:
        left_indicator = "<" if page_index > 0 else ""
        right_indicator = ">" if page_index < total_pages - 1 else ""
        indicator = f"{left_indicator}{page_index + 1}/{total_pages}{right_indicator}"
        indicator_bbox = context.draw.textbbox((0, 0), indicator, font=font)
        indicator_width = indicator_bbox[2] - indicator_bbox[0]
        indicator_height = indicator_bbox[3] - indicator_bbox[1]
        context.draw.text(
            (
                context.width - indicator_width - 2,
                context.height - indicator_height - 2,
            ),
            indicator,
            font=font,
            fill=255,
        )
