"""UI action handlers for settings screens."""

import time
from pathlib import Path

from PIL import Image, ImageDraw

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.config import settings
from rpi_usb_cloner.config.settings import (
    DEFAULT_TRANSITION_FRAME_COUNT,
    DEFAULT_TRANSITION_FRAME_DELAY,
)
from rpi_usb_cloner.ui import display, keyboard, menus, screens, screensaver
from rpi_usb_cloner.ui.icons import KEYBOARD_ICON, SETTINGS_ICON
from rpi_usb_cloner.web import server as web_server


def validate_restore_partition_mode(mode: str) -> str:
    """Validate Clonezilla restore partition mode."""
    valid_modes = {"k0", "k", "k1", "k2"}
    if mode not in valid_modes:
        valid_list = ", ".join(sorted(valid_modes))
        raise ValueError(
            f"Invalid restore partition mode: {mode}. Expected: {valid_list}."
        )
    return mode


def apply_restore_partition_mode(mode: str) -> None:
    """Persist the restore partition mode to settings."""
    validated = validate_restore_partition_mode(mode)
    settings.set_setting("restore_partition_mode", validated)


def validate_transition_settings(frames: int, delay: float) -> None:
    """Validate transition settings values."""
    valid_pairs = {(2, 0.0), (3, 0.005), (4, 0.01)}
    if (frames, delay) not in valid_pairs:
        valid_list = ", ".join(
            f"{pair[0]}@{pair[1]:.3f}s" for pair in sorted(valid_pairs)
        )
        raise ValueError(
            "Invalid transition settings: "
            f"frames={frames}, delay={delay}. Expected one of: {valid_list}."
        )


def apply_transition_settings(frames: int, delay: float) -> None:
    """Persist transition settings to configuration."""
    validate_transition_settings(frames, delay)
    settings.set_setting("transition_frame_count", frames)
    settings.set_setting("transition_frame_delay", delay)


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
        transition_direction="forward",
    )
    if selection is None:
        return
    selected_value, selected_label = options[selection]
    apply_restore_partition_mode(selected_value)
    screens.render_status_template("RESTORE PT", f"Set: {selected_label}")
    time.sleep(1.5)


def screensaver_settings() -> None:
    """Toggle screensaver settings."""
    toggle_screensaver_enabled()


def toggle_screensaver_enabled() -> None:
    """Toggle screensaver enabled/disabled."""
    enabled = settings.get_bool(
        "screensaver_enabled", default=app_state.screensaver_enabled
    )
    enabled = not enabled
    settings.set_bool("screensaver_enabled", enabled)
    app_state.screensaver_enabled = enabled
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
        transition_direction="forward",
    )
    if selection is None:
        return
    selected_name = gif_names[selection]
    settings.set_setting("screensaver_gif", selected_name)
    screens.render_status_template("SCREENSAVER", f"Selected {selected_name}")
    time.sleep(1.5)


def preview_screensaver() -> None:
    """Preview the current screensaver configuration."""
    mode = settings.get_setting("screensaver_mode", "random")
    selected_gif = settings.get_setting("screensaver_gif")

    screens.render_status_template("PREVIEW", "Starting...")
    time.sleep(0.5)  # Short delay to show status and avoid immediate keypress detection

    context = display.get_display_context()

    # We need to manually check input to break the loop, but play_screensaver
    # handles the loop internally and returns when input is detected.
    # We just need to ensure we don't return immediately if the button
    # used to select the menu item is still pressed.
    # However, standard practice in this codebase seems to be just calling the function.
    # Let's trust play_screensaver's input check or the delay we added.

    screensaver.play_screensaver(
        context,
        selected_gif=selected_gif,
        screensaver_mode=mode,
    )


def keyboard_test() -> None:
    """Test keyboard input."""
    text = keyboard.prompt_text(
        title="KEYBOARD", masked=False, title_icon=KEYBOARD_ICON
    )
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
    screens.render_status_template(
        "STATUS", "Running...", progress_line="Demo progress"
    )
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


def toggle_screenshots() -> None:
    """Toggle screenshot mode enabled/disabled."""
    enabled = settings.get_bool("screenshots_enabled", default=False)
    enabled = not enabled
    settings.set_bool("screenshots_enabled", enabled)
    status = "ENABLED" if enabled else "DISABLED"
    screens.render_status_template("SCREENSHOTS", f"Screenshots {status}")
    time.sleep(1.5)


def toggle_web_server(app_context=None) -> None:
    """Toggle web server enabled/disabled."""
    enabled = settings.get_bool("web_server_enabled", default=False)
    if enabled:
        settings.set_bool("web_server_enabled", False)
        web_server.stop_server()
        screens.render_status_template("WEB SERVER", "Web server DISABLED")
        time.sleep(1.5)
        return

    try:
        web_server.start_server(app_context=app_context)
    except OSError:
        screens.render_status_template("WEB SERVER", "Start FAILED")
        time.sleep(1.5)
        return
    settings.set_bool("web_server_enabled", True)
    screens.render_status_template("WEB SERVER", "Web server ENABLED")
    time.sleep(1.5)


def select_transition_speed() -> None:
    """Select OLED/Web UI transition speed."""
    options = [
        ("FAST", 2, 0.0),
        ("SNAPPY", 3, 0.005),
        ("SMOOTH", 4, 0.01),
    ]
    current_frames = settings.get_setting(
        "transition_frame_count", DEFAULT_TRANSITION_FRAME_COUNT
    )
    current_delay = settings.get_setting(
        "transition_frame_delay", DEFAULT_TRANSITION_FRAME_DELAY
    )
    selected_index = 0
    for index, (_, frames, delay) in enumerate(options):
        if frames == current_frames and delay == current_delay:
            selected_index = index
            break
    labels = [
        f"{label} ({frames} frames, {delay:.3f}s)" for label, frames, delay in options
    ]
    selection = menus.render_menu_list(
        "TRANSITIONS",
        labels,
        selected_index=selected_index,
        header_lines=["Slide transition speed"],
        title_icon=SETTINGS_ICON,
        transition_direction="forward",
    )
    if selection is None:
        return
    label, frames, delay = options[selection]
    apply_transition_settings(frames, delay)
    screens.render_status_template("TRANSITIONS", f"Set: {label}")
    time.sleep(1.5)


def show_about_credits() -> None:
    """Display the credits screen from assets/credits.png.

    This function is called from the ABOUT menu option in Settings.
    It displays the credits.png image on the OLED screen and waits
    for the user to press back or OK button to return to the menu.

    Image path: rpi_usb_cloner/ui/assets/credits.png

    Flow:
    1. Settings menu -> ABOUT option
    2. menu_actions.show_about_credits() called
    3. settings_actions.show_about_credits() re-exported
    4. This function loads and displays credits.png
    5. User presses button to return to Settings menu
    """
    context = display.get_display_context()
    assets_dir = Path(__file__).resolve().parent.parent.parent / "ui" / "assets"
    credits_path = assets_dir / "credits.png"

    if not credits_path.exists():
        screens.render_status_template("ABOUT", "Credits not found")
        time.sleep(1.5)
        return

    # Load and display the credits image (convert to 1-bit for OLED)
    credits_image = Image.open(credits_path).convert("1")

    # Resize if necessary to fit the OLED display dimensions
    if credits_image.size != (context.width, context.height):
        credits_image = credits_image.resize((context.width, context.height))

    # Display the image on the OLED screen
    with display._display_lock:
        context.image = credits_image
        context.draw = ImageDraw.Draw(context.image)
        context.disp.display(credits_image)
        display.mark_display_dirty()

    # Wait for user to press back (PIN_A) or OK (PIN_B) button
    screens.wait_for_ack()
