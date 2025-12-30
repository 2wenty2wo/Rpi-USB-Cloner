import argparse
import os
import time
from datetime import datetime, timedelta

from rpi_usb_cloner.actions import drive_actions, image_actions, settings_actions, tools_actions
from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.services import drives
from rpi_usb_cloner.storage import devices
from rpi_usb_cloner.storage.mount import (
    get_device_name,
    get_model,
    get_size,
    get_vendor,
    list_media_devices,
)
from rpi_usb_cloner.storage.clone import configure_clone_helpers
from rpi_usb_cloner.ui import display, menus, renderer
from rpi_usb_cloner.menu import MenuItem, definitions, navigator


def main(argv=None):
    parser = argparse.ArgumentParser(description="Raspberry Pi USB Cloner")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable verbose debug output")
    args = parser.parse_args(argv)
    debug_enabled = args.debug
    clone_mode = os.environ.get("CLONE_MODE", "smart").lower()

    app_context = AppContext()

    def log_debug(message):
        app_context.add_log(message)
        if debug_enabled:
            print(f"[DEBUG] {message}")

    gpio.setup_gpio()
    context = display.init_display()
    display.set_display_context(context)
    app_context.display = context
    display.configure_display_helpers(log_debug=log_debug)
    devices.configure_device_helpers(log_debug=log_debug, error_handler=display.display_lines)
    configure_clone_helpers(log_debug=log_debug)

    state = app_state.AppState()
    visible_rows = 4
    def get_active_drive_name():
        return app_context.active_drive

    def get_usb_snapshot():
        try:
            devices_list = drives.list_media_drive_names()
        except Exception as error:
            log_debug(f"Failed to list media devices: {error}")
            return []
        snapshot = sorted(devices_list)
        log_debug(f"USB snapshot: {snapshot}")
        return snapshot

    def get_device_items():
        labels = drives.list_media_drive_labels()
        items = [
            MenuItem(label=label, next_screen=definitions.ACTIONS_MENU.screen_id)
            for label in labels
        ]
        if not items:
            items.append(MenuItem(label="NO USB DEVICES"))
        return items

    def get_device_status_line():
        devices_list = list_media_devices()
        if not devices_list:
            return "INSERT USB"
        selected_name = app_context.active_drive
        for device in devices_list:
            if get_device_name(device) == selected_name:
                vendor = (get_vendor(device) or "").strip()
                model = (get_model(device) or "").strip()
                label = " ".join(part for part in [vendor, model] if part)
                return label or selected_name
        return "NO DRIVE SELECTED"

    def render_drive_info(page_index: int) -> tuple[int, int]:
        selected_name = app_context.active_drive
        if not selected_name:
            display.display_lines(["NO DRIVE", "SELECTED"])
            return 1, 0
        device = None
        for candidate in list_media_devices():
            if get_device_name(candidate) == selected_name:
                device = candidate
                break
        if not device:
            display.display_lines(["NO DRIVE", "SELECTED"])
            return 1, 0
        size_gb = get_size(device) / 1024 ** 3
        vendor = (get_vendor(device) or "").strip()
        model = (get_model(device) or "").strip()
        info_lines = [f"{selected_name} {size_gb:.2f}GB"]
        if vendor or model:
            info_lines.append(" ".join(part for part in [vendor, model] if part))
        return display.render_paginated_lines(
            "DRIVE INFO",
            info_lines,
            page_index=page_index,
            title_font=display.get_display_context().fontcopy,
        )

    def show_drive_info() -> None:
        page_index = 0
        total_pages, page_index = render_drive_info(page_index)
        menus.wait_for_buttons_release([gpio.PIN_A, gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D])
        last_selected_name = app_context.active_drive
        prev_states = {
            "A": gpio.read_button(gpio.PIN_A),
            "L": gpio.read_button(gpio.PIN_L),
            "R": gpio.read_button(gpio.PIN_R),
            "U": gpio.read_button(gpio.PIN_U),
            "D": gpio.read_button(gpio.PIN_D),
        }
        while True:
            current_a = gpio.read_button(gpio.PIN_A)
            if prev_states["A"] and not current_a:
                return
            current_l = gpio.read_button(gpio.PIN_L)
            if prev_states["L"] and not current_l:
                page_index = max(0, page_index - 1)
                total_pages, page_index = render_drive_info(page_index)
            current_r = gpio.read_button(gpio.PIN_R)
            if prev_states["R"] and not current_r:
                page_index = min(total_pages - 1, page_index + 1)
                total_pages, page_index = render_drive_info(page_index)
            current_u = gpio.read_button(gpio.PIN_U)
            if prev_states["U"] and not current_u:
                page_index = max(0, page_index - 1)
                total_pages, page_index = render_drive_info(page_index)
            current_d = gpio.read_button(gpio.PIN_D)
            if prev_states["D"] and not current_d:
                page_index = min(total_pages - 1, page_index + 1)
                total_pages, page_index = render_drive_info(page_index)
            current_selected_name = app_context.active_drive
            if current_selected_name != last_selected_name:
                page_index = 0
                total_pages, page_index = render_drive_info(page_index)
                last_selected_name = current_selected_name
            prev_states["A"] = current_a
            prev_states["L"] = current_l
            prev_states["R"] = current_r
            prev_states["U"] = current_u
            prev_states["D"] = current_d
            time.sleep(0.05)

    menu_navigator = navigator.MenuNavigator(
        screens=definitions.SCREENS,
        root_screen_id=definitions.ACTIONS_MENU.screen_id,
        items_providers={definitions.MAIN_MENU.screen_id: get_device_items},
    )

    def render_current_screen():
        menu_navigator.sync_visible_rows(visible_rows)
        current_screen = menu_navigator.current_screen()
        if current_screen.screen_id == definitions.MAIN_MENU.screen_id:
            state.usb_list_index = menu_navigator.current_state().selected_index
            app_context.active_drive = drives.select_active_drive(
                app_context.discovered_drives,
                state.usb_list_index,
            )
        items = [item.label for item in menu_navigator.current_items()]
        status_line = current_screen.status_line
        active_drive_label = drives.get_active_drive_label(app_context.active_drive)
        if current_screen.screen_id == definitions.MAIN_MENU.screen_id:
            status_line = get_device_status_line()
        if active_drive_label:
            status_line = active_drive_label
        elif current_screen.screen_id == definitions.ACTIONS_MENU.screen_id:
            status_line = "NO DRIVE SELECTED"
        renderer.render_menu_screen(
            title=current_screen.title,
            items=items,
            selected_index=menu_navigator.current_state().selected_index,
            scroll_offset=menu_navigator.current_state().scroll_offset,
            status_line=status_line,
            visible_rows=visible_rows,
        )

    action_handlers = {
        "drive.copy": lambda: drive_actions.copy_drive(
            state=state,
            clone_mode=clone_mode,
            log_debug=log_debug,
            get_selected_usb_name=get_active_drive_name,
        ),
        "drive.info": show_drive_info,
        "drive.erase": lambda: drive_actions.erase_drive(
            state=state,
            log_debug=log_debug,
            get_selected_usb_name=get_active_drive_name,
        ),
        "image.coming_soon": image_actions.coming_soon,
        "tools.coming_soon": tools_actions.coming_soon,
        "settings.coming_soon": settings_actions.coming_soon,
    }

    def run_action(action):
        if action in {"drive.copy", "drive.info", "drive.erase"} and not app_context.active_drive:
            display.display_lines(["NO DRIVE", "SELECTED"])
            time.sleep(1)
            return
        handler = action_handlers.get(action)
        if handler:
            handler()
        else:
            log_debug(f"Unhandled action: {action}")

    def sleepdisplay():
        context.draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        context.disp.display(context.image)
        state.run_once = 1

    def cleanup_display(clear_display=True):
        if clear_display:
            context.disp.clear()
        gpio.cleanup()

    app_context.discovered_drives = drives.list_media_drive_names()
    app_context.active_drive = drives.select_active_drive(
        app_context.discovered_drives,
        state.usb_list_index,
    )
    render_current_screen()
    state.last_usb_check = time.time()
    state.last_seen_devices = list(app_context.discovered_drives)
    prev_states = {
        "U": gpio.read_button(gpio.PIN_U),
        "D": gpio.read_button(gpio.PIN_D),
        "L": gpio.read_button(gpio.PIN_L),
        "R": gpio.read_button(gpio.PIN_R),
        "A": gpio.read_button(gpio.PIN_A),
        "B": gpio.read_button(gpio.PIN_B),
        "C": gpio.read_button(gpio.PIN_C),
    }

    error_displayed = False
    try:
        while True:
            time.sleep(0.1)
            if time.time() - state.last_usb_check >= app_state.USB_REFRESH_INTERVAL:
                log_debug(f"Checking USB devices (interval {app_state.USB_REFRESH_INTERVAL}s)")
                current_devices = get_usb_snapshot()
                if current_devices != app_context.discovered_drives:
                    log_debug(
                        f"USB devices changed: {app_context.discovered_drives} -> {current_devices}"
                    )
                    selected_name = None
                    if (
                        app_context.discovered_drives
                        and state.usb_list_index < len(app_context.discovered_drives)
                    ):
                        selected_name = app_context.discovered_drives[state.usb_list_index]
                    if selected_name and selected_name in current_devices:
                        state.usb_list_index = current_devices.index(selected_name)
                    else:
                        state.usb_list_index = min(state.usb_list_index, max(len(current_devices) - 1, 0))
                    menu_navigator.set_selection(definitions.MAIN_MENU.screen_id, state.usb_list_index, visible_rows)
                    app_context.discovered_drives = current_devices
                    app_context.active_drive = drives.select_active_drive(
                        app_context.discovered_drives,
                        state.usb_list_index,
                    )
                    state.last_seen_devices = current_devices
                state.last_usb_check = time.time()
            if app_state.ENABLE_SLEEP:
                lcdtmp = state.lcdstart + timedelta(seconds=30)
                if datetime.now() > lcdtmp:
                    if state.run_once == 0:
                        sleepdisplay()
                    time.sleep(0.1)

            current_states = {
                "U": gpio.read_button(gpio.PIN_U),
                "D": gpio.read_button(gpio.PIN_D),
                "L": gpio.read_button(gpio.PIN_L),
                "R": gpio.read_button(gpio.PIN_R),
                "A": gpio.read_button(gpio.PIN_A),
                "B": gpio.read_button(gpio.PIN_B),
                "C": gpio.read_button(gpio.PIN_C),
            }
            app_context.input_state = current_states
            button_pressed = False

            if prev_states["U"] and not current_states["U"]:
                log_debug("Button UP pressed")
                menu_navigator.move_selection(-1, visible_rows)
                button_pressed = True
            if prev_states["D"] and not current_states["D"]:
                log_debug("Button DOWN pressed")
                menu_navigator.move_selection(1, visible_rows)
                button_pressed = True
            if prev_states["L"] and not current_states["L"]:
                log_debug("Button LEFT pressed")
                menu_navigator.back()
                button_pressed = True
            if prev_states["A"] and not current_states["A"]:
                log_debug("Button BACK pressed")
                menu_navigator.back()
                button_pressed = True
            if prev_states["R"] and not current_states["R"]:
                log_debug("Button RIGHT pressed")
                action = menu_navigator.activate(visible_rows)
                if action:
                    run_action(action)
                button_pressed = True
            if prev_states["B"] and not current_states["B"]:
                log_debug("Button SELECT pressed")
                action = menu_navigator.activate(visible_rows)
                if action:
                    run_action(action)
                button_pressed = True
            if prev_states["C"] and not current_states["C"]:
                log_debug("Button C pressed")
                button_pressed = True

            if button_pressed:
                state.lcdstart = datetime.now()
                state.run_once = 0

            prev_states = current_states
            render_current_screen()
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(f"An error occurred: {type(error).__name__}")
        print(str(error))
        error_displayed = True
        context.disp.clear()
        context.draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        context.draw.text((context.x, context.top + 30), "ERROR", font=context.fontinsert, fill=255)
        context.disp.display(context.image)
    finally:
        cleanup_display(clear_display=not error_displayed)


if __name__ == "__main__":
    main()
