"""Settings and configuration menu definitions."""

from __future__ import annotations

from rpi_usb_cloner.menu.model import MenuScreen

from .. import actions as menu_actions
from . import menu_entry


ICONS_MENU = MenuScreen(
    screen_id="icons",
    title="ICONS",
    items=[
        menu_entry("LUCIDE", action=menu_actions.lucide_demo),
        menu_entry("HEROICONS", action=menu_actions.heroicons_demo),
    ],
)

SCREENS_MENU = MenuScreen(
    screen_id="screens",
    title="SCREENS",
    items=[
        menu_entry("KEYBOARD", action=menu_actions.keyboard_test),
        menu_entry("CONFIRMATION", action=menu_actions.demo_confirmation_screen),
        menu_entry("STATUS", action=menu_actions.demo_status_screen),
        menu_entry("INFO", action=menu_actions.demo_info_screen),
        menu_entry("PROGRESS", action=menu_actions.demo_progress_screen),
    ],
)

DEVELOP_MENU = MenuScreen(
    screen_id="develop",
    title="DEVELOP",
    items=[
        menu_entry("SCREENS", submenu=SCREENS_MENU),
        menu_entry("ICONS", submenu=ICONS_MENU),
        menu_entry("TITLE FONT PREVIEW", action=menu_actions.preview_title_font),
        menu_entry("SCREENSHOTS", action=menu_actions.toggle_screenshots),
    ],
)

POWER_MENU = MenuScreen(
    screen_id="power",
    title="POWER",
    items=[
        menu_entry("RESTART RPI-USB-CLONER", action=menu_actions.restart_service),
        menu_entry("STOP RPI-USB-CLONER", action=menu_actions.stop_service),
        menu_entry("RESTART SYSTEM", action=menu_actions.restart_system),
        menu_entry("SHUTDOWN SYSTEM", action=menu_actions.shutdown_system),
    ],
)

SCREENSAVER_MENU = MenuScreen(
    screen_id="screensaver",
    title="SCREENSAVER",
)

VIEW_MENU = MenuScreen(
    screen_id="view",
    title="VIEW",
    items=[
        menu_entry("MENU VIEW MODE", action=menu_actions.toggle_menu_view_mode),
    ],
)

SETTINGS_MENU = MenuScreen(
    screen_id="settings",
    title="SETTINGS",
    items=[
        menu_entry("WIFI", action=menu_actions.wifi_settings),
        menu_entry("WEB SERVER", action=menu_actions.toggle_web_server),
        menu_entry("VIEW", submenu=VIEW_MENU),
        menu_entry("SCREENSAVER", submenu=SCREENSAVER_MENU),
        menu_entry("DEVELOP", submenu=DEVELOP_MENU),
        menu_entry("POWER", submenu=POWER_MENU),
    ],
)
