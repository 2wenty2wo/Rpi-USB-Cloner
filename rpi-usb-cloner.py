import time
import datetime
from gpio import (
            PIN_A,
            PIN_B,
            PIN_L,
            PIN_R,
            PIN_U,
            PIN_D,
            PIN_C,
            cleanup as gpio_cleanup,
            is_pressed,
            read_button,
)
import os
from mount import *
import sys
import argparse
from dataclasses import dataclass
from typing import List, Optional
from devices import (
            configure_device_helpers,
            get_children,
            human_size,
            is_root_device,
            list_usb_disks,
)
from operations import clone_device, configure_commands, erase_device, normalize_clone_mode

from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from datetime import datetime, timedelta
from time import sleep, strftime, localtime

parser = argparse.ArgumentParser(description="Raspberry Pi USB Cloner")
parser.add_argument("-d", "--debug", action="store_true", help="Enable verbose debug output")
args = parser.parse_args()
DEBUG = args.debug
CLONE_MODE = os.environ.get("CLONE_MODE", "smart").lower()

def log_debug(message):
            if DEBUG:
                        print(f"[DEBUG] {message}")


# Create the I2C interface.
serial = i2c(port=1, address=0x3C)
# Create the SSD1306 OLED class.
disp = ssd1306(serial)

# Input pins:
# Clear display.
disp.clear()

# Create blank image for drawing.
# Make sure to create image with mode '1' for 1-bit color.
width = disp.width
height = disp.height
splash = Image.open("splash.png").convert("1")
if splash.size != (width, height):
    splash = splash.resize((width, height))
disp.display(splash)
time.sleep(1.5)
image = Image.new('1', (width, height))

x = 12
padding = -2
top = padding
bottom = height-padding

# Load default font.
font = ImageFont.load_default()
fontcopy = ImageFont.truetype("rainyhearts.ttf", 16)
fontinsert = ImageFont.truetype("slkscr.ttf", 16)
fontdisks = ImageFont.truetype("slkscr.ttf", 8)
fontmain = ImageFont.load_default()
fonts = {
            "title": fontdisks,
            "items": fontdisks,
            "footer": fontcopy,
}

# Get drawing object to draw on image.
draw = ImageDraw.Draw(image)
MENU_COPY = 0
MENU_VIEW = 1
MENU_ERASE = 2
MENU_NONE = -1

CONFIRM_NO = 0
CONFIRM_YES = 1

index = MENU_NONE

# Draw a black filled box to clear the image.
draw.rectangle((0, 0, width, height), outline=0, fill=0)

usb = 0
ENABLE_SLEEP = False
USB_REFRESH_INTERVAL = 2.0
usb_list_index = 0
VISIBLE_ROWS = 3

@dataclass
class MenuItem:
            lines: List[str]

@dataclass
class Menu:
            items: List[MenuItem]
            selected_index: int = 0
            title: Optional[str] = None
            title_font: Optional[ImageFont.ImageFont] = None
            footer: Optional[List[str]] = None
            footer_selected_index: Optional[int] = None
            footer_positions: Optional[List[int]] = None
            content_top: Optional[int] = None
            items_font: Optional[ImageFont.ImageFont] = None

def render_menu(menu, draw, width, height, fonts):
            draw.rectangle((0, 0, width, height), outline=0, fill=0)
            current_y = top
            if menu.title:
                        title_font = menu.title_font or fonts["title"]
                        title_bbox = draw.textbbox((x - 11, current_y), menu.title, font=title_font)
                        draw.text((x - 11, current_y), menu.title, font=title_font, fill=255)
                        title_height = title_bbox[3] - title_bbox[1]
                        current_y += title_height + 2
            if menu.content_top is not None:
                        current_y = menu.content_top

            items_font = menu.items_font or fonts["items"]
            line_height = 8
            try:
                        bbox = items_font.getbbox("Ag")
                        line_height = max(bbox[3] - bbox[1], line_height)
            except AttributeError:
                        if hasattr(items_font, "getmetrics"):
                                    ascent, descent = items_font.getmetrics()
                                    line_height = max(ascent + descent, line_height)

            for item_index, item in enumerate(menu.items):
                        lines = item.lines
                        row_height = max(len(lines), 1) * line_height + 4
                        row_top = current_y
                        text_y_offset = (row_height - len(lines) * line_height) // 2
                        is_selected = item_index == menu.selected_index
                        if is_selected:
                                    draw.rectangle((0, row_top - 1, width, row_top + row_height - 1), outline=0, fill=1)
                        for line_index, line in enumerate(lines):
                                    text_color = 0 if is_selected else 255
                                    draw.text((x - 11, row_top + text_y_offset + line_index * line_height), line, font=items_font, fill=text_color)
                        current_y += row_height

            if menu.footer:
                        footer_font = fonts["footer"]
                        footer_y = height - 15
                        positions = menu.footer_positions
                        if positions is None:
                                    spacing = width // (len(menu.footer) + 1)
                                    positions = [(spacing * (index + 1)) - 10 for index in range(len(menu.footer))]
                        for footer_index, label in enumerate(menu.footer):
                                    x_pos = positions[footer_index]
                                    text_bbox = draw.textbbox((x_pos, footer_y), label, font=footer_font)
                                    if menu.footer_selected_index is not None and footer_index == menu.footer_selected_index:
                                                draw.rectangle((text_bbox[0] - 3, text_bbox[1] - 2, text_bbox[2] + 3, text_bbox[3] + 2), outline=0, fill=1)
                                                draw.text((x_pos, footer_y), label, font=footer_font, fill=0)
                                    else:
                                                draw.text((x_pos, footer_y), label, font=footer_font, fill=255)

def basemenu():
            global lcdstart
            global run_once
            global usb_list_index
            global index
            devices = list_media_devices()  #This is mount.py stuff.
            devices_present = bool(devices)
            if not devices:  # If nothing in devices list (No USB connected), display "INSERT USB".
                        draw.rectangle((0, 0, width, height), outline=0, fill=0)
                        text = "INSERT USB"
                        text_bbox = draw.textbbox((0, 0), text, font=fontinsert)
                        text_width = text_bbox[2] - text_bbox[0]
                        text_height = text_bbox[3] - text_bbox[1]
                        text_x = (width - text_width) // 2
                        text_y = (height - text_height) // 2
                        draw.text((text_x, text_y), text, font=fontinsert, fill=255)
                        usb = 0
                        usb_list_index = 0
            else:  # If USB is connected.
                        if usb_list_index >= len(devices):
                                    usb_list_index = max(len(devices) - 1, 0)
                        menu_items = []
                        for device in devices:  # This is mount.py stuff.
                                    menu_items.append(MenuItem([
                                                (get_device_name(device)) + " " + "%.2f" % (get_size(device) / 1024 ** 3) + "GB",
                                                (get_vendor(device)) + " " + (get_model(device)),
                                    ]))
                        usb = 1
                        start_index = max(0, usb_list_index - 1)
                        max_start = max(len(menu_items) - VISIBLE_ROWS, 0)
                        if start_index > max_start:
                                    start_index = max_start
                        visible_items = menu_items[start_index:start_index + VISIBLE_ROWS]
                        visible_selected_index = usb_list_index - start_index
                        if index not in (MENU_COPY, MENU_VIEW, MENU_ERASE):
                                    index = MENU_COPY
                        footer_selected = None
                        if index in (MENU_COPY, MENU_VIEW, MENU_ERASE):
                                    footer_selected = index
                        menu = Menu(
                                    items=visible_items,
                                    selected_index=visible_selected_index,
                                    footer=["COPY", "VIEW", "ERASE"],
                                    footer_selected_index=footer_selected,
                                    footer_positions=[x - 11, x + 32, x + 71],
                        )
                        render_menu(menu, draw, width, height, fonts)
            disp.display(image)
            lcdstart = datetime.now()
            run_once = 0
            if not devices_present:
                        index = MENU_NONE
            log_debug("Base menu drawn")

basemenu()  # Run Base Menu at script start

#set up a bit of a grid for mapping menu choices.
index = MENU_COPY if list_media_devices() else MENU_NONE
latindex = 0
filler = 0

# Menu Selection
def menuselect():
            if index == MENU_COPY:
                        copy()
            if index == MENU_VIEW:
                        view()
            if index == MENU_ERASE:
                        erase()
            else:
                        # Display image.
                        disp.display(image)
                        time.sleep(.01)

global run_once
run_once = 0

#setup the  go to sleep timer
lcdstart = datetime.now()

# Copy USB Screen
def display_lines(lines, font=fontdisks):
            draw.rectangle((0, 0, width, height), outline=0, fill=0)
            y = top
            for line in lines[:6]:
                        draw.text((x - 11, y), line, font=font, fill=255)
                        y += 10
            disp.display(image)

configure_device_helpers(log_debug=log_debug, error_handler=display_lines)
configure_commands(log_debug=log_debug, display_lines=display_lines, human_size=human_size)

def ensure_root_for_erase():
            if os.geteuid() != 0:
                        display_lines(["Run as root"])
                        time.sleep(1)
                        basemenu()
                        return False
            return True

def wait_for_buttons_release(buttons, poll_delay=0.05):
            while any(is_pressed(pin) for pin in buttons):
                        time.sleep(poll_delay)

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

def select_clone_mode():
            modes = ["smart", "exact", "verify"]
            selected_mode = normalize_clone_mode(CLONE_MODE)
            if selected_mode not in modes:
                        selected_mode = "smart"
            selected_index = modes.index(selected_mode)
            menu_items = [MenuItem([mode.upper()]) for mode in modes]
            menu = Menu(
                        items=menu_items,
                        selected_index=selected_index,
                        title="CLONE MODE",
                        footer=["BACK", "OK"],
                        footer_positions=[x + 12, x + 63],
            )
            render_menu(menu, draw, width, height, fonts)
            disp.display(image)
            wait_for_buttons_release([PIN_U, PIN_D, PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
            prev_states = {
                        "U": read_button(PIN_U),
                        "D": read_button(PIN_D),
                        "L": read_button(PIN_L),
                        "R": read_button(PIN_R),
                        "A": read_button(PIN_A),
                        "B": read_button(PIN_B),
                        "C": read_button(PIN_C),
            }
            while True:
                        current_U = read_button(PIN_U)
                        if prev_states["U"] and not current_U:
                                    selected_index = max(0, selected_index - 1)
                                    log_debug(f"Clone mode selection changed: {modes[selected_index]}")
                        current_D = read_button(PIN_D)
                        if prev_states["D"] and not current_D:
                                    selected_index = min(len(modes) - 1, selected_index + 1)
                                    log_debug(f"Clone mode selection changed: {modes[selected_index]}")
                        current_L = read_button(PIN_L)
                        if prev_states["L"] and not current_L:
                                    selected_index = max(0, selected_index - 1)
                        current_R = read_button(PIN_R)
                        if prev_states["R"] and not current_R:
                                    selected_index = min(len(modes) - 1, selected_index + 1)
                        current_A = read_button(PIN_A)
                        if prev_states["A"] and not current_A:
                                    return None
                        current_B = read_button(PIN_B)
                        if prev_states["B"] and not current_B:
                                    return modes[selected_index]
                        current_C = read_button(PIN_C)
                        prev_states["U"] = current_U
                        prev_states["D"] = current_D
                        prev_states["L"] = current_L
                        prev_states["R"] = current_R
                        prev_states["A"] = current_A
                        prev_states["B"] = current_B
                        prev_states["C"] = current_C
                        menu.selected_index = selected_index
                        render_menu(menu, draw, width, height, fonts)
                        disp.display(image)
                        time.sleep(0.05)

def select_erase_mode():
            modes = ["quick", "zero", "discard", "secure"]
            selected_index = 0
            menu_items = [MenuItem([mode.upper()]) for mode in modes]
            menu = Menu(
                        items=menu_items,
                        selected_index=selected_index,
                        title="ERASE MODE",
                        title_font=fontcopy,
            )
            render_menu(menu, draw, width, height, fonts)
            disp.display(image)
            wait_for_buttons_release([PIN_U, PIN_D, PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
            prev_states = {
                        "U": read_button(PIN_U),
                        "D": read_button(PIN_D),
                        "L": read_button(PIN_L),
                        "R": read_button(PIN_R),
                        "A": read_button(PIN_A),
                        "B": read_button(PIN_B),
                        "C": read_button(PIN_C),
            }
            while True:
                        current_U = read_button(PIN_U)
                        if prev_states["U"] and not current_U:
                                    selected_index = max(0, selected_index - 1)
                                    log_debug(f"Erase mode selection changed: {modes[selected_index]}")
                        current_D = read_button(PIN_D)
                        if prev_states["D"] and not current_D:
                                    selected_index = min(len(modes) - 1, selected_index + 1)
                                    log_debug(f"Erase mode selection changed: {modes[selected_index]}")
                        current_L = read_button(PIN_L)
                        if prev_states["L"] and not current_L:
                                    selected_index = max(0, selected_index - 1)
                        current_R = read_button(PIN_R)
                        if prev_states["R"] and not current_R:
                                    selected_index = min(len(modes) - 1, selected_index + 1)
                        current_A = read_button(PIN_A)
                        if prev_states["A"] and not current_A:
                                    return None
                        current_B = read_button(PIN_B)
                        if prev_states["B"] and not current_B:
                                    return modes[selected_index]
                        current_C = read_button(PIN_C)
                        prev_states["U"] = current_U
                        prev_states["D"] = current_D
                        prev_states["L"] = current_L
                        prev_states["R"] = current_R
                        prev_states["A"] = current_A
                        prev_states["B"] = current_B
                        prev_states["C"] = current_C
                        menu.selected_index = selected_index
                        render_menu(menu, draw, width, height, fonts)
                        disp.display(image)
                        time.sleep(0.05)

def copy():
            global index
            index = MENU_NONE
            source, target = pick_source_target()
            if not source or not target:
                        display_lines(["COPY", "Need 2 USBs"])
                        time.sleep(1)
                        basemenu()
                        return
            source_name = source.get("name")
            target_name = target.get("name")
            title = f"CLONE {source_name} to {target_name}?"
            menu = Menu(
                        items=[],
                        title=title,
                        footer=["NO", "YES"],
                        footer_positions=[x + 24, x + 52],
            )
            confirm_selection = CONFIRM_NO
            menu.footer_selected_index = confirm_selection
            render_menu(menu, draw, width, height, fonts)
            disp.display(image)
            wait_for_buttons_release([PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
            prev_states = {
                        "L": read_button(PIN_L),
                        "R": read_button(PIN_R),
                        "A": read_button(PIN_A),
                        "B": read_button(PIN_B),
                        "C": read_button(PIN_C),
            }
            try:
                        while 1:
                                    current_R = read_button(PIN_R)
                                    if prev_states["R"] and not current_R:
                                                if confirm_selection == CONFIRM_NO:
                                                            confirm_selection = CONFIRM_YES
                                                            log_debug("Copy menu selection changed: YES")
                                                            run_once = 0
                                                elif confirm_selection == CONFIRM_YES:
                                                            confirm_selection = CONFIRM_YES
                                                            log_debug("Copy menu selection changed: YES")
                                                            lcdstart = datetime.now()
                                                            run_once = 0
                                                else:
                                                            # Display image.
                                                            disp.display(image)
                                                            time.sleep(.01)
                                    current_L = read_button(PIN_L)
                                    if prev_states["L"] and not current_L:
                                                if confirm_selection == CONFIRM_YES:
                                                            confirm_selection = CONFIRM_NO
                                                            log_debug("Copy menu selection changed: NO")
                                                            lcdstart = datetime.now()
                                                            run_once = 0
                                                #if index == (5):
                                                            #draw.rectangle((x + 21, 48, 57, 60), outline=0, fill=0) #Deselect No
                                                            #draw.text((x + 24, top + 49), "NO", font=fontcopy, fill=1) #No White
                                                            #draw.rectangle((x + 49, 48, 92, 60), outline=0, fill=1) #Select Yes
                                                            #draw.text((x + 52, top + 49), "YES", font=fontcopy, fill=0) #Yes Black
                                                            #index = 6
                                                            #disp.display(image)
                                                            #print("YES" + str(index))
                                                            #lcdstart = datetime.now()
                                                            #run_once = 0
                                                else:
                                                            # Display image.
                                                            disp.display(image)
                                                            time.sleep(.01)
                                    current_A = read_button(PIN_A)
                                    if prev_states["A"] and not current_A:
                                                log_debug("Copy menu: Button A pressed")
                                                basemenu()
                                                return
                                    current_B = read_button(PIN_B)
                                    if prev_states["B"] and not current_B:
                                                log_debug("Copy menu: Button B pressed")
                                                if confirm_selection == CONFIRM_YES:
                                                            display_lines(["COPY", "Starting..."])
                                                            mode = select_clone_mode()
                                                            if not mode:
                                                                        basemenu()
                                                                        return
                                                            display_lines(["COPY", mode.upper()])
                                                            if clone_device(source, target, mode=mode):
                                                                        display_lines(["COPY", "Done"])
                                                            else:
                                                                        log_debug("Copy failed")
                                                                        display_lines(["COPY", "Failed"])
                                                            time.sleep(1)
                                                            basemenu()
                                                            return
                                                elif confirm_selection == CONFIRM_NO:
                                                            basemenu()
                                                            return
                                    current_C = read_button(PIN_C)
                                    if prev_states["C"] and not current_C:
                                                log_debug("Copy menu: Button C pressed (ignored)")
                                    prev_states["R"] = current_R
                                    prev_states["L"] = current_L
                                    prev_states["B"] = current_B
                                    prev_states["A"] = current_A
                                    prev_states["C"] = current_C
                                    menu.footer_selected_index = confirm_selection
                                    render_menu(menu, draw, width, height, fonts)
                                    disp.display(image)
            except KeyboardInterrupt:
                        raise

def view():
            view_devices()
            time.sleep(2)
            basemenu()

def erase():
            global index
            index = MENU_NONE
            target_devices = list_usb_disks()
            if not target_devices:
                        display_lines(["ERASE", "No USB found"])
                        time.sleep(1)
                        basemenu()
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
            mode = select_erase_mode()
            if not mode:
                        basemenu()
                        return
            title = f"ERASE {target_name} {mode.upper()}?"
            menu = Menu(
                        items=[],
                        title=title,
                        footer=["NO", "YES"],
                        footer_positions=[x + 24, x + 52],
            )
            confirm_selection = CONFIRM_NO
            menu.footer_selected_index = confirm_selection
            render_menu(menu, draw, width, height, fonts)
            disp.display(image)
            wait_for_buttons_release([PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
            prev_states = {
                        "L": read_button(PIN_L),
                        "R": read_button(PIN_R),
                        "A": read_button(PIN_A),
                        "B": read_button(PIN_B),
                        "C": read_button(PIN_C),
            }
            try:
                        while 1:
                                    current_R = read_button(PIN_R)
                                    if prev_states["R"] and not current_R:
                                                if confirm_selection == CONFIRM_NO:
                                                            confirm_selection = CONFIRM_YES
                                                            log_debug("Erase menu selection changed: YES")
                                                elif confirm_selection == CONFIRM_YES:
                                                            confirm_selection = CONFIRM_YES
                                                            log_debug("Erase menu selection changed: YES")
                                    current_L = read_button(PIN_L)
                                    if prev_states["L"] and not current_L:
                                                if confirm_selection == CONFIRM_YES:
                                                            confirm_selection = CONFIRM_NO
                                                            log_debug("Erase menu selection changed: NO")
                                    current_A = read_button(PIN_A)
                                    if prev_states["A"] and not current_A:
                                                basemenu()
                                                return
                                    current_B = read_button(PIN_B)
                                    if prev_states["B"] and not current_B:
                                                if confirm_selection == CONFIRM_YES:
                                                            if not ensure_root_for_erase():
                                                                        return
                                                            display_lines(["ERASE", "Starting..."])
                                                            if erase_device(target, mode):
                                                                        display_lines(["ERASE", "Done"])
                                                            else:
                                                                        log_debug("Erase failed")
                                                                        display_lines(["ERASE", "Failed"])
                                                            time.sleep(1)
                                                            basemenu()
                                                            return
                                                elif confirm_selection == CONFIRM_NO:
                                                            basemenu()
                                                            return
                                    current_C = read_button(PIN_C)
                                    if prev_states["C"] and not current_C:
                                                log_debug("Erase menu: Button C pressed (ignored)")
                                    prev_states["R"] = current_R
                                    prev_states["L"] = current_L
                                    prev_states["A"] = current_A
                                    prev_states["B"] = current_B
                                    prev_states["C"] = current_C
                                    menu.footer_selected_index = confirm_selection
                                    render_menu(menu, draw, width, height, fonts)
                                    disp.display(image)
            except KeyboardInterrupt:
                        raise

def sleepdisplay():  # put the display to sleep to reduce power
            global run_once
            draw.rectangle((0, 0, width, height), outline=0, fill=0)
            disp.display(image)
            run_once = 1

def cleanup_display(clear_display=True):
            if clear_display:
                        disp.clear()
            gpio_cleanup()

# Button Commands
error_displayed = False
try:
            while 1:
                        # Sleep Stuff
                        time.sleep(0.1)
                        if time.time() - last_usb_check >= USB_REFRESH_INTERVAL:
                                    log_debug(f"Checking USB devices (interval {USB_REFRESH_INTERVAL}s)")
                                    current_devices = get_usb_snapshot()
                                    if current_devices != last_seen_devices:
                                                log_debug(f"USB devices changed: {last_seen_devices} -> {current_devices}")
                                                basemenu()
                                                last_seen_devices = current_devices
                                    last_usb_check = time.time()
                        if ENABLE_SLEEP:
                                    lcdtmp = lcdstart + timedelta(seconds=30)
                                    if (datetime.now() > lcdtmp):
                                                if run_once == 0:
                                                            sleepdisplay()
                                                time.sleep(0.1)
                        # Sleep Stuff
                        if read_button(PIN_U): # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    log_debug("Button UP pressed")
                                    devices = list_media_devices()
                                    if devices:
                                                previous_index = usb_list_index
                                                usb_list_index = max(usb_list_index - 1, 0)
                                                if usb_list_index != previous_index:
                                                            basemenu()
                                    disp.display(image)
                                    lcdstart = datetime.now()
                                    run_once = 0
                        if read_button(PIN_L): # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    if index == MENU_ERASE:
                                                index = MENU_VIEW
                                                log_debug("Menu selection changed: index=1 (VIEW)")
                                                basemenu()
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    elif index == MENU_VIEW:
                                                index = MENU_COPY
                                                log_debug("Menu selection changed: index=0 (COPY)")
                                                basemenu()
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    elif index == MENU_COPY:
                                                index = MENU_COPY
                                                log_debug("Menu selection changed: index=0 (COPY)")
                                                basemenu()
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    else:
                                                # Display image.
                                                disp.display(image)
                                                time.sleep(.01)
                        if read_button(PIN_R): # button is released
                                    filler =(0)
                        else: # button is pressed:
                                    if index == MENU_COPY:
                                                index = MENU_VIEW
                                                log_debug("Menu selection changed: index=1 (VIEW)")
                                                basemenu()
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    elif index == MENU_VIEW:
                                                index = MENU_ERASE
                                                log_debug("Menu selection changed: index=2 (ERASE)")
                                                basemenu()
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    elif index == MENU_ERASE:
                                                index = MENU_ERASE
                                                log_debug("Menu selection changed: index=2 (END OF MENU)")
                                                basemenu()
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    else:
                                                # Display image.
                                                disp.display(image)
                                                time.sleep(.01)
                        if read_button(PIN_D): # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    log_debug("Button DOWN pressed")
                                    devices = list_media_devices()
                                    if devices:
                                                previous_index = usb_list_index
                                                usb_list_index = min(usb_list_index + 1, len(devices) - 1)
                                                if usb_list_index != previous_index:
                                                            basemenu()
                        if read_button(PIN_C): # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    filler = (0)
                                    log_debug("Button C pressed")
                        if read_button(PIN_A): # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    log_debug("Button A pressed")
                                    basemenu()
                        if read_button(PIN_B): # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    menuselect ()
except KeyboardInterrupt:
            pass
except Exception as e:
            # This will print the type of exception and error message to the terminal
            print(f"An error occurred: {type(e).__name__}")
            print(str(e))

            # This will display a simple error message on the OLED screen
            error_displayed = True
            disp.clear()
            draw.rectangle((0,0,width,height), outline=0, fill=0)
            draw.text((x, top + 30), "ERROR", font=fontinsert, fill=255)
            disp.display(image)
finally:
            cleanup_display(clear_display=not error_displayed)
