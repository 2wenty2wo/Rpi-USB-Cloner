"""UI action handlers for settings screens."""
import time

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.config import settings
from rpi_usb_cloner.menu.model import get_screen_icon
from rpi_usb_cloner.ui import keyboard, menus, screens, screensaver
from rpi_usb_cloner.ui.icons import KEYBOARD_ICON, SETTINGS_ICON


def coming_soon() -> None:
    """Display coming soon screen."""
    screens.show_coming_soon(title="SETTINGS")


def wifi_settings() -> None:
    """Display WiFi settings screen."""
    screens.show_wifi_settings(title="WIFI")


def select_restore_partition_mode() -> None:
    """Select Clonezilla restore partition mode."""
    options = [
        ("k0", "USE SOURCE (-k0)"),
        ("k", "SKIP TABLE (-k)"),
        ("k1", "RESIZE TABLE (-k1)"),
        ("k2", "MANUAL TABLE (-k2)"),
    ]
    current_mode = str(settings.get_setting("restore_partition_mode", "k0")).lstrip("-")
    selected_index = 0
    for index, (value, _) in enumerate(options):
        if value == current_mode:
            selected_index = index
            break
    selection = menus.render_menu_list(
        "Partitions",
        [label for _, label in options],
        selected_index=selected_index,
        header_lines=["Partition table mode"],
        title_icon=SETTINGS_ICON,
    )
    if selection is None:
        return
    selected_value, selected_label = options[selection]
    settings.set_setting("restore_partition_mode", selected_value)
    screens.render_status_template("RESTORE PT", f"Set: {selected_label}")
    time.sleep(1.5)


def screensaver_settings() -> None:
    """Toggle screensaver settings."""
    toggle_screensaver_enabled()


def toggle_screensaver_enabled() -> None:
    """Toggle screensaver enabled/disabled."""
    enabled = settings.get_bool("screensaver_enabled", default=app_state.ENABLE_SLEEP)
    enabled = not enabled
    settings.set_bool("screensaver_enabled", enabled)
    app_state.ENABLE_SLEEP = enabled
    status = "ENABLED" if enabled else "DISABLED"
    screens.render_status_template("SCREENSAVER", f"Screensaver {status}")
    time.sleep(1.5)


def toggle_screensaver_mode() -> None:
    """Toggle screensaver mode between random and selected."""
    mode = settings.get_setting("screensaver_mode", "random")
    new_mode = "selected" if mode == "random" else "random"
    settings.set_setting("screensaver_mode", new_mode)
    status = "SELECTED" if new_mode == "selected" else "RANDOM"
    screens.render_status_template("SCREENSAVER", f"Mode: {status}")
    time.sleep(1.5)


def select_screensaver_gif() -> None:
    """Select screensaver GIF from available options."""
    gif_paths = screensaver.list_available_gifs()
    if not gif_paths:
        screens.render_status_template("SCREENSAVER", "No GIFs found")
        time.sleep(1.5)
        return
    gif_names = [path.name for path in gif_paths]
    current_selection = settings.get_setting("screensaver_gif")
    selected_index = 0
    if current_selection in gif_names:
        selected_index = gif_names.index(current_selection)
    selection = menus.render_menu_list(
        "SELECT GIF",
        gif_names,
        selected_index=selected_index,
    )
    if selection is None:
        return
    selected_name = gif_names[selection]
    settings.set_setting("screensaver_gif", selected_name)
    screens.render_status_template("SCREENSAVER", f"Selected {selected_name}")
    time.sleep(1.5)


def keyboard_test() -> None:
    """Test keyboard input."""
    text = keyboard.prompt_text(title="KEYBOARD", masked=False, title_icon=KEYBOARD_ICON)
    if text is None:
        return
    screens.render_status_template("KEYBOARD", "Entry captured")
    time.sleep(1.5)


def demo_confirmation_screen() -> None:
    """Demo confirmation screen."""
    screens.render_confirmation_screen("CONFIRM", ["Demo prompt line 1", "Demo line 2"])
    screens.wait_for_ack()


def demo_status_screen() -> None:
    """Demo status screen."""
    screens.render_status_template("STATUS", "Running...", progress_line="Demo progress")
    screens.wait_for_ack()


def demo_info_screen() -> None:
    """Demo info screen."""
    lines = [
        "Line 1",
        "Line 2",
        "Line 3",
        "Line 4",
        "Line 5",
    ]
    screens.render_info_screen("INFO", lines)
    screens.wait_for_paginated_input("INFO", lines)


def demo_progress_screen() -> None:
    """Demo progress screen."""
    screens.render_progress_screen("PROGRESS", ["Working..."], progress_ratio=0.6)
    screens.wait_for_ack()


def lucide_demo() -> None:
    """Show Lucide icons demo."""
    screens.show_lucide_demo()


def heroicons_demo() -> None:
    """Show Heroicons demo."""
    screens.show_heroicons_demo()


def preview_title_font() -> None:
    """Preview title font."""
    screens.show_title_font_preview()
