"""Settings and configuration menu actions."""

from __future__ import annotations

from rpi_usb_cloner.actions import settings_actions

from . import get_action_context


def _run_operation(action, *, allow_back_interrupt: bool = False) -> None:
    context = get_action_context()
    context.app_context.operation_active = True
    context.app_context.allow_back_interrupt = allow_back_interrupt
    try:
        action()
    finally:
        context.app_context.operation_active = False
        context.app_context.allow_back_interrupt = False


def settings_coming_soon() -> None:
    settings_actions.coming_soon()


def wifi_settings() -> None:
    settings_actions.wifi_settings()


def select_restore_partition_mode() -> None:
    settings_actions.select_restore_partition_mode()


def select_transition_speed() -> None:
    settings_actions.select_transition_speed()


def screensaver_settings() -> None:
    settings_actions.screensaver_settings()


def toggle_screensaver_enabled() -> None:
    settings_actions.toggle_screensaver_enabled()


def toggle_screensaver_mode() -> None:
    settings_actions.toggle_screensaver_mode()


def select_screensaver_gif() -> None:
    settings_actions.select_screensaver_gif()


def preview_screensaver() -> None:
    settings_actions.preview_screensaver()


def keyboard_test() -> None:
    settings_actions.keyboard_test()


def demo_confirmation_screen() -> None:
    settings_actions.demo_confirmation_screen()


def demo_status_screen() -> None:
    settings_actions.demo_status_screen()


def demo_info_screen() -> None:
    settings_actions.demo_info_screen()


def demo_progress_screen() -> None:
    settings_actions.demo_progress_screen()


def lucide_demo() -> None:
    settings_actions.lucide_demo()


def heroicons_demo() -> None:
    settings_actions.heroicons_demo()


def preview_title_font() -> None:
    settings_actions.preview_title_font()


def toggle_screenshots() -> None:
    settings_actions.toggle_screenshots()


def toggle_menu_icon_preview() -> None:
    settings_actions.toggle_menu_icon_preview()


def toggle_web_server() -> None:
    context = get_action_context()
    settings_actions.toggle_web_server(
        app_context=context.app_context,
    )


def update_version() -> None:
    _run_operation(lambda: settings_actions.update_version())


def restart_service() -> None:
    _run_operation(lambda: settings_actions.restart_service())


def stop_service() -> None:
    _run_operation(lambda: settings_actions.stop_service())


def restart_system() -> None:
    _run_operation(lambda: settings_actions.restart_system())


def shutdown_system() -> None:
    _run_operation(lambda: settings_actions.shutdown_system())


def show_about_credits() -> None:
    """Display the ABOUT/credits screen.

    Shows credits.png from ui/assets and waits for user to press back/OK.
    Re-exports from: rpi_usb_cloner.actions.settings.ui_actions.show_about_credits
    """
    settings_actions.show_about_credits()


# -----------------------------------------------------------------------------
# Status Bar Toggle Actions
# -----------------------------------------------------------------------------


def toggle_status_bar_enabled() -> None:
    """Toggle status bar visibility (master toggle)."""
    settings_actions.toggle_status_bar_enabled()


def toggle_status_bar_wifi() -> None:
    """Toggle WiFi icon visibility in status bar."""
    settings_actions.toggle_status_bar_wifi()


def toggle_status_bar_bluetooth() -> None:
    """Toggle Bluetooth icon visibility in status bar."""
    settings_actions.toggle_status_bar_bluetooth()


def toggle_status_bar_web() -> None:
    """Toggle Web Server icon visibility in status bar."""
    settings_actions.toggle_status_bar_web()


def toggle_status_bar_drives() -> None:
    """Toggle drive counts visibility in status bar."""
    settings_actions.toggle_status_bar_drives()


def bluetooth_settings() -> None:
    """Display Bluetooth settings screen."""
    settings_actions.bluetooth_settings()


def toggle_bluetooth_pan() -> None:
    """Toggle Bluetooth PAN mode on/off."""
    settings_actions.toggle_bluetooth_pan()


def show_bluetooth_qr() -> None:
    """Show Bluetooth pairing QR code."""
    settings_actions.show_bluetooth_qr()


def enable_bluetooth_pan() -> None:
    """Enable Bluetooth PAN mode."""
    settings_actions.enable_bluetooth_pan()


def disable_bluetooth_pan() -> None:
    """Disable Bluetooth PAN mode."""
    settings_actions.disable_bluetooth_pan()


def bluetooth_trusted_devices() -> None:
    """Show and manage trusted Bluetooth devices."""
    settings_actions.bluetooth_trusted_devices()


def bluetooth_trust_current() -> None:
    """Trust the currently connected Bluetooth device."""
    settings_actions.bluetooth_trust_current()
