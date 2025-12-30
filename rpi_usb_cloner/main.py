import argparse
import os
import shutil
import time
from datetime import datetime, timedelta

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.storage import devices
from rpi_usb_cloner.storage.devices import get_children, human_size, list_usb_disks
from rpi_usb_cloner.storage.mount import get_device_name, list_media_devices
from rpi_usb_cloner.storage.clone import clone_device, configure_clone_helpers, erase_device
from rpi_usb_cloner.ui import display, menus


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
            display.basemenu(state)
            return False
        return True

    def build_device_info_lines(device, max_lines=6):
        lines = []
        header = format_device_label(device)
        vendor = (device.get("vendor") or "").strip()
        model = (device.get("model") or "").strip()
        vendor_model = " ".join(part for part in [vendor, model] if part)
        if vendor_model:
            header = f"{header} {vendor_model}"
        lines.append(header.strip())

        for child in get_children(device):
            if len(lines) >= max_lines:
                break
            name = child.get("name") or ""
            fstype = child.get("fstype") or "raw"
            label = (child.get("label") or "").strip()
            mountpoint = child.get("mountpoint")
            label_suffix = f" {label}" if label else ""
            if not mountpoint:
                lines.append(f"{name} {fstype}{label_suffix} not mounted")
                continue

            usage_label = ""
            try:
                usage = shutil.disk_usage(mountpoint)
                usage_label = f" {human_size(usage.used)}/{human_size(usage.total)}"
            except (FileNotFoundError, PermissionError, OSError) as error:
                log_debug(f"Usage check failed for {mountpoint}: {error}")
                usage_label = " usage?"

            files_label = ""
            try:
                entries = sorted(os.listdir(mountpoint))[:3]
                if entries:
                    files_label = " files:" + ",".join(entries)
            except (FileNotFoundError, PermissionError, OSError) as error:
                log_debug(f"Listdir failed for {mountpoint}: {error}")
                files_label = " files?"

            lines.append(f"{name} {fstype}{label_suffix} {mountpoint}{usage_label}{files_label}")

        if len(lines) > max_lines:
            return lines[:max_lines]
        return lines

    def view_devices():
        selected_name = get_selected_usb_name()
        if not selected_name:
            display.display_lines(["NO SELECTED USB"])
            return
        devices_list = [device for device in list_usb_disks() if device.get("name") == selected_name]
        if not devices_list:
            display.display_lines(["NO SELECTED USB"])
            return
        device = devices_list[0]
        lines = build_device_info_lines(device, max_lines=6)
        display.display_lines(lines)

    def menuselect():
        if state.index == app_state.MENU_COPY:
            copy()
        if state.index == app_state.MENU_VIEW:
            view()
        if state.index == app_state.MENU_ERASE:
            erase()
        else:
            context.disp.display(context.image)
            time.sleep(0.01)

    def copy():
        state.index = app_state.MENU_NONE
        source, target = pick_source_target()
        if not source or not target:
            display.display_lines(["COPY", "Need 2 USBs"])
            time.sleep(1)
            display.basemenu(state)
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
                    display.basemenu(state)
                    return
                current_B = gpio.read_button(gpio.PIN_B)
                if prev_states["B"] and not current_B:
                    log_debug("Copy menu: Button B pressed")
                    if confirm_selection == app_state.CONFIRM_YES:
                        display.display_lines(["COPY", "Starting..."])
                        mode = menus.select_clone_mode(clone_mode)
                        if not mode:
                            display.basemenu(state)
                            return
                        display.display_lines(["COPY", mode.upper()])
                        if clone_device(source, target, mode=mode):
                            display.display_lines(["COPY", "Done"])
                        else:
                            log_debug("Copy failed")
                            display.display_lines(["COPY", "Failed"])
                        time.sleep(1)
                        display.basemenu(state)
                        return
                    if confirm_selection == app_state.CONFIRM_NO:
                        display.basemenu(state)
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
        view_devices()
        menus.wait_for_buttons_release([gpio.PIN_A])
        last_selected_name = get_selected_usb_name()
        while True:
            current_a = gpio.read_button(gpio.PIN_A)
            if not current_a:
                display.basemenu(state)
                return
            current_selected_name = get_selected_usb_name()
            if current_selected_name != last_selected_name:
                view_devices()
                last_selected_name = current_selected_name
            time.sleep(0.05)

    def erase():
        state.index = app_state.MENU_NONE
        target_devices = list_usb_disks()
        if not target_devices:
            display.display_lines(["ERASE", "No USB found"])
            time.sleep(1)
            display.basemenu(state)
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
            display.basemenu(state)
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
                    display.basemenu(state)
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
                        display.basemenu(state)
                        return
                    if confirm_selection == app_state.CONFIRM_NO:
                        display.basemenu(state)
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

    display.basemenu(state)
    state.index = app_state.MENU_COPY if list_media_devices() else app_state.MENU_NONE
    state.last_usb_check = time.time()
    state.last_seen_devices = get_usb_snapshot()

    error_displayed = False
    try:
        while True:
            time.sleep(0.1)
            if time.time() - state.last_usb_check >= app_state.USB_REFRESH_INTERVAL:
                log_debug(f"Checking USB devices (interval {app_state.USB_REFRESH_INTERVAL}s)")
                current_devices = get_usb_snapshot()
                if current_devices != state.last_seen_devices:
                    log_debug(f"USB devices changed: {state.last_seen_devices} -> {current_devices}")
                    display.basemenu(state)
                    state.last_seen_devices = current_devices
                state.last_usb_check = time.time()
            if app_state.ENABLE_SLEEP:
                lcdtmp = state.lcdstart + timedelta(seconds=30)
                if datetime.now() > lcdtmp:
                    if state.run_once == 0:
                        sleepdisplay()
                    time.sleep(0.1)
            if gpio.read_button(gpio.PIN_U):
                pass
            else:
                log_debug("Button UP pressed")
                devices_list = list_media_devices()
                if devices_list:
                    previous_index = state.usb_list_index
                    state.usb_list_index = max(state.usb_list_index - 1, 0)
                    if state.usb_list_index != previous_index:
                        display.basemenu(state)
                context.disp.display(context.image)
                state.lcdstart = datetime.now()
                state.run_once = 0
            if gpio.read_button(gpio.PIN_L):
                pass
            else:
                if state.index == app_state.MENU_ERASE:
                    state.index = app_state.MENU_VIEW
                    log_debug("Menu selection changed: index=1 (VIEW)")
                    display.basemenu(state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                elif state.index == app_state.MENU_VIEW:
                    state.index = app_state.MENU_COPY
                    log_debug("Menu selection changed: index=0 (COPY)")
                    display.basemenu(state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                elif state.index == app_state.MENU_COPY:
                    state.index = app_state.MENU_COPY
                    log_debug("Menu selection changed: index=0 (COPY)")
                    display.basemenu(state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                else:
                    context.disp.display(context.image)
                    time.sleep(0.01)
            if gpio.read_button(gpio.PIN_R):
                pass
            else:
                if state.index == app_state.MENU_COPY:
                    state.index = app_state.MENU_VIEW
                    log_debug("Menu selection changed: index=1 (VIEW)")
                    display.basemenu(state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                elif state.index == app_state.MENU_VIEW:
                    state.index = app_state.MENU_ERASE
                    log_debug("Menu selection changed: index=2 (ERASE)")
                    display.basemenu(state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                elif state.index == app_state.MENU_ERASE:
                    state.index = app_state.MENU_ERASE
                    log_debug("Menu selection changed: index=2 (END OF MENU)")
                    display.basemenu(state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                else:
                    context.disp.display(context.image)
                    time.sleep(0.01)
            if gpio.read_button(gpio.PIN_D):
                pass
            else:
                log_debug("Button DOWN pressed")
                devices_list = list_media_devices()
                if devices_list:
                    previous_index = state.usb_list_index
                    state.usb_list_index = min(state.usb_list_index + 1, len(devices_list) - 1)
                    if state.usb_list_index != previous_index:
                        display.basemenu(state)
            if gpio.read_button(gpio.PIN_C):
                pass
            else:
                log_debug("Button C pressed")
            if gpio.read_button(gpio.PIN_A):
                pass
            else:
                log_debug("Button A pressed")
                display.basemenu(state)
            if gpio.read_button(gpio.PIN_B):
                pass
            else:
                menuselect()
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
