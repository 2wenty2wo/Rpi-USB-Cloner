import os

from rpi_usb_cloner.config.settings import (
    DEFAULT_TRANSITION_FRAME_COUNT,
    DEFAULT_TRANSITION_FRAME_DELAY,
)
from rpi_usb_cloner.menu import MenuItem, definitions
from rpi_usb_cloner.ui.toggle import format_toggle_label


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
    from rpi_usb_cloner.services.bluetooth import is_bluetooth_pan_enabled

    web_server_enabled_setting = settings_store.get_bool(
        "web_server_enabled",
        default=False,
    )
    web_server_env_override = os.environ.get("WEB_SERVER_ENABLED", None)
    if web_server_env_override is not None:
        web_server_enabled = web_server_env_override.lower() not in {"0", "false", "no"}
        # Show (ENV) suffix when overridden by environment variable
        web_server_label = format_toggle_label("WEB SERVER (ENV)", web_server_enabled)
    else:
        web_server_enabled = web_server_enabled_setting
        web_server_label = format_toggle_label("WEB SERVER", web_server_enabled)

    # Bluetooth PAN status
    bluetooth_enabled = is_bluetooth_pan_enabled()
    bluetooth_label = format_toggle_label("BLUETOOTH PAN", bluetooth_enabled)

    return [
        MenuItem(
            label="WIFI",
            action=menu_actions.wifi_settings,
        ),
        MenuItem(
            label=web_server_label,
            action=menu_actions.toggle_web_server,
        ),
        MenuItem(
            label=bluetooth_label,
            action=menu_actions.bluetooth_settings,
        ),
    ]


def build_display_items(settings_store, app_state, menu_actions):
    screensaver_enabled = settings_store.get_bool(
        "screensaver_enabled",
        default=app_state.screensaver_enabled,
    )
    status_bar_enabled = settings_store.get_bool("status_bar_enabled", default=True)

    return [
        MenuItem(
            label=format_toggle_label("SCREENSAVER", screensaver_enabled),
            submenu=definitions.SCREENSAVER_MENU,
        ),
        MenuItem(
            label=format_toggle_label("STATUS BAR", status_bar_enabled),
            submenu=definitions.STATUS_BAR_MENU,
        ),
    ]


def build_screensaver_items(settings_store, app_state, menu_actions):
    screensaver_enabled = settings_store.get_bool(
        "screensaver_enabled",
        default=app_state.screensaver_enabled,
    )
    mode = settings_store.get_setting("screensaver_mode", "random")
    mode_label = "RANDOM" if mode == "random" else "SELECTED"
    selected_gif = settings_store.get_setting("screensaver_gif")
    selected_label = selected_gif if selected_gif else "NONE"
    items = [
        MenuItem(
            label=format_toggle_label("SCREENSAVER", screensaver_enabled),
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
    screenshots_enabled = settings_store.get_bool("screenshots_enabled", default=False)
    icon_preview_enabled = settings_store.get_bool(
        "menu_icon_preview_enabled", default=False
    )
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
            label=format_toggle_label("SCREENSHOTS", screenshots_enabled),
            action=menu_actions.toggle_screenshots,
        ),
        MenuItem(
            label=format_toggle_label("ICON PREVIEW", icon_preview_enabled),
            action=menu_actions.toggle_menu_icon_preview,
        ),
        MenuItem(
            label=transition_label,
            action=menu_actions.select_transition_speed,
        ),
    ]


def build_status_bar_items(settings_store, menu_actions):
    """Build status bar visibility toggle menu items.

    Shows a master toggle for all icons, and if enabled,
    shows individual toggles for each icon type.
    """
    status_bar_enabled = settings_store.get_bool("status_bar_enabled", default=True)

    items = [
        MenuItem(
            label=format_toggle_label("SHOW ALL", status_bar_enabled),
            action=menu_actions.toggle_status_bar_enabled,
        ),
    ]

    # Only show individual toggles if status bar is enabled
    if status_bar_enabled:
        wifi_enabled = settings_store.get_bool("status_bar_wifi_enabled", default=True)
        bluetooth_enabled = settings_store.get_bool(
            "status_bar_bluetooth_enabled", default=True
        )
        web_enabled = settings_store.get_bool("status_bar_web_enabled", default=True)
        drives_enabled = settings_store.get_bool(
            "status_bar_drives_enabled", default=True
        )

        items.extend(
            [
                MenuItem(
                    label=format_toggle_label("WIFI", wifi_enabled),
                    action=menu_actions.toggle_status_bar_wifi,
                ),
                MenuItem(
                    label=format_toggle_label("BLUETOOTH", bluetooth_enabled),
                    action=menu_actions.toggle_status_bar_bluetooth,
                ),
                MenuItem(
                    label=format_toggle_label("WEB SERVER", web_enabled),
                    action=menu_actions.toggle_status_bar_web,
                ),
                MenuItem(
                    label=format_toggle_label("DRIVE COUNTS", drives_enabled),
                    action=menu_actions.toggle_status_bar_drives,
                ),
            ]
        )

    return items
