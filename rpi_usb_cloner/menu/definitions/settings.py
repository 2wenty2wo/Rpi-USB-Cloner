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
        # Only submenu refs needed here for _collect_screens() discovery.
        # Full items (including dynamic TRANSITIONS label) provided by build_develop_items.
        menu_entry("SCREENS", submenu=SCREENS_MENU),
        menu_entry("ICONS", submenu=ICONS_MENU),
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

STATUS_BAR_MENU = MenuScreen(
    screen_id="status_bar",
    title="STATUS BAR",
    # Items provided dynamically by build_status_bar_items
)

CONNECTIVITY_MENU = MenuScreen(
    screen_id="connectivity",
    title="CONNECTIVITY",
    # Items provided dynamically by build_connectivity_items for WEB SERVER: ON/OFF label
)

DISPLAY_MENU = MenuScreen(
    screen_id="display",
    title="DISPLAY",
    items=[
        menu_entry("SCREENSAVER", submenu=SCREENSAVER_MENU),
        menu_entry("STATUS BAR", submenu=STATUS_BAR_MENU),
    ],
)

SYSTEM_MENU = MenuScreen(
    screen_id="system",
    title="SYSTEM",
    items=[
        menu_entry("SYSTEM INFO", action=menu_actions.system_info),
        menu_entry("UPDATE", action=menu_actions.update_version),
        menu_entry("ABOUT", action=menu_actions.show_about_credits),
        menu_entry("POWER", submenu=POWER_MENU),
    ],
)

ADVANCED_MENU = MenuScreen(
    screen_id="advanced",
    title="ADVANCED",
    items=[
        menu_entry("DEVELOP", submenu=DEVELOP_MENU),
    ],
)

SETTINGS_MENU = MenuScreen(
    screen_id="settings",
    title="SETTINGS",
    items=[
        menu_entry("CONNECTIVITY", submenu=CONNECTIVITY_MENU),
        menu_entry("DISPLAY", submenu=DISPLAY_MENU),
        menu_entry("SYSTEM", submenu=SYSTEM_MENU),
        menu_entry("ADVANCED", submenu=ADVANCED_MENU),
    ],
)
