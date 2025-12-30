import argparse
import os
import time
from datetime import datetime, timedelta

from rpi_usb_cloner.actions import drive_actions, image_actions, settings_actions, tools_actions
from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.storage import devices
from rpi_usb_cloner.storage.mount import get_device_name, get_model, get_size, get_vendor, list_media_devices
from rpi_usb_cloner.storage.clone import configure_clone_helpers
from rpi_usb_cloner.ui import display, renderer
from rpi_usb_cloner.menu import MenuItem, definitions, navigator


def main(argv=None):
    parser = argparse.ArgumentParser(description="Raspberry Pi USB Cloner")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable verbose debug output")
    args = parser.parse_args(argv)
    debug_enabled = args.debug
    clone_mode = os.environ.get("CLONE_MODE", "smart").lower()

    def log_debug(message):
        if debug_enabled:
            print(f"[DEBUG] {message}")

    gpio.setup_gpio()
    context = display.init_display()
    display.set_display_context(context)
    display.configure_display_helpers(log_debug=log_debug)
    devices.configure_device_helpers(log_debug=log_debug, error_handler=display.display_lines)
    configure_clone_helpers(log_debug=log_debug)

    state = app_state.AppState()
    visible_rows = 4
    def get_selected_usb_name():
        devices_list = list_media_devices()
        if not devices_list:
            return None
        if state.usb_list_index >= len(devices_list):
            state.usb_list_index = max(len(devices_list) - 1, 0)
        device = devices_list[state.usb_list_index]
        return get_device_name(device)

    def get_usb_snapshot():
        try:
            devices_list = list_media_devices()
        except Exception as error:
            log_debug(f"Failed to list media devices: {error}")
            return []
        snapshot = sorted(get_device_name(device) for device in devices_list)
        log_debug(f"USB snapshot: {snapshot}")
        return snapshot

    def get_device_items():
        devices_list = list_media_devices()
        items = []
        for device in devices_list:
            label = f"{get_device_name(device)} {get_size(device) / 1024 ** 3:.2f}GB"
            items.append(MenuItem(label=label, next_screen=definitions.ACTIONS_MENU.screen_id))
        if not items:
            items.append(MenuItem(label="NO USB DEVICES"))
        return items

    def get_device_status_line():
        devices_list = list_media_devices()
        if not devices_list:
            return "INSERT USB"
        selected_name = get_selected_usb_name()
        for device in devices_list:
            if get_device_name(device) == selected_name:
                vendor = (get_vendor(device) or "").strip()
                model = (get_model(device) or "").strip()
                label = " ".join(part for part in [vendor, model] if part)
                return label or selected_name
        return "USB DEVICES"

    menu_navigator = navigator.MenuNavigator(
        screens=definitions.SCREENS,
        root_screen_id=definitions.MAIN_MENU.screen_id,
        items_providers={definitions.MAIN_MENU.screen_id: get_device_items},
    )

    def render_current_screen():
        menu_navigator.sync_visible_rows(visible_rows)
        current_screen = menu_navigator.current_screen()
        if current_screen.screen_id == definitions.MAIN_MENU.screen_id:
            state.usb_list_index = menu_navigator.current_state().selected_index
        items = [item.label for item in menu_navigator.current_items()]
        status_line = current_screen.status_line
        if current_screen.screen_id == definitions.MAIN_MENU.screen_id:
            status_line = get_device_status_line()
        elif current_screen.screen_id == definitions.ACTIONS_MENU.screen_id:
            selected_name = get_selected_usb_name() or "NO USB"
            status_line = f"USB: {selected_name}"
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
            get_selected_usb_name=get_selected_usb_name,
        ),
        "drive.info": lambda: drive_actions.drive_info(
            state=state,
            log_debug=log_debug,
            get_selected_usb_name=get_selected_usb_name,
        ),
        "drive.erase": lambda: drive_actions.erase_drive(
            state=state,
            log_debug=log_debug,
            get_selected_usb_name=get_selected_usb_name,
        ),
        "image.coming_soon": image_actions.coming_soon,
        "tools.coming_soon": tools_actions.coming_soon,
        "settings.coming_soon": settings_actions.coming_soon,
    }

    def run_action(action):
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

    render_current_screen()
    state.last_usb_check = time.time()
    state.last_seen_devices = get_usb_snapshot()
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
                if current_devices != state.last_seen_devices:
                    log_debug(f"USB devices changed: {state.last_seen_devices} -> {current_devices}")
                    selected_name = None
                    if state.last_seen_devices and state.usb_list_index < len(state.last_seen_devices):
                        selected_name = state.last_seen_devices[state.usb_list_index]
                    if selected_name and selected_name in current_devices:
                        state.usb_list_index = current_devices.index(selected_name)
                    else:
                        state.usb_list_index = min(state.usb_list_index, max(len(current_devices) - 1, 0))
                    menu_navigator.set_selection(definitions.MAIN_MENU.screen_id, state.usb_list_index, visible_rows)
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
