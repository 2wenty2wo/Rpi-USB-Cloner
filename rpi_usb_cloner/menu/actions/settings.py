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


def screensaver_settings() -> None:
    settings_actions.screensaver_settings()


def toggle_screensaver_enabled() -> None:
    settings_actions.toggle_screensaver_enabled()


def toggle_screensaver_mode() -> None:
    settings_actions.toggle_screensaver_mode()


def select_screensaver_gif() -> None:
    settings_actions.select_screensaver_gif()


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


def toggle_web_server() -> None:
    context = get_action_context()
    settings_actions.toggle_web_server(
        app_context=context.app_context,
        log_debug=context.log_debug,
    )


def toggle_menu_view_mode() -> None:
    settings_actions.toggle_menu_view_mode()


def update_version() -> None:
    context = get_action_context()
    _run_operation(lambda: settings_actions.update_version(log_debug=context.log_debug))


def restart_service() -> None:
    context = get_action_context()
    _run_operation(
        lambda: settings_actions.restart_service(log_debug=context.log_debug)
    )


def stop_service() -> None:
    context = get_action_context()
    _run_operation(lambda: settings_actions.stop_service(log_debug=context.log_debug))


def restart_system() -> None:
    context = get_action_context()
    _run_operation(lambda: settings_actions.restart_system(log_debug=context.log_debug))


def shutdown_system() -> None:
    context = get_action_context()
    _run_operation(
        lambda: settings_actions.shutdown_system(log_debug=context.log_debug)
    )


def show_about_credits() -> None:
    """Display the ABOUT/credits screen.

    Shows credits.png from ui/assets and waits for user to press back/OK.
    Re-exports from: rpi_usb_cloner.actions.settings.ui_actions.show_about_credits
    """
    settings_actions.show_about_credits()
