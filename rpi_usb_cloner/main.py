"""Main application entry point and event loop for Rpi-USB-Cloner.

This module implements the main event loop for the USB cloning application, handling:
- Hardware initialization (GPIO, OLED display)
- Menu navigation and user input via GPIO buttons
- USB device detection and monitoring
- Screensaver activation on idle timeout
- Application state management

Architecture Overview:
    The application follows an event-driven architecture with a main polling loop that:

    1. Polls GPIO buttons for user input (every INPUT_POLL_INTERVAL)
    2. Checks for USB device changes (every USB_REFRESH_INTERVAL)
    3. Handles screensaver activation after idle timeout
    4. Dispatches actions based on menu selections
    5. Updates OLED display with current state

    The loop is complex (~167 lines, lines 328-494) and handles:
    - Button repeat logic for smooth navigation
    - USB hotplug detection
    - Menu state management
    - Screen rendering coordination

Button Mapping:
    UP/DOWN:    Navigate menu items (with repeat for fast scrolling)
    LEFT:       Go back in menu hierarchy
    RIGHT:      Activate/enter selected menu item
    A:          Back/Cancel (same as LEFT)
    B:          Select/Confirm current item (same as RIGHT)
    C:          Context-specific action (varies by screen)

Command Line Arguments:
    --debug (-d):               Enable verbose debug logging to console
    --trace (-t):               Enable ultra-verbose trace logging (button presses,
                               WebSocket events, cache operations, etc.)
    --restore-partition-mode:   Set Clonezilla partition mode (k0/k/k1/k2)
                               for image restoration operations

Application Flow:
    1. Parse arguments
    2. Initialize hardware (GPIO pins, I2C OLED display)
    3. Configure logging and error handlers
    4. Load persisted settings from ~/.config/rpi-usb-cloner/settings.json
    5. Build menu structure with device-specific actions
    6. Enter main event loop (runs until Ctrl+C or system shutdown)
    7. Cleanup GPIO and display on exit

State Management:
    - AppContext: Stores runtime state (discovered drives, active drive, etc.)
    - AppState: Configuration and timing values (intervals, timeouts)
    - MenuNavigator: Tracks current menu position and history
    - Settings: Persistent configuration (screensaver, WiFi, etc.)

Device Monitoring:
    USB devices are polled every 2 seconds (USB_REFRESH_INTERVAL). When devices
    change:
    - Menu items are rebuilt to reflect current drives
    - Active drive selection is preserved if still present
    - Display is updated to show new device list

Screensaver:
    After SCREENSAVER_TIMEOUT seconds of inactivity:
    - Random or configured GIF is displayed on OLED
    - Any button press wakes display
    - If no GIFs available, shows blank screen
    - Timer resets on any user interaction

Error Handling:
    - Uncaught exceptions displayed on OLED as "ERROR"
    - GPIO cleanup ensured via try/finally
    - Display cleared on abnormal exit

Performance Notes:
    - Main loop runs with 100ms sleep (INPUT_POLL_INTERVAL)
    - Button repeat starts after 0.5s initial delay
    - Repeat interval is 0.1s for smooth scrolling
    - USB polling at 2s intervals keeps CPU usage low

Example Usage:
    $ sudo -E python3 rpi-usb-cloner.py
    $ sudo -E python3 rpi-usb-cloner.py --debug
    $ sudo -E python3 rpi-usb-cloner.py --restore-partition-mode k0

Security Considerations:
    - Must run as root for disk operations
    - No device validation before destructive operations
    - Settings file not validated or sandboxed
    - GPIO cleanup not guaranteed on hard crashes

See Also:
    - rpi_usb_cloner.storage.clone: Cloning operations
    - rpi_usb_cloner.menu.definitions: Menu structure
    - rpi_usb_cloner.hardware.gpio: Button input handling
"""

import argparse
import os
import time
from datetime import datetime
from functools import partial
from typing import Any, Generator, Optional

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.app.drive_info import get_device_status_line, render_drive_info
from rpi_usb_cloner.app.menu_builders import (
    build_connectivity_items,
    build_develop_items,
    build_device_items,
    build_display_items,
    build_screensaver_items,
    build_status_bar_items,
)
from rpi_usb_cloner.config import settings as settings_store
from rpi_usb_cloner.config.settings import (
    DEFAULT_TRANSITION_FRAME_COUNT,
    DEFAULT_TRANSITION_FRAME_DELAY,
)
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.logging import get_logger, setup_logging
from rpi_usb_cloner.menu import actions as menu_actions
from rpi_usb_cloner.menu import definitions, navigator
from rpi_usb_cloner.menu.model import get_screen_icon
from rpi_usb_cloner.services import drives, wifi
from rpi_usb_cloner.services.drives import list_usb_disks_filtered
from rpi_usb_cloner.storage import devices
from rpi_usb_cloner.storage.format import configure_format_helpers
from rpi_usb_cloner.ui import (
    display,
    menus,
    renderer,
    screens,
    screensaver,
    transitions,
)
from rpi_usb_cloner.ui.constants import (
    BUTTON_POLL_DELAY,
    INITIAL_REPEAT_DELAY,
    REPEAT_INTERVAL,
)
from rpi_usb_cloner.web import server as web_server


# Wrapper functions to adapt device dict interface from list_usb_disks()
# to the interface expected by drive_info.py functions
def get_device_name_from_dict(device: dict) -> str:
    """Extract device name from device dict."""
    return device.get("name", "")


def get_size_from_dict(device: dict) -> int:
    """Extract size in bytes from device dict."""
    return device.get("size", 0)


def get_vendor_from_dict(device: dict) -> str:
    """Extract vendor from device dict."""
    return device.get("vendor", "")


def get_model_from_dict(device: dict) -> str:
    """Extract model from device dict."""
    return device.get("model", "")


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Raspberry Pi USB Cloner")
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable verbose debug output"
    )
    parser.add_argument(
        "-t",
        "--trace",
        action="store_true",
        help="Enable ultra-verbose trace logging (includes button presses, WebSocket events, etc.)",
    )
    parser.add_argument(
        "--restore-partition-mode",
        choices=["k0", "k", "k1", "k2"],
        help="Partition table restore mode (k0, k, k1, k2)",
    )
    parser.add_argument(
        "-k",
        dest="restore_partition_mode",
        action="store_const",
        const="k",
        help="Restore without creating a partition table",
    )
    parser.add_argument(
        "-k0",
        dest="restore_partition_mode",
        action="store_const",
        const="k0",
        help="Restore using the source partition table",
    )
    parser.add_argument(
        "-k1",
        dest="restore_partition_mode",
        action="store_const",
        const="k1",
        help="Restore with proportional partition table for larger disks",
    )
    parser.add_argument(
        "-k2",
        dest="restore_partition_mode",
        action="store_const",
        const="k2",
        help="Restore after manual partition table creation",
    )
    args = parser.parse_args(argv)
    debug_enabled = args.debug
    trace_enabled = args.trace
    if args.restore_partition_mode:
        settings_store.set_setting(
            "restore_partition_mode", args.restore_partition_mode
        )
    clone_mode = os.environ.get("CLONE_MODE", "smart").lower()

    app_context = AppContext()
    setup_logging(app_context, debug=debug_enabled, trace=trace_enabled)

    # Use LoggerFactory for structured logging
    from rpi_usb_cloner.logging import LoggerFactory

    log = LoggerFactory.for_system()

    # Log startup with context
    log.info(
        "Application starting",
        debug=debug_enabled,
        trace=trace_enabled,
        clone_mode=clone_mode,
        restore_partition_mode=settings_store.get_setting(
            "restore_partition_mode", "k0"
        ),
    )

    def log_debug(
        message: Any,
        *,
        level: str = "debug",
        tags: Optional[list[str]] = None,
        timestamp: Optional[float] = None,
        source: Optional[str] = None,
    ) -> None:
        message_text = message.message if hasattr(message, "message") else message
        logger = get_logger(tags=tags, source=source or "APP")
        logger.log(str(level).upper(), message_text)

    gpio.setup_gpio()
    context = display.init_display()
    display.set_display_context(context)
    app_context.display = context

    # Check web server enabled setting (default: False for new installations)
    # Environment variable WEB_SERVER_ENABLED can override the setting
    web_server_enabled_setting = settings_store.get_bool(
        "web_server_enabled", default=False
    )
    web_server_env_override = os.environ.get("WEB_SERVER_ENABLED", None)

    web_log_debug = get_logger(tags=["web", "ws"], source="web").debug
    if web_server_env_override is not None:
        web_server_enabled = web_server_env_override.lower() not in {"0", "false", "no"}
        if web_server_enabled:
            web_log_debug(
                "Web server enabled via WEB_SERVER_ENABLED environment variable"
            )
        else:
            web_log_debug(
                "Web server disabled via WEB_SERVER_ENABLED environment variable"
            )
    else:
        web_server_enabled = web_server_enabled_setting

    if web_server_enabled:
        try:
            web_server.start_server(log_debug=web_log_debug, app_context=app_context)
        except OSError as error:
            web_log_debug(f"Web server failed to start: {error}")
    else:
        web_log_debug("Web server disabled in settings")

    usb_log_debug = partial(log_debug, tags=["usb"])
    devices.configure_device_helpers(
        log_debug=usb_log_debug, error_handler=display.display_lines
    )
    configure_format_helpers(
        log_debug=get_logger(tags=["format"], source="format").debug
    )
    wifi.configure_wifi_helpers(
        log_debug=get_logger(source="wifi").debug, error_handler=display.display_lines
    )

    state = app_state.AppState()
    app_state.screensaver_enabled = settings_store.get_bool(
        "screensaver_enabled",
        default=app_state.screensaver_enabled,
    )
    # Use batched USB snapshot for efficiency - single lsblk call
    last_batched_snapshot: drives.USBSnapshot | None = None

    def get_batched_usb_snapshot() -> drives.USBSnapshot:
        """Get USB device snapshot with single system call.

        Returns a USBSnapshot containing raw devices, media devices, and
        mountpoints in a single pass. Uses ~3x fewer system calls than
        separate functions.
        """
        try:
            snapshot = drives.get_usb_snapshot()
        except Exception as error:
            usb_log_debug(f"Failed to get USB snapshot: {error}")
            snapshot = drives.USBSnapshot(
                raw_devices=[], media_devices=[], mountpoints=[]
            )
        return snapshot

    def log_snapshot_changes(snapshot: drives.USBSnapshot) -> None:
        """Log changes in USB snapshot compared to last_batched_snapshot."""
        nonlocal last_batched_snapshot
        if snapshot.raw_devices != getattr(
            last_batched_snapshot, "raw_devices", None
        ):
            usb_log_debug(f"Raw USB snapshot: {snapshot.raw_devices}")
        if snapshot.mountpoints != getattr(
            last_batched_snapshot, "mountpoints", None
        ):
            usb_log_debug(f"USB mount snapshot: {snapshot.mountpoints}")
        if snapshot.media_devices != getattr(
            last_batched_snapshot, "media_devices", None
        ):
            usb_log_debug(f"USB snapshot: {snapshot.media_devices}")
        last_batched_snapshot = snapshot

    get_device_items = partial(
        build_device_items,
        drives,
        definitions.DRIVES_MENU,
        menu_actions,
    )
    get_connectivity_items = partial(
        build_connectivity_items,
        settings_store,
        menu_actions,
    )
    get_display_items = partial(
        build_display_items,
        settings_store,
        app_state,
        menu_actions,
    )
    get_develop_items = partial(
        build_develop_items,
        settings_store,
        menu_actions,
    )
    get_screensaver_items = partial(
        build_screensaver_items,
        settings_store,
        app_state,
        menu_actions,
    )
    get_status_bar_items = partial(
        build_status_bar_items,
        settings_store,
        menu_actions,
    )

    input_poll_interval = BUTTON_POLL_DELAY
    initial_repeat_delay = INITIAL_REPEAT_DELAY
    repeat_interval = REPEAT_INTERVAL

    def show_drive_info() -> None:
        page_index = 0
        total_pages, page_index = render_drive_info(
            app_context.active_drive,
            list_usb_disks_filtered,
            get_device_name_from_dict,
            get_size_from_dict,
            get_vendor_from_dict,
            get_model_from_dict,
            display,
            screens,
            page_index,
        )
        menus.wait_for_buttons_release(
            [gpio.PIN_A, gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D]
        )
        last_selected_name = app_context.active_drive
        prev_states = {
            "A": gpio.is_pressed(gpio.PIN_A),
            "L": gpio.is_pressed(gpio.PIN_L),
            "R": gpio.is_pressed(gpio.PIN_R),
            "U": gpio.is_pressed(gpio.PIN_U),
            "D": gpio.is_pressed(gpio.PIN_D),
        }
        while True:
            current_a = gpio.is_pressed(gpio.PIN_A)
            if not prev_states["A"] and current_a:
                return
            current_l = gpio.is_pressed(gpio.PIN_L)
            if not prev_states["L"] and current_l:
                page_index = max(0, page_index - 1)
                total_pages, page_index = render_drive_info(
                    app_context.active_drive,
                    list_usb_disks_filtered,
                    get_device_name_from_dict,
                    get_size_from_dict,
                    get_vendor_from_dict,
                    get_model_from_dict,
                    display,
                    screens,
                    page_index,
                )
            current_r = gpio.is_pressed(gpio.PIN_R)
            if not prev_states["R"] and current_r:
                page_index = min(total_pages - 1, page_index + 1)
                total_pages, page_index = render_drive_info(
                    app_context.active_drive,
                    list_usb_disks_filtered,
                    get_device_name_from_dict,
                    get_size_from_dict,
                    get_vendor_from_dict,
                    get_model_from_dict,
                    display,
                    screens,
                    page_index,
                )
            current_u = gpio.is_pressed(gpio.PIN_U)
            if not prev_states["U"] and current_u:
                page_index = max(0, page_index - 1)
                total_pages, page_index = render_drive_info(
                    app_context.active_drive,
                    list_usb_disks_filtered,
                    get_device_name_from_dict,
                    get_size_from_dict,
                    get_vendor_from_dict,
                    get_model_from_dict,
                    display,
                    screens,
                    page_index,
                )
            current_d = gpio.is_pressed(gpio.PIN_D)
            if not prev_states["D"] and current_d:
                page_index = min(total_pages - 1, page_index + 1)
                total_pages, page_index = render_drive_info(
                    app_context.active_drive,
                    list_usb_disks_filtered,
                    get_device_name_from_dict,
                    get_size_from_dict,
                    get_vendor_from_dict,
                    get_model_from_dict,
                    display,
                    screens,
                    page_index,
                )
            current_selected_name = app_context.active_drive
            if current_selected_name != last_selected_name:
                page_index = 0
                total_pages, page_index = render_drive_info(
                    app_context.active_drive,
                    list_usb_disks_filtered,
                    get_device_name_from_dict,
                    get_size_from_dict,
                    get_vendor_from_dict,
                    get_model_from_dict,
                    display,
                    screens,
                    page_index,
                )
                last_selected_name = current_selected_name
            prev_states["A"] = current_a
            prev_states["L"] = current_l
            prev_states["R"] = current_r
            prev_states["U"] = current_u
            prev_states["D"] = current_d
            time.sleep(input_poll_interval)

    menu_actions.set_action_context(
        menu_actions.ActionContext(
            app_context=app_context,
            clone_mode=clone_mode,
            state=state,
            log_debug=get_logger(source="actions").debug,
            get_selected_usb_name=lambda: app_context.active_drive,
            show_drive_info=show_drive_info,
        )
    )

    menu_navigator = navigator.MenuNavigator(
        screens=definitions.SCREENS,
        root_screen_id=definitions.MAIN_MENU.screen_id,
        items_providers={
            definitions.DRIVE_LIST_MENU.screen_id: get_device_items,
            definitions.CONNECTIVITY_MENU.screen_id: get_connectivity_items,
            definitions.DISPLAY_MENU.screen_id: get_display_items,
            definitions.DEVELOP_MENU.screen_id: get_develop_items,
            definitions.SCREENSAVER_MENU.screen_id: get_screensaver_items,
            definitions.STATUS_BAR_MENU.screen_id: get_status_bar_items,
        },
    )

    def get_screen_status_line(screen: Any) -> Optional[str]:
        status_line = screen.status_line
        active_drive_label = drives.get_active_drive_label(app_context.active_drive)
        if screen.screen_id == definitions.DRIVE_LIST_MENU.screen_id:
            return get_device_status_line(
                app_context.active_drive,
                list_usb_disks_filtered,
                get_device_name_from_dict,
                get_vendor_from_dict,
                get_model_from_dict,
            )
        # For all other screens, show custom status_line if set,
        # otherwise fall back to active drive label
        return status_line or active_drive_label or "NO DRIVE SELECTED"

    def get_visible_rows_for_screen(
        screen: Any, status_line: Optional[str] = None
    ) -> int:
        if status_line is None:
            status_line = get_screen_status_line(screen)
        return renderer.calculate_visible_rows(
            title=screen.title,
            title_icon=get_screen_icon(screen.screen_id),
            status_line=status_line,
        )

    last_render_state: dict[str, Optional[tuple[object, ...]]] = {"key": None}
    last_screen_id: dict[str, Optional[str]] = {"value": None}
    last_menu_state: dict[str, Optional[tuple[object, ...]]] = {"value": None}
    last_menu_activity_time = time.monotonic()

    def calculate_transition_frames() -> int:
        context = display.get_display_context()
        default_frames = max(8, min(24, context.width // 4))
        setting_value = settings_store.get_setting(
            "transition_frame_count", DEFAULT_TRANSITION_FRAME_COUNT
        )
        try:
            frames = int(setting_value)
        except (TypeError, ValueError):
            return default_frames
        return max(1, min(24, frames))

    def get_transition_frame_delay() -> float:
        setting_value = settings_store.get_setting(
            "transition_frame_delay", DEFAULT_TRANSITION_FRAME_DELAY
        )
        try:
            delay = float(setting_value)
        except (TypeError, ValueError):
            return DEFAULT_TRANSITION_FRAME_DELAY
        return max(0.0, delay)

    def render_current_screen(
        *,
        force: bool = False,
        now: float | None = None,
    ) -> None:
        nonlocal last_menu_activity_time
        if now is None:
            now = time.monotonic()
        current_screen = menu_navigator.current_screen()
        previous_screen_id = last_screen_id["value"]
        screen_changed = current_screen.screen_id != previous_screen_id
        if screen_changed:
            log_debug(
                f"Screen changed: {last_screen_id['value']} -> {current_screen.screen_id}"
            )
            last_screen_id["value"] = current_screen.screen_id
        if current_screen.screen_id == definitions.DRIVE_LIST_MENU.screen_id:
            state.usb_list_index = menu_navigator.current_state().selected_index
            app_context.active_drive = drives.select_active_drive(
                app_context.discovered_drives,
                state.usb_list_index,
            )
        current_items = menu_navigator.current_items()
        items = [item.label for item in current_items]
        status_line = get_screen_status_line(current_screen)
        dynamic_visible_rows = get_visible_rows_for_screen(current_screen, status_line)
        menu_navigator.sync_visible_rows(dynamic_visible_rows)
        current_state = menu_navigator.current_state()

        # Get selected item's submenu icon for preview (if applicable)
        selected_item_icon = None
        if current_items and 0 <= current_state.selected_index < len(current_items):
            selected_item = current_items[current_state.selected_index]
            if selected_item.submenu:
                selected_item_icon = get_screen_icon(selected_item.submenu.screen_id)
        current_menu_state = (
            current_screen.screen_id,
            current_state.selected_index,
            current_state.scroll_offset,
        )
        if current_menu_state != last_menu_state["value"]:
            last_menu_state["value"] = current_menu_state
            last_menu_activity_time = now
        render_key = (
            current_screen.screen_id,
            tuple(items),
            current_state.selected_index,
            current_state.scroll_offset,
            status_line,
            dynamic_visible_rows,
        )
        if force or render_key != last_render_state["key"]:
            navigation_action = (
                menu_navigator.consume_last_navigation_action()
                if screen_changed
                else None
            )
            if navigation_action is not None:
                last_menu_activity_time = now
            if screen_changed and navigation_action in {"forward", "back"}:
                from_image = display.get_display_context().image.copy()
                to_image = renderer.render_menu_image(
                    title=current_screen.title,
                    items=items,
                    selected_index=current_state.selected_index,
                    scroll_offset=current_state.scroll_offset,
                    status_line=status_line,
                    visible_rows=dynamic_visible_rows,
                    title_icon=get_screen_icon(current_screen.screen_id),
                    now=now,
                    last_activity_time=last_menu_activity_time,
                    app_context=app_context,
                    selected_item_icon=selected_item_icon,
                )
                context = display.get_display_context()
                footer_start, _ = renderer.calculate_footer_bounds(
                    status_line=status_line
                )
                dirty_region = (0, 0, context.width, footer_start)
                
                # Start non-blocking transition
                nonlocal active_transition, transition_next_frame_time
                active_transition = transitions.generate_slide_transition(
                    from_image=from_image,
                    to_image=to_image,
                    direction=navigation_action,
                    frame_count=calculate_transition_frames(),
                    dirty_region=dirty_region,
                    frame_delay=get_transition_frame_delay(),
                )
                # Advance to first frame and get next frame time
                try:
                    transition_next_frame_time = next(active_transition)
                except StopIteration:
                    # Transition completed immediately (e.g., frame_count=0)
                    active_transition = None
                    with display._display_lock:
                        context = display.get_display_context()
                        context.image.paste(to_image)
                        context.disp.display(context.image)
                        display.mark_display_dirty()
            else:
                renderer.render_menu_screen(
                    title=current_screen.title,
                    items=items,
                    selected_index=current_state.selected_index,
                    scroll_offset=current_state.scroll_offset,
                    status_line=status_line,
                    visible_rows=dynamic_visible_rows,
                    title_icon=get_screen_icon(current_screen.screen_id),
                    now=now,
                    last_activity_time=last_menu_activity_time,
                    app_context=app_context,
                    selected_item_icon=selected_item_icon,
                )
            last_render_state["key"] = render_key

    def handle_back() -> None:
        if app_context.operation_active and not app_context.allow_back_interrupt:
            # Silently ignore back when operation is active
            return
        # Silently ignore if already at root
        menu_navigator.back()

    def cleanup_display(clear_display: bool = True) -> None:
        if clear_display:
            context.disp.clear()
        gpio.cleanup()

    app_context.discovered_drives = drives.list_media_drive_names()
    app_context.active_drive = drives.select_active_drive(
        app_context.discovered_drives,
        state.usb_list_index,
    )
    render_current_screen(force=True, now=time.monotonic())
    state.last_usb_check = time.time()
    state.last_seen_devices = list(app_context.discovered_drives)
    # Initialize batched snapshot
    _initial_snapshot = get_batched_usb_snapshot()
    state.last_seen_raw_devices = _initial_snapshot.raw_devices
    state.last_seen_mount_snapshot = _initial_snapshot.mountpoints
    prev_states = {
        "U": gpio.is_pressed(gpio.PIN_U),
        "D": gpio.is_pressed(gpio.PIN_D),
        "L": gpio.is_pressed(gpio.PIN_L),
        "R": gpio.is_pressed(gpio.PIN_R),
        "A": gpio.is_pressed(gpio.PIN_A),
        "B": gpio.is_pressed(gpio.PIN_B),
        "C": gpio.is_pressed(gpio.PIN_C),
    }
    repeat_state = {
        "U": {"next_repeat": None},
        "D": {"next_repeat": None},
    }
    screensaver_active = False

    # Non-blocking transition state
    active_transition: Generator[float, None, None] | None = None
    transition_next_frame_time: float = 0.0

    def any_button_pressed() -> bool:
        return any(gpio.is_pressed(pin) for pin in gpio.PINS)

    error_displayed = False
    try:
        while True:
            # Handle non-blocking animation transitions first
            if active_transition is not None:
                now = time.monotonic()
                if now >= transition_next_frame_time:
                    try:
                        transition_next_frame_time = next(active_transition)
                    except StopIteration:
                        # Transition complete - finalize with to_image
                        active_transition = None
                        # Final frame already displayed by generator, just need
                        # to ensure we have the complete to_image in context
                # Skip other processing during animation to maintain frame timing
                # Small sleep to prevent busy-wait
                time.sleep(0.001)
                continue

            render_requested = False
            force_render = False
            now = time.monotonic()
            if time.time() - state.last_usb_check >= app_state.USB_REFRESH_INTERVAL:
                # Use batched snapshot for efficiency (single lsblk call)
                # First pass: get raw/mount info to detect changes
                usb_snapshot = get_batched_usb_snapshot()
                raw_devices = usb_snapshot.raw_devices
                mount_snapshot = usb_snapshot.mountpoints

                # Check for changes and invalidate cache BEFORE using media_devices
                # This ensures repo filtering uses fresh cache
                cache_invalidated = False
                if raw_devices != state.last_seen_raw_devices:
                    log_debug(
                        f"Raw USB devices changed: {state.last_seen_raw_devices} -> {raw_devices}"
                    )
                    drives.invalidate_repo_cache()
                    cache_invalidated = True
                    state.last_seen_raw_devices = raw_devices
                if mount_snapshot != state.last_seen_mount_snapshot:
                    log_debug(
                        "USB mountpoints changed: "
                        f"{state.last_seen_mount_snapshot} -> {mount_snapshot}"
                    )
                    drives.invalidate_repo_cache()
                    cache_invalidated = True
                    state.last_seen_mount_snapshot = mount_snapshot

                # If cache was invalidated, get fresh media_devices
                # Otherwise use the media_devices from first snapshot
                if cache_invalidated:
                    # Get fresh snapshot with updated cache
                    usb_snapshot = get_batched_usb_snapshot()

                # Log all changes now that we have final snapshot
                log_snapshot_changes(usb_snapshot)
                current_devices = usb_snapshot.media_devices

                if current_devices != app_context.discovered_drives:
                    log_debug(
                        f"Checking USB devices (interval {app_state.USB_REFRESH_INTERVAL}s)"
                    )
                    log_debug(
                        f"USB devices changed: {app_context.discovered_drives} -> {current_devices}"
                    )
                    # Invalidate repo cache when USB devices change to avoid stale data
                    drives.invalidate_repo_cache()
                    selected_name = None
                    if app_context.discovered_drives and state.usb_list_index < len(
                        app_context.discovered_drives
                    ):
                        selected_name = app_context.discovered_drives[
                            state.usb_list_index
                        ]
                    if selected_name and selected_name in current_devices:
                        state.usb_list_index = current_devices.index(selected_name)
                    else:
                        state.usb_list_index = min(
                            state.usb_list_index, max(len(current_devices) - 1, 0)
                        )
                    main_screen = definitions.SCREENS[definitions.MAIN_MENU.screen_id]
                    main_visible_rows = get_visible_rows_for_screen(main_screen)
                    menu_navigator.set_selection(
                        definitions.MAIN_MENU.screen_id,
                        state.usb_list_index,
                        main_visible_rows,
                    )
                    app_context.discovered_drives = current_devices
                    app_context.active_drive = drives.select_active_drive(
                        app_context.discovered_drives,
                        state.usb_list_index,
                    )
                    state.last_seen_devices = current_devices
                    render_requested = True
                state.last_usb_check = time.time()
            if app_state.screensaver_enabled and not screensaver_active:
                idle_seconds = (datetime.now() - state.lcdstart).total_seconds()
                if idle_seconds >= app_state.SCREENSAVER_TIMEOUT:
                    screensaver_active = True
                    screensaver_mode = settings_store.get_setting(
                        "screensaver_mode", "random"
                    )
                    screensaver_gif = settings_store.get_setting("screensaver_gif")
                    screensaver_ran = screensaver.play_screensaver(
                        context,
                        selected_gif=screensaver_gif,
                        screensaver_mode=screensaver_mode,
                        input_checker=any_button_pressed,
                    )
                    if not screensaver_ran:
                        display.clear_display()
                        while not any_button_pressed():
                            time.sleep(input_poll_interval)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                    prev_states = {
                        "U": gpio.is_pressed(gpio.PIN_U),
                        "D": gpio.is_pressed(gpio.PIN_D),
                        "L": gpio.is_pressed(gpio.PIN_L),
                        "R": gpio.is_pressed(gpio.PIN_R),
                        "A": gpio.is_pressed(gpio.PIN_A),
                        "B": gpio.is_pressed(gpio.PIN_B),
                        "C": gpio.is_pressed(gpio.PIN_C),
                    }
                    render_current_screen(force=True, now=time.monotonic())
                    screensaver_active = False
                    continue

            current_states = {
                "U": gpio.is_pressed(gpio.PIN_U),
                "D": gpio.is_pressed(gpio.PIN_D),
                "L": gpio.is_pressed(gpio.PIN_L),
                "R": gpio.is_pressed(gpio.PIN_R),
                "A": gpio.is_pressed(gpio.PIN_A),
                "B": gpio.is_pressed(gpio.PIN_B),
                "C": gpio.is_pressed(gpio.PIN_C),
            }
            app_context.input_state = current_states
            button_pressed = False
            current_screen = menu_navigator.current_screen()
            status_line = get_screen_status_line(current_screen)
            dynamic_visible_rows = get_visible_rows_for_screen(
                current_screen, status_line
            )

            def handle_repeat_button(
                key: str,
                direction: int,
                *,
                current_states=current_states,
                prev_states=prev_states,
                dynamic_visible_rows=dynamic_visible_rows,
                now=now,
            ) -> None:
                nonlocal button_pressed, render_requested
                is_pressed = current_states[key]
                was_pressed = prev_states[key]
                if is_pressed and not was_pressed:
                    menu_navigator.move_selection(direction, dynamic_visible_rows)
                    button_pressed = True
                    render_requested = True
                    repeat_state[key]["next_repeat"] = now + initial_repeat_delay
                    return
                if (
                    is_pressed
                    and repeat_state[key]["next_repeat"] is not None
                    and now >= repeat_state[key]["next_repeat"]
                ):
                    menu_navigator.move_selection(direction, dynamic_visible_rows)
                    button_pressed = True
                    render_requested = True
                    repeat_state[key]["next_repeat"] = now + repeat_interval
                    return
                if not is_pressed:
                    repeat_state[key]["next_repeat"] = None

            handle_repeat_button("U", -1)
            handle_repeat_button("D", 1)
            if not prev_states["L"] and current_states["L"]:
                handle_back()
                button_pressed = True
                render_requested = True
            if not prev_states["A"] and current_states["A"]:
                handle_back()
                button_pressed = True
                render_requested = True
            if not prev_states["R"] and current_states["R"]:
                action = menu_navigator.activate(dynamic_visible_rows)
                if action:
                    action()
                    force_render = True
                    # Update button states after action to prevent double-handling of button presses
                    current_states = {
                        "U": gpio.is_pressed(gpio.PIN_U),
                        "D": gpio.is_pressed(gpio.PIN_D),
                        "L": gpio.is_pressed(gpio.PIN_L),
                        "R": gpio.is_pressed(gpio.PIN_R),
                        "A": gpio.is_pressed(gpio.PIN_A),
                        "B": gpio.is_pressed(gpio.PIN_B),
                        "C": gpio.is_pressed(gpio.PIN_C),
                    }
                    prev_states = current_states.copy()
                button_pressed = True
                render_requested = True
            if not prev_states["B"] and current_states["B"]:
                action = menu_navigator.activate(dynamic_visible_rows)
                if action:
                    action()
                    force_render = True
                    # Update button states after action to prevent double-handling of button presses
                    current_states = {
                        "U": gpio.is_pressed(gpio.PIN_U),
                        "D": gpio.is_pressed(gpio.PIN_D),
                        "L": gpio.is_pressed(gpio.PIN_L),
                        "R": gpio.is_pressed(gpio.PIN_R),
                        "A": gpio.is_pressed(gpio.PIN_A),
                        "B": gpio.is_pressed(gpio.PIN_B),
                        "C": gpio.is_pressed(gpio.PIN_C),
                    }
                    prev_states = current_states.copy()
                button_pressed = True
                render_requested = True
            if not prev_states["C"] and current_states["C"]:
                button_pressed = True
                if settings_store.get_bool("screenshots_enabled", default=False):
                    screenshot_path = display.capture_screenshot()
                    if screenshot_path:
                        screens.render_status_template(
                            "SCREENSHOT", f"Saved to {screenshot_path.name}"
                        )
                        time.sleep(1.5)
                        force_render = True
                        render_requested = True
                else:
                    render_requested = True

            if button_pressed:
                last_menu_activity_time = now
                state.lcdstart = datetime.now()
                state.run_once = 0

            prev_states = current_states
            if render_requested:
                render_current_screen(force=force_render, now=now)

            # Sleep at end of loop to minimize latency for next button press
            time.sleep(input_poll_interval)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        # Log critical crash to all sinks (console, files, Web UI)
        crash_log = get_logger(tags=["crash", "fatal"], source="main")
        crash_log.critical(
            f"Application crash: {type(error).__name__}",
            error_type=type(error).__name__,
            error_message=str(error),
            error_traceback=str(error.__traceback__),
        )
        # Also print to stderr for immediate visibility
        print(f"An error occurred: {type(error).__name__}")
        print(str(error))
        error_displayed = True
        context.disp.clear()
        context.draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        context.draw.text(
            (context.x, context.top + 30), "ERROR", font=context.fontinsert, fill=255
        )
        context.disp.display(context.image)
    finally:
        cleanup_display(clear_display=not error_displayed)


if __name__ == "__main__":
    main()
