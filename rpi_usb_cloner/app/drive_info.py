def get_device_status_line(
    active_drive,
    list_media_devices,
    get_device_name,
    get_vendor,
    get_model,
):
    devices_list = list_media_devices()
    if not devices_list:
        return "INSERT USB"
    for device in devices_list:
        if get_device_name(device) == active_drive:
            vendor = (get_vendor(device) or "").strip()
            model = (get_model(device) or "").strip()
            label = " ".join(part for part in [vendor, model] if part)
            return label or active_drive
    return "NO DRIVE SELECTED"


def render_drive_info(
    active_drive,
    list_media_devices,
    get_device_name,
    get_size,
    get_vendor,
    get_model,
    display_module,
    screens_module,
    page_index,
):
    if not active_drive:
        display_module.display_lines(["NO DRIVE", "SELECTED"])
        return 1, 0
    device = None
    for candidate in list_media_devices():
        if get_device_name(candidate) == active_drive:
            device = candidate
            break
    if not device:
        display_module.display_lines(["NO DRIVE", "SELECTED"])
        return 1, 0
    size_gb = get_size(device) / 1024 ** 3
    vendor = (get_vendor(device) or "").strip()
    model = (get_model(device) or "").strip()
    info_lines = [f"{active_drive} {size_gb:.2f}GB"]
    if vendor or model:
        info_lines.append(" ".join(part for part in [vendor, model] if part))
    return screens_module.render_info_screen(
        "DRIVE INFO",
        info_lines,
        page_index=page_index,
        title_font=display_module.get_display_context().fontcopy,
    )
