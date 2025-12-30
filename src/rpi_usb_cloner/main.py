import argparse
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from gpio import (
    PIN_A,
    PIN_B,
    PIN_C,
    PIN_D,
    PIN_L,
    PIN_R,
    PIN_U,
    cleanup as gpio_cleanup,
    is_pressed,
    read_button,
)
from mount import get_device_name, list_media_devices
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306

from devices import configure_device_helpers, get_children, human_size, is_root_device, list_usb_disks
from rpi_usb_cloner import config
from rpi_usb_cloner.services import cloning, progress
from rpi_usb_cloner.ui import screens
from rpi_usb_cloner.ui.menu import Menu, render_menu
from rpi_usb_cloner.ui.screens import ScreenContext

CONFIRM_NO = 0
CONFIRM_YES = 1
ENABLE_SLEEP = False


@dataclass
class AppState:
    usb_list_index: int = 0
    index: int = screens.MENU_NONE
    run_once: int = 0
    lcdstart: datetime = field(default_factory=datetime.now)
    last_usb_check: float = 0.0
    last_seen_devices: list = field(default_factory=list)


def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi USB Cloner")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable verbose debug output")
    args = parser.parse_args()
    config.DEBUG = args.debug
    config.CLONE_MODE = os.environ.get("CLONE_MODE", config.CLONE_MODE).lower()

    serial = i2c(port=1, address=0x3C)
    disp = ssd1306(serial)
    disp.clear()

    width = disp.width
    height = disp.height
    splash = Image.open("splash.png").convert("1")
    if splash.size != (width, height):
        splash = splash.resize((width, height))
    disp.display(splash)
    time.sleep(1.5)
    image = Image.new("1", (width, height))
    draw = ImageDraw.Draw(image)

    x = 12
    padding = -2
    top = padding

    fontcopy = ImageFont.truetype("rainyhearts.ttf", 16)
    fontinsert = ImageFont.truetype("slkscr.ttf", 16)
    fontdisks = ImageFont.truetype("slkscr.ttf", 8)
    fonts = {
        "title": fontdisks,
        "items": fontdisks,
        "footer": fontcopy,
    }

    context = ScreenContext(
        disp=disp,
        draw=draw,
        image=image,
        fonts=fonts,
        width=width,
        height=height,
        x=x,
        top=top,
        fontcopy=fontcopy,
        fontinsert=fontinsert,
        fontdisks=fontdisks,
        read_button=read_button,
        is_pressed=is_pressed,
        pin_u=PIN_U,
        pin_d=PIN_D,
        pin_l=PIN_L,
        pin_r=PIN_R,
        pin_a=PIN_A,
        pin_b=PIN_B,
        pin_c=PIN_C,
    )

    def display_lines(lines, font=None):
        screens.display_lines(context, lines, font=font)

    configure_device_helpers(log_debug=config.log_debug, error_handler=display_lines)
    progress.configure(display_lines, config.log_debug, human_size)
    cloning.configure(display_lines)

    state = AppState()

    def get_selected_usb_name():
        devices = list_media_devices()
        if not devices:
            return None
        if state.usb_list_index >= len(devices):
            state.usb_list_index = max(len(devices) - 1, 0)
        device = devices[state.usb_list_index]
        return get_device_name(device)

    def get_usb_snapshot():
        try:
            devices = list_media_devices()
        except Exception as error:
            config.log_debug(f"Failed to list media devices: {error}")
            return []
        snapshot = sorted(get_device_name(device) for device in devices)
        config.log_debug(f"USB snapshot: {snapshot}")
        return snapshot

    def pick_source_target():
        devices = [device for device in list_usb_disks() if not is_root_device(device)]
        if len(devices) < 2:
            return None, None
        devices = sorted(devices, key=lambda d: d.get("name", ""))
        selected_name = get_selected_usb_name()
        selected = None
        if selected_name:
            for device in devices:
                if device.get("name") == selected_name:
                    selected = device
                    break
        if selected:
            remaining = [device for device in devices if device.get("name") != selected_name]
            if not remaining:
                return None, None
            source = selected
            target = remaining[0]
        else:
            source = devices[0]
            target = devices[1]
        return source, target

    def view_devices():
        devices = list_usb_disks()
        if not devices:
            display_lines(["NO USB", "Insert device"])
            return
        lines = []
        for device in devices:
            name = device.get("name")
            size = human_size(device.get("size"))
            model = (device.get("model") or "").strip()
            line = f"{name} {size}"
            if model:
                line = f"{line} {model[:6]}"
            lines.append(line)
            for child in get_children(device):
                fstype = child.get("fstype") or "raw"
                mountpoint = child.get("mountpoint") or "-"
                lines.append(f"{child.get('name')} {fstype} {mountpoint[:10]}")
        display_lines(lines)

    def ensure_root_for_erase():
        if os.geteuid() != 0:
            display_lines(["Run as root"])
            time.sleep(1)
            screens.basemenu(context, state)
            return False
        return True

    def copy():
        state.index = screens.MENU_NONE
        source, target = pick_source_target()
        if not source or not target:
            display_lines(["COPY", "Need 2 USBs"])
            time.sleep(1)
            screens.basemenu(context, state)
            return
        source_name = source.get("name")
        target_name = target.get("name")
        title = f"CLONE {source_name} to {target_name}?"
        menu = Menu(
            items=[],
            title=title,
            footer=["NO", "YES"],
            footer_positions=[context.x + 24, context.x + 52],
        )
        confirm_selection = CONFIRM_NO
        menu.footer_selected_index = confirm_selection
        render_menu(menu, draw, width, height, context.fonts, x=context.x, top=context.top)
        disp.display(image)
        screens.wait_for_buttons_release(context, [PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
        prev_states = {
            "L": read_button(PIN_L),
            "R": read_button(PIN_R),
            "A": read_button(PIN_A),
            "B": read_button(PIN_B),
            "C": read_button(PIN_C),
        }
        try:
            while True:
                current_R = read_button(PIN_R)
                if prev_states["R"] and not current_R:
                    if confirm_selection == CONFIRM_NO:
                        confirm_selection = CONFIRM_YES
                        config.log_debug("Copy menu selection changed: YES")
                        state.run_once = 0
                    elif confirm_selection == CONFIRM_YES:
                        confirm_selection = CONFIRM_YES
                        config.log_debug("Copy menu selection changed: YES")
                        state.lcdstart = datetime.now()
                        state.run_once = 0
                current_L = read_button(PIN_L)
                if prev_states["L"] and not current_L:
                    if confirm_selection == CONFIRM_YES:
                        confirm_selection = CONFIRM_NO
                        config.log_debug("Copy menu selection changed: NO")
                        state.lcdstart = datetime.now()
                        state.run_once = 0
                current_A = read_button(PIN_A)
                if prev_states["A"] and not current_A:
                    config.log_debug("Copy menu: Button A pressed")
                    screens.basemenu(context, state)
                    return
                current_B = read_button(PIN_B)
                if prev_states["B"] and not current_B:
                    config.log_debug("Copy menu: Button B pressed")
                    if confirm_selection == CONFIRM_YES:
                        display_lines(["COPY", "Starting..."])
                        mode = screens.select_clone_mode(context)
                        if not mode:
                            screens.basemenu(context, state)
                            return
                        display_lines(["COPY", mode.upper()])
                        if cloning.clone_device(source, target, mode=mode):
                            display_lines(["COPY", "Done"])
                        else:
                            config.log_debug("Copy failed")
                            display_lines(["COPY", "Failed"])
                        time.sleep(1)
                        screens.basemenu(context, state)
                        return
                    if confirm_selection == CONFIRM_NO:
                        screens.basemenu(context, state)
                        return
                current_C = read_button(PIN_C)
                if prev_states["C"] and not current_C:
                    config.log_debug("Copy menu: Button C pressed (ignored)")
                prev_states["R"] = current_R
                prev_states["L"] = current_L
                prev_states["B"] = current_B
                prev_states["A"] = current_A
                prev_states["C"] = current_C
                menu.footer_selected_index = confirm_selection
                render_menu(menu, draw, width, height, context.fonts, x=context.x, top=context.top)
                disp.display(image)
        except KeyboardInterrupt:
            raise

    def view():
        view_devices()
        time.sleep(2)
        screens.basemenu(context, state)

    def erase():
        state.index = screens.MENU_NONE
        target_devices = list_usb_disks()
        if not target_devices:
            display_lines(["ERASE", "No USB found"])
            time.sleep(1)
            screens.basemenu(context, state)
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
        mode = screens.select_erase_mode(context)
        if not mode:
            screens.basemenu(context, state)
            return
        title = f"ERASE {target_name} {mode.upper()}?"
        menu = Menu(
            items=[],
            title=title,
            footer=["NO", "YES"],
            footer_positions=[context.x + 24, context.x + 52],
        )
        confirm_selection = CONFIRM_NO
        menu.footer_selected_index = confirm_selection
        render_menu(menu, draw, width, height, context.fonts, x=context.x, top=context.top)
        disp.display(image)
        screens.wait_for_buttons_release(context, [PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
        prev_states = {
            "L": read_button(PIN_L),
            "R": read_button(PIN_R),
            "A": read_button(PIN_A),
            "B": read_button(PIN_B),
            "C": read_button(PIN_C),
        }
        try:
            while True:
                current_R = read_button(PIN_R)
                if prev_states["R"] and not current_R:
                    if confirm_selection == CONFIRM_NO:
                        confirm_selection = CONFIRM_YES
                        config.log_debug("Erase menu selection changed: YES")
                    elif confirm_selection == CONFIRM_YES:
                        confirm_selection = CONFIRM_YES
                        config.log_debug("Erase menu selection changed: YES")
                current_L = read_button(PIN_L)
                if prev_states["L"] and not current_L:
                    if confirm_selection == CONFIRM_YES:
                        confirm_selection = CONFIRM_NO
                        config.log_debug("Erase menu selection changed: NO")
                current_A = read_button(PIN_A)
                if prev_states["A"] and not current_A:
                    screens.basemenu(context, state)
                    return
                current_B = read_button(PIN_B)
                if prev_states["B"] and not current_B:
                    if confirm_selection == CONFIRM_YES:
                        if not ensure_root_for_erase():
                            return
                        display_lines(["ERASE", "Starting..."])
                        if cloning.erase_device(target, mode):
                            display_lines(["ERASE", "Done"])
                        else:
                            config.log_debug("Erase failed")
                            display_lines(["ERASE", "Failed"])
                        time.sleep(1)
                        screens.basemenu(context, state)
                        return
                    if confirm_selection == CONFIRM_NO:
                        screens.basemenu(context, state)
                        return
                current_C = read_button(PIN_C)
                if prev_states["C"] and not current_C:
                    config.log_debug("Erase menu: Button C pressed (ignored)")
                prev_states["R"] = current_R
                prev_states["L"] = current_L
                prev_states["A"] = current_A
                prev_states["B"] = current_B
                prev_states["C"] = current_C
                menu.footer_selected_index = confirm_selection
                render_menu(menu, draw, width, height, context.fonts, x=context.x, top=context.top)
                disp.display(image)
        except KeyboardInterrupt:
            raise

    def sleepdisplay():
        draw.rectangle((0, 0, width, height), outline=0, fill=0)
        disp.display(image)
        state.run_once = 1

    def cleanup_display(clear_display=True):
        if clear_display:
            disp.clear()
        gpio_cleanup()

    screens.basemenu(context, state)
    state.index = screens.MENU_COPY if list_media_devices() else screens.MENU_NONE
    state.last_usb_check = time.time()
    state.last_seen_devices = get_usb_snapshot()

    error_displayed = False
    try:
        while True:
            time.sleep(0.1)
            if time.time() - state.last_usb_check >= config.USB_REFRESH_INTERVAL:
                config.log_debug(f"Checking USB devices (interval {config.USB_REFRESH_INTERVAL}s)")
                current_devices = get_usb_snapshot()
                if current_devices != state.last_seen_devices:
                    config.log_debug(f"USB devices changed: {state.last_seen_devices} -> {current_devices}")
                    screens.basemenu(context, state)
                    state.last_seen_devices = current_devices
                state.last_usb_check = time.time()
            if ENABLE_SLEEP:
                lcdtmp = state.lcdstart + timedelta(seconds=30)
                if datetime.now() > lcdtmp:
                    if state.run_once == 0:
                        sleepdisplay()
                    time.sleep(0.1)
            if read_button(PIN_U):
                pass
            else:
                config.log_debug("Button UP pressed")
                devices = list_media_devices()
                if devices:
                    previous_index = state.usb_list_index
                    state.usb_list_index = max(state.usb_list_index - 1, 0)
                    if state.usb_list_index != previous_index:
                        screens.basemenu(context, state)
                disp.display(image)
                state.lcdstart = datetime.now()
                state.run_once = 0
            if read_button(PIN_L):
                pass
            else:
                if state.index == screens.MENU_ERASE:
                    state.index = screens.MENU_VIEW
                    config.log_debug("Menu selection changed: index=1 (VIEW)")
                    screens.basemenu(context, state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                elif state.index == screens.MENU_VIEW:
                    state.index = screens.MENU_COPY
                    config.log_debug("Menu selection changed: index=0 (COPY)")
                    screens.basemenu(context, state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                elif state.index == screens.MENU_COPY:
                    state.index = screens.MENU_COPY
                    config.log_debug("Menu selection changed: index=0 (COPY)")
                    screens.basemenu(context, state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                else:
                    disp.display(image)
                    time.sleep(0.01)
            if read_button(PIN_R):
                pass
            else:
                if state.index == screens.MENU_COPY:
                    state.index = screens.MENU_VIEW
                    config.log_debug("Menu selection changed: index=1 (VIEW)")
                    screens.basemenu(context, state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                elif state.index == screens.MENU_VIEW:
                    state.index = screens.MENU_ERASE
                    config.log_debug("Menu selection changed: index=2 (ERASE)")
                    screens.basemenu(context, state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                elif state.index == screens.MENU_ERASE:
                    state.index = screens.MENU_ERASE
                    config.log_debug("Menu selection changed: index=2 (END OF MENU)")
                    screens.basemenu(context, state)
                    state.lcdstart = datetime.now()
                    state.run_once = 0
                else:
                    disp.display(image)
                    time.sleep(0.01)
            if read_button(PIN_D):
                pass
            else:
                config.log_debug("Button DOWN pressed")
                devices = list_media_devices()
                if devices:
                    previous_index = state.usb_list_index
                    state.usb_list_index = min(state.usb_list_index + 1, len(devices) - 1)
                    if state.usb_list_index != previous_index:
                        screens.basemenu(context, state)
            if read_button(PIN_C):
                pass
            else:
                config.log_debug("Button C pressed")
            if read_button(PIN_A):
                pass
            else:
                config.log_debug("Button A pressed")
                screens.basemenu(context, state)
            if read_button(PIN_B):
                pass
            else:
                if state.index == screens.MENU_COPY:
                    copy()
                if state.index == screens.MENU_VIEW:
                    view()
                if state.index == screens.MENU_ERASE:
                    erase()
                else:
                    disp.display(image)
                    time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(f"An error occurred: {type(error).__name__}")
        print(str(error))

        error_displayed = True
        disp.clear()
        draw.rectangle((0, 0, width, height), outline=0, fill=0)
        draw.text((x, top + 30), "ERROR", font=fontinsert, fill=255)
        disp.display(image)
    finally:
        cleanup_display(clear_display=not error_displayed)


if __name__ == "__main__":
    main()
