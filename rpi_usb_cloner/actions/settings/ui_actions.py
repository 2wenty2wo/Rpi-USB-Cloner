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


def toggle_menu_icon_preview() -> None:
    """Toggle menu icon preview enabled/disabled.

    When enabled, shows a larger 24px version of the selected menu item's
    icon in the empty space on the right side of the display.
    """
    enabled = settings.get_bool("menu_icon_preview_enabled", default=False)
    enabled = not enabled
    settings.set_bool("menu_icon_preview_enabled", enabled)
    status = "ENABLED" if enabled else "DISABLED"
    screens.render_status_template("ICON PREVIEW", f"Icon preview {status}")
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


# -----------------------------------------------------------------------------
# Status Bar Toggle Actions
# -----------------------------------------------------------------------------


def toggle_status_bar_enabled() -> None:
    """Toggle status bar visibility (master toggle)."""
    enabled = settings.get_bool("status_bar_enabled", default=True)
    enabled = not enabled
    settings.set_bool("status_bar_enabled", enabled)
    status = "SHOWN" if enabled else "HIDDEN"
    screens.render_status_template("STATUS BAR", f"Status bar {status}")
    time.sleep(1.5)


def toggle_status_bar_wifi() -> None:
    """Toggle WiFi icon visibility in status bar."""
    enabled = settings.get_bool("status_bar_wifi_enabled", default=True)
    enabled = not enabled
    settings.set_bool("status_bar_wifi_enabled", enabled)
    status = "SHOWN" if enabled else "HIDDEN"
    screens.render_status_template("STATUS BAR", f"WiFi icon {status}")
    time.sleep(1.5)


def toggle_status_bar_bluetooth() -> None:
    """Toggle Bluetooth icon visibility in status bar."""
    enabled = settings.get_bool("status_bar_bluetooth_enabled", default=True)
    enabled = not enabled
    settings.set_bool("status_bar_bluetooth_enabled", enabled)
    status = "SHOWN" if enabled else "HIDDEN"
    screens.render_status_template("STATUS BAR", f"Bluetooth icon {status}")
    time.sleep(1.5)


def toggle_status_bar_web() -> None:
    """Toggle Web Server icon visibility in status bar."""
    enabled = settings.get_bool("status_bar_web_enabled", default=True)
    enabled = not enabled
    settings.set_bool("status_bar_web_enabled", enabled)
    status = "SHOWN" if enabled else "HIDDEN"
    screens.render_status_template("STATUS BAR", f"Web Server icon {status}")
    time.sleep(1.5)


def toggle_status_bar_drives() -> None:
    """Toggle drive counts visibility in status bar."""
    enabled = settings.get_bool("status_bar_drives_enabled", default=True)
    enabled = not enabled
    settings.set_bool("status_bar_drives_enabled", enabled)
    status = "SHOWN" if enabled else "HIDDEN"
    screens.render_status_template("STATUS BAR", f"Drive counts {status}")
    time.sleep(1.5)


# -----------------------------------------------------------------------------
# Bluetooth PAN Actions
# -----------------------------------------------------------------------------


def bluetooth_settings() -> None:
    """Display Bluetooth settings and status screen with menu options."""
    from rpi_usb_cloner.menu.actions import get_action_context
    from rpi_usb_cloner.services.bluetooth import (
        get_bluetooth_status,
        is_bluetooth_pan_enabled,
        is_bluetooth_connected,
    )
    from rpi_usb_cloner.ui.screens.qr_code import render_bluetooth_status_screen

    # Get app context from action context
    action_context = get_action_context()
    app_context = action_context.app_context

    while True:
        context = display.get_display_context()

        # Show status screen
        render_bluetooth_status_screen(app_context, context)

        # Wait for user input
        event_received = False
        while not event_received:
            from rpi_usb_cloner.hardware import gpio

            event = gpio.get_button_event()
            if event:
                button, event_type = event
                if event_type == "press":
                    if button == "A":
                        # Back
                        return
                    elif button == "B":
                        # Select - show Bluetooth menu
                        bluetooth_menu()
                        event_received = True
                    elif button == "C":
                        # Quick toggle
                        status = get_bluetooth_status()
                        if status.enabled:
                            toggle_bluetooth_pan()
                        else:
                            enable_bluetooth_pan()
                        event_received = True

            time.sleep(0.02)


def bluetooth_menu() -> None:
    """Show Bluetooth options menu."""
    from rpi_usb_cloner.services.bluetooth import (
        get_bluetooth_status,
        is_bluetooth_connected,
    )

    status = get_bluetooth_status()

    # Build menu based on current state
    items = []
    if status.enabled:
        items.append("DISABLE BLUETOOTH")
        if status.connected:
            items.append("TRUST THIS DEVICE")
            items.append("SHOW QR CODE")
        else:
            items.append("SHOW QR CODE")
    else:
        items.append("ENABLE BLUETOOTH")

    items.append("TRUSTED DEVICES...")

    selection = menus.render_menu_list(
        "BLUETOOTH",
        items,
        header_lines=["Bluetooth options"],
        transition_direction="forward",
    )

    if selection is None:
        return

    selected = items[selection]

    if selected == "ENABLE BLUETOOTH":
        enable_bluetooth_pan()
    elif selected == "DISABLE BLUETOOTH":
        disable_bluetooth_pan()
    elif selected == "TRUST THIS DEVICE":
        bluetooth_trust_current()
    elif selected == "SHOW QR CODE":
        show_bluetooth_qr()
    elif selected == "TRUSTED DEVICES...":
        bluetooth_trusted_devices()


def toggle_bluetooth_pan() -> None:
    """Toggle Bluetooth PAN mode on/off."""
    from rpi_usb_cloner.services.bluetooth import (
        get_bluetooth_status,
        toggle_bluetooth_pan as do_toggle,
    )

    status = get_bluetooth_status()
    was_enabled = status.enabled

    screens.render_status_template(
        "BLUETOOTH",
        "Enabling..." if not was_enabled else "Disabling...",
    )

    try:
        new_state = do_toggle()
        if new_state:
            status = get_bluetooth_status()
            pin = status.pin or "Unknown"
            screens.render_status_template(
                "BLUETOOTH",
                f"Enabled PIN: {pin}",
            )
        else:
            screens.render_status_template("BLUETOOTH", "Disabled")
    except Exception as e:
        screens.render_status_template("BLUETOOTH", f"Error: {str(e)[:20]}")

    time.sleep(1.5)


def show_bluetooth_qr() -> None:
    """Show Bluetooth pairing QR code screen."""
    from rpi_usb_cloner.menu.actions import get_action_context
    from rpi_usb_cloner.services.bluetooth import (
        generate_qr_data,
        get_bluetooth_status,
        is_bluetooth_pan_enabled,
    )
    from rpi_usb_cloner.ui.screens.qr_code import render_bluetooth_qr_screen

    if not is_bluetooth_pan_enabled():
        screens.render_status_template("BLUETOOTH", "Enable Bluetooth first")
        time.sleep(1.5)
        return

    # Get app context from action context
    action_context = get_action_context()
    app_context = action_context.app_context

    context = display.get_display_context()

    # Show QR screen
    render_bluetooth_qr_screen(app_context, context)

    # Wait for user input
    while True:
        from rpi_usb_cloner.hardware import gpio

        event = gpio.get_button_event()
        if event:
            button, event_type = event
            if event_type == "press":
                if button == "A":
                    # Back
                    break
                elif button == "C":
                    # Refresh - re-render QR code
                    render_bluetooth_qr_screen(app_context, context)

        time.sleep(0.02)


def enable_bluetooth_pan() -> None:
    """Enable Bluetooth PAN mode."""
    from rpi_usb_cloner.services.bluetooth import (
        enable_bluetooth_pan as do_enable,
        get_bluetooth_status,
    )

    screens.render_status_template("BLUETOOTH", "Enabling...")

    try:
        if do_enable():
            status = get_bluetooth_status()
            pin = status.pin or "Unknown"
            screens.render_status_template(
                "BLUETOOTH",
                f"Enabled PIN: {pin}",
            )
        else:
            screens.render_status_template("BLUETOOTH", "Failed to enable")
    except Exception as e:
        screens.render_status_template("BLUETOOTH", f"Error: {str(e)[:20]}")

    time.sleep(1.5)


def disable_bluetooth_pan() -> None:
    """Disable Bluetooth PAN mode."""
    from rpi_usb_cloner.services.bluetooth import disable_bluetooth_pan as do_disable

    screens.render_status_template("BLUETOOTH", "Disabling...")

    try:
        do_disable()
        screens.render_status_template("BLUETOOTH", "Disabled")
    except Exception as e:
        screens.render_status_template("BLUETOOTH", f"Error: {str(e)[:20]}")

    time.sleep(1.5)


def bluetooth_trusted_devices() -> None:
    """Show and manage trusted Bluetooth devices."""
    from rpi_usb_cloner.services.bluetooth import (
        forget_all_bluetooth_devices,
        get_trusted_bluetooth_devices,
        is_bluetooth_auto_reconnect_enabled,
        remove_trusted_bluetooth_device,
        set_bluetooth_auto_reconnect,
    )

    while True:
        devices = get_trusted_bluetooth_devices()
        auto_reconnect = is_bluetooth_auto_reconnect_enabled()

        # Build menu items
        items = []
        # Add auto-reconnect toggle at top
        auto_label = f"AUTO-RECONNECT: {'ON' if auto_reconnect else 'OFF'}"
        items.append(auto_label)

        if devices:
            items.append("-- TRUSTED DEVICES --")
            for device in devices:
                name = device.get("name", "Unknown")
                mac = device.get("mac", "Unknown")
                items.append(f"{name} ({mac[-5:]})")
            items.append("-- ACTIONS --")
            items.append("FORGET ALL DEVICES")
        else:
            items.append("No trusted devices")

        selection = menus.render_menu_list(
            "TRUSTED DEVICES",
            items,
            header_lines=["Manage trusted devices"],
            transition_direction="forward",
        )

        if selection is None:
            break

        selected = items[selection]

        if selected == auto_label:
            # Toggle auto-reconnect
            set_bluetooth_auto_reconnect(not auto_reconnect)
            screens.render_status_template(
                "AUTO-RECONNECT",
                "Enabled" if not auto_reconnect else "Disabled",
            )
            time.sleep(1)

        elif selected == "FORGET ALL DEVICES":
            # Confirm before clearing
            confirmed = screens.render_confirmation_screen(
                "FORGET ALL?",
                ["Remove all trusted", "Bluetooth devices?"],
            )
            if confirmed == "YES":
                forget_all_bluetooth_devices()
                screens.render_status_template("TRUSTED DEVICES", "All devices forgotten")
                time.sleep(1.5)

        elif "(" in selected and ")" in selected and "--" not in selected:
            # Selected a device - offer to forget it
            # Extract MAC from the display string
            device_idx = selection - 2  # Account for header and separator
            if 0 <= device_idx < len(devices):
                device = devices[device_idx]
                mac = device.get("mac", "")
                name = device.get("name", "Unknown")

                confirmed = screens.render_confirmation_screen(
                    "FORGET DEVICE?",
                    [f"Remove {name}?"],
                )
                if confirmed == "YES":
                    remove_trusted_bluetooth_device(mac)
                    screens.render_status_template("TRUSTED DEVICES", f"Forgot {name}")
                    time.sleep(1.5)


def bluetooth_trust_current() -> None:
    """Trust the currently connected Bluetooth device."""
    from rpi_usb_cloner.services.bluetooth import (
        get_bluetooth_status,
        trust_current_bluetooth_device,
    )

    status = get_bluetooth_status()
    if not status.connected:
        screens.render_status_template("BLUETOOTH", "No device connected")
        time.sleep(1.5)
        return

    if trust_current_bluetooth_device():
        screens.render_status_template("BLUETOOTH", "Device trusted")
    else:
        screens.render_status_template("BLUETOOTH", "Trust failed")
    time.sleep(1.5)
