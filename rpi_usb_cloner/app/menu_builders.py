import os

from rpi_usb_cloner.config.settings import (
    DEFAULT_TRANSITION_FRAME_COUNT,
    DEFAULT_TRANSITION_FRAME_DELAY,
)
from rpi_usb_cloner.menu import MenuItem, definitions


def build_device_items(drives_service, drive_menu, menu_actions):
    labels = drives_service.list_media_drive_labels()
    items = [MenuItem(label=label, submenu=drive_menu) for label in labels]
    if not items:
        items.append(MenuItem(label="NO USB DEVICES", action=menu_actions.noop))
    return items


def _build_transition_label(settings_store):
    transition_frames = settings_store.get_setting(
        "transition_frame_count", DEFAULT_TRANSITION_FRAME_COUNT
    )
    transition_delay = settings_store.get_setting(
        "transition_frame_delay", DEFAULT_TRANSITION_FRAME_DELAY
    )
    try:
        transition_frames_label = int(transition_frames)
    except (TypeError, ValueError):
        transition_frames_label = DEFAULT_TRANSITION_FRAME_COUNT
    try:
        transition_delay_label = float(transition_delay)
    except (TypeError, ValueError):
        transition_delay_label = DEFAULT_TRANSITION_FRAME_DELAY
    return f"TRANSITIONS: {transition_frames_label}F {transition_delay_label:.3f}s"


def build_connectivity_items(settings_store, menu_actions):
    web_server_enabled_setting = settings_store.get_bool(
        "web_server_enabled",
        default=False,
    )
    web_server_env_override = os.environ.get("WEB_SERVER_ENABLED", None)
    if web_server_env_override is not None:
        web_server_enabled = web_server_env_override.lower() not in {"0", "false", "no"}
        web_server_state = "ON" if web_server_enabled else "OFF"
        web_server_label = f"WEB SERVER: {web_server_state} (ENV)"
    else:
        web_server_enabled = web_server_enabled_setting
        web_server_state = "ON" if web_server_enabled else "OFF"
        web_server_label = f"WEB SERVER: {web_server_state}"

    return [
        MenuItem(
            label="WIFI",
            action=menu_actions.wifi_settings,
        ),
        MenuItem(
            label=web_server_label,
            action=menu_actions.toggle_web_server,
        ),
    ]


def build_display_items(settings_store, app_state, menu_actions):
    screensaver_enabled = settings_store.get_bool(
        "screensaver_enabled",
        default=app_state.screensaver_enabled,
    )
    screensaver_state = "ON" if screensaver_enabled else "OFF"

    return [
        MenuItem(
            label=f"SCREENSAVER: {screensaver_state}",
            submenu=definitions.SCREENSAVER_MENU,
        ),
    ]


def build_screensaver_items(settings_store, app_state, menu_actions):
    screensaver_enabled = settings_store.get_bool(
        "screensaver_enabled",
        default=app_state.screensaver_enabled,
    )
    screensaver_state = "ON" if screensaver_enabled else "OFF"
    mode = settings_store.get_setting("screensaver_mode", "random")
    mode_label = "RANDOM" if mode == "random" else "SELECTED"
    selected_gif = settings_store.get_setting("screensaver_gif")
    selected_label = selected_gif if selected_gif else "NONE"
    items = [
        MenuItem(
            label=f"SCREENSAVER: {screensaver_state}",
            action=menu_actions.toggle_screensaver_enabled,
        ),
        MenuItem(
            label=f"MODE: {mode_label}",
            action=menu_actions.toggle_screensaver_mode,
        ),
    ]

    if mode != "random":
        items.append(
            MenuItem(
                label=f"SELECT GIF: {selected_label}",
                action=menu_actions.select_screensaver_gif,
            )
        )

    items.append(
        MenuItem(
            label="PREVIEW",
            action=menu_actions.preview_screensaver,
        )
    )

    return items


def build_develop_items(settings_store, menu_actions):
    transition_label = _build_transition_label(settings_store)
    return [
        MenuItem(
            label="SCREENS",
            submenu=definitions.SCREENS_MENU,
        ),
        MenuItem(
            label="ICONS",
            submenu=definitions.ICONS_MENU,
        ),
        MenuItem(
            label="TITLE FONT PREVIEW",
            action=menu_actions.preview_title_font,
        ),
        MenuItem(
            label="SCREENSHOTS",
            action=menu_actions.toggle_screenshots,
        ),
        MenuItem(
            label=transition_label,
            action=menu_actions.select_transition_speed,
        ),
    ]
