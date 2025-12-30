import argparse
import os
import shutil
import time
from datetime import datetime, timedelta

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.storage import devices
from rpi_usb_cloner.storage.devices import (
    format_device_label,
    get_children,
    human_size,
    list_usb_disks,
)
from rpi_usb_cloner.storage.mount import get_device_name, get_model, get_size, get_vendor, list_media_devices
from rpi_usb_cloner.storage.clone import clone_device, configure_clone_helpers, erase_device
from rpi_usb_cloner.ui import display, menus, renderer
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

    def pick_source_target():
        devices_list = [device for device in list_usb_disks() if not devices.is_root_device(device)]
        if len(devices_list) < 2:
            return None, None
        devices_list = sorted(devices_list, key=lambda d: d.get("name", ""))
        selected_name = get_selected_usb_name()
        selected = None
        if selected_name:
            for device in devices_list:
                if device.get("name") == selected_name:
                    selected = device
                    break
        if selected:
            remaining = [device for device in devices_list if device.get("name") != selected_name]
            if not remaining:
                return None, None
            source = selected
            target = remaining[0]
        else:
            source = devices_list[0]
            target = devices_list[1]
        return source, target

    def ensure_root_for_erase():
        if os.geteuid() != 0:
            display.display_lines(["Run as root"])
            time.sleep(1)
            return False
        return True

    def build_device_info_lines(device, max_lines=None):
        lines = []
        header = format_device_label(device)
        vendor = (device.get("vendor") or "").strip()
        model = (device.get("model") or "").strip()
        vendor_model = " ".join(part for part in [vendor, model] if part)
        if vendor_model:
            header = f"{header} {vendor_model}"
        lines.append(header.strip())

        def append_line(line):
            if max_lines is not None and len(lines) >= max_lines:
                return False
            lines.append(line)
            return True

        for child in get_children(device):
            if max_lines is not None and len(lines) >= max_lines:
                break
            name = child.get("name") or ""
            fstype = child.get("fstype") or "raw"
            label = (child.get("label") or "").strip()
            mountpoint = child.get("mountpoint")
            label_suffix = f" {label}" if label else ""
            if not append_line(f"{name} {fstype}{label_suffix}".strip()):
                break
            if max_lines is not None and len(lines) >= max_lines:
                break
            if not mountpoint:
                append_line("mnt: not mounted")
                continue

            if not append_line(f"mnt:{mountpoint}"):
                break

            usage_label = "?"
            try:
                usage = shutil.disk_usage(mountpoint)
                usage_label = f"{human_size(usage.used)}/{human_size(usage.total)}"
            except (FileNotFoundError, PermissionError, OSError) as error:
                log_debug(f"Usage check failed for {mountpoint}: {error}")
                usage_label = "usage?"

            if not append_line(f"use:{usage_label}"):
                break

            try:
                entries = sorted(os.listdir(mountpoint))[:3]
                if entries:
                    if not append_line(f"files:{','.join(entries)}"):
                        break
            except (FileNotFoundError, PermissionError, OSError) as error:
                log_debug(f"Listdir failed for {mountpoint}: {error}")
                append_line("files?")

        if max_lines is not None and len(lines) > max_lines:
            return lines[:max_lines]
        return lines

    def view_devices(page_index=0):
        selected_name = get_selected_usb_name()
        if not selected_name:
            display.display_lines(["NO SELECTED USB"])
            return 1, 0
        devices_list = [device for device in list_usb_disks() if device.get("name") == selected_name]
        if not devices_list:
            display.display_lines(["NO SELECTED USB"])
            return 1, 0
        device = devices_list[0]
        lines = build_device_info_lines(device)
        return display.render_paginated_lines(
            "DRIVE INFO",
            lines,
            page_index=page_index,
            title_font=context.fontcopy,
        )

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

    def copy():
        source, target = pick_source_target()
        if not source or not target:
            display.display_lines(["COPY", "Need 2 USBs"])
            time.sleep(1)
            return
        source_name = source.get("name")
        target_name = target.get("name")
        title = f"CLONE {source_name} to {target_name}?"
        menu = menus.Menu(
            items=[],
            title=title,
            footer=["NO", "YES"],
            footer_positions=[context.x + 24, context.x + 52],
        )
        confirm_selection = app_state.CONFIRM_NO
        menu.footer_selected_index = confirm_selection
        menus.render_menu(menu, context.draw, context.width, context.height, context.fonts)
        context.disp.display(context.image)
        menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B, gpio.PIN_C])
        prev_states = {
            "L": gpio.read_button(gpio.PIN_L),
            "R": gpio.read_button(gpio.PIN_R),
            "A": gpio.read_button(gpio.PIN_A),
            "B": gpio.read_button(gpio.PIN_B),
            "C": gpio.read_button(gpio.PIN_C),
        }
        try:
            while True:
                current_R = gpio.read_button(gpio.PIN_R)
                if prev_states["R"] and not current_R:
                    if confirm_selection == app_state.CONFIRM_NO:
                        confirm_selection = app_state.CONFIRM_YES
                        log_debug("Copy menu selection changed: YES")
                        state.run_once = 0
                    elif confirm_selection == app_state.CONFIRM_YES:
                        confirm_selection = app_state.CONFIRM_YES
                        log_debug("Copy menu selection changed: YES")
                        state.lcdstart = datetime.now()
                        state.run_once = 0
                    else:
                        context.disp.display(context.image)
                        time.sleep(0.01)
                current_L = gpio.read_button(gpio.PIN_L)
                if prev_states["L"] and not current_L:
                    if confirm_selection == app_state.CONFIRM_YES:
                        confirm_selection = app_state.CONFIRM_NO
                        log_debug("Copy menu selection changed: NO")
                        state.lcdstart = datetime.now()
                        state.run_once = 0
                    else:
                        context.disp.display(context.image)
                        time.sleep(0.01)
                current_A = gpio.read_button(gpio.PIN_A)
                if prev_states["A"] and not current_A:
                    log_debug("Copy menu: Button A pressed")
                    return
                current_B = gpio.read_button(gpio.PIN_B)
                if prev_states["B"] and not current_B:
                    log_debug("Copy menu: Button B pressed")
                    if confirm_selection == app_state.CONFIRM_YES:
                        display.display_lines(["COPY", "Starting..."])
                        mode = menus.select_clone_mode(clone_mode)
                        if not mode:
                            return
                        display.display_lines(["COPY", mode.upper()])
                        if clone_device(source, target, mode=mode):
                            display.display_lines(["COPY", "Done"])
                        else:
                            log_debug("Copy failed")
                            display.display_lines(["COPY", "Failed"])
                        time.sleep(1)
                        return
                    if confirm_selection == app_state.CONFIRM_NO:
                        return
                current_C = gpio.read_button(gpio.PIN_C)
                if prev_states["C"] and not current_C:
                    log_debug("Copy menu: Button C pressed (ignored)")
                prev_states["R"] = current_R
                prev_states["L"] = current_L
                prev_states["B"] = current_B
                prev_states["A"] = current_A
                prev_states["C"] = current_C
                menu.footer_selected_index = confirm_selection
                menus.render_menu(menu, context.draw, context.width, context.height, context.fonts)
                context.disp.display(context.image)
        except KeyboardInterrupt:
            raise

    def view():
        page_index = 0
        total_pages, page_index = view_devices(page_index)
        menus.wait_for_buttons_release([gpio.PIN_A, gpio.PIN_L, gpio.PIN_R, gpio.PIN_U, gpio.PIN_D])
        last_selected_name = get_selected_usb_name()
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
                total_pages, page_index = view_devices(page_index)
            current_r = gpio.read_button(gpio.PIN_R)
            if prev_states["R"] and not current_r:
                page_index = min(total_pages - 1, page_index + 1)
                total_pages, page_index = view_devices(page_index)
            current_u = gpio.read_button(gpio.PIN_U)
            if prev_states["U"] and not current_u:
                page_index = max(0, page_index - 1)
                total_pages, page_index = view_devices(page_index)
            current_d = gpio.read_button(gpio.PIN_D)
            if prev_states["D"] and not current_d:
                page_index = min(total_pages - 1, page_index + 1)
                total_pages, page_index = view_devices(page_index)
            current_selected_name = get_selected_usb_name()
            if current_selected_name != last_selected_name:
                page_index = 0
                total_pages, page_index = view_devices(page_index)
                last_selected_name = current_selected_name
            prev_states["A"] = current_a
            prev_states["L"] = current_l
            prev_states["R"] = current_r
            prev_states["U"] = current_u
            prev_states["D"] = current_d
            time.sleep(0.05)

    def erase():
        target_devices = list_usb_disks()
        if not target_devices:
            display.display_lines(["ERASE", "No USB found"])
            time.sleep(1)
            return
        target_devices = sorted(target_devices, key=lambda d: d.get("name", ""))
        selected_name = get_selected_usb_name()
        target = None
        if selected_name:
            for device in target_devices:
                if device.get("name") == selected_name:
                    target = device
                    break
        if not target:
            target = target_devices[-1]
        target_name = target.get("name")
        mode = menus.select_erase_mode()
        if not mode:
            return
        title = f"ERASE {target_name} {mode.upper()}?"
        menu = menus.Menu(
            items=[],
            title=title,
            footer=["NO", "YES"],
            footer_positions=[context.x + 24, context.x + 52],
        )
        confirm_selection = app_state.CONFIRM_NO
        menu.footer_selected_index = confirm_selection
        menus.render_menu(menu, context.draw, context.width, context.height, context.fonts)
        context.disp.display(context.image)
        menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B, gpio.PIN_C])
        prev_states = {
            "L": gpio.read_button(gpio.PIN_L),
            "R": gpio.read_button(gpio.PIN_R),
            "A": gpio.read_button(gpio.PIN_A),
            "B": gpio.read_button(gpio.PIN_B),
            "C": gpio.read_button(gpio.PIN_C),
        }
        try:
            while True:
                current_R = gpio.read_button(gpio.PIN_R)
                if prev_states["R"] and not current_R:
                    if confirm_selection == app_state.CONFIRM_NO:
                        confirm_selection = app_state.CONFIRM_YES
                        log_debug("Erase menu selection changed: YES")
                    elif confirm_selection == app_state.CONFIRM_YES:
                        confirm_selection = app_state.CONFIRM_YES
                        log_debug("Erase menu selection changed: YES")
                current_L = gpio.read_button(gpio.PIN_L)
                if prev_states["L"] and not current_L:
                    if confirm_selection == app_state.CONFIRM_YES:
                        confirm_selection = app_state.CONFIRM_NO
                        log_debug("Erase menu selection changed: NO")
                current_A = gpio.read_button(gpio.PIN_A)
                if prev_states["A"] and not current_A:
                    return
                current_B = gpio.read_button(gpio.PIN_B)
                if prev_states["B"] and not current_B:
                    if confirm_selection == app_state.CONFIRM_YES:
                        if not ensure_root_for_erase():
                            return
                        display.display_lines(["ERASE", "Starting..."])
                        if erase_device(target, mode):
                            display.display_lines(["ERASE", "Done"])
                        else:
                            log_debug("Erase failed")
                            display.display_lines(["ERASE", "Failed"])
                        time.sleep(1)
                        return
                    if confirm_selection == app_state.CONFIRM_NO:
                        return
                current_C = gpio.read_button(gpio.PIN_C)
                if prev_states["C"] and not current_C:
                    log_debug("Erase menu: Button C pressed (ignored)")
                prev_states["R"] = current_R
                prev_states["L"] = current_L
                prev_states["A"] = current_A
                prev_states["B"] = current_B
                prev_states["C"] = current_C
                menu.footer_selected_index = confirm_selection
                menus.render_menu(menu, context.draw, context.width, context.height, context.fonts)
                context.disp.display(context.image)
        except KeyboardInterrupt:
            raise

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
                    if action == "copy":
                        copy()
                    elif action == "view":
                        view()
                    elif action == "erase":
                        erase()
                button_pressed = True
            if prev_states["B"] and not current_states["B"]:
                log_debug("Button SELECT pressed")
                action = menu_navigator.activate(visible_rows)
                if action:
                    if action == "copy":
                        copy()
                    elif action == "view":
                        view()
                    elif action == "erase":
                        erase()
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
