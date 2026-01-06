from rpi_usb_cloner.menu import MenuItem, definitions


def build_device_items(drives_service, drive_menu, menu_actions):
    labels = drives_service.list_media_drive_labels()
    items = [MenuItem(label=label, submenu=drive_menu) for label in labels]
    if not items:
        items.append(MenuItem(label="NO USB DEVICES", action=menu_actions.noop))
    return items


def build_settings_items(settings_store, app_state, menu_actions, power_menu):
    screensaver_enabled = settings_store.get_bool(
        "screensaver_enabled",
        default=app_state.ENABLE_SLEEP,
    )
    screensaver_state = "ON" if screensaver_enabled else "OFF"
    return [
        MenuItem(
            label="WIFI",
            action=menu_actions.wifi_settings,
        ),
        MenuItem(
            label=f"SCREENSAVER: {screensaver_state}",
            submenu=definitions.SCREENSAVER_MENU,
        ),
        MenuItem(
            label="POWER",
            submenu=power_menu,
        ),
        MenuItem(
            label="DEVELOP",
            submenu=definitions.DEVELOP_MENU,
        ),
        MenuItem(
            label="UPDATE",
            action=menu_actions.update_version,
        ),
    ]


def build_screensaver_items(settings_store, app_state, menu_actions):
    screensaver_enabled = settings_store.get_bool(
        "screensaver_enabled",
        default=app_state.ENABLE_SLEEP,
    )
    screensaver_state = "ON" if screensaver_enabled else "OFF"
    mode = settings_store.get_setting("screensaver_mode", "random")
    mode_label = "RANDOM" if mode == "random" else "SELECTED"
    selected_gif = settings_store.get_setting("screensaver_gif")
    selected_label = selected_gif if selected_gif else "NONE"
    return [
        MenuItem(
            label=f"SCREENSAVER: {screensaver_state}",
            action=menu_actions.toggle_screensaver_enabled,
        ),
        MenuItem(
            label=f"MODE: {mode_label}",
            action=menu_actions.toggle_screensaver_mode,
        ),
        MenuItem(
            label=f"SELECT GIF: {selected_label}",
            action=menu_actions.select_screensaver_gif,
        ),
    ]
