import board
import busio
import time
import datetime
import subprocess
import RPi.GPIO as GPIO
import os
import json
import shutil
import re
from mount import *
import sys
import argparse
from dataclasses import dataclass
from typing import List, Optional

from digitalio import DigitalInOut, Direction, Pull
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
from datetime import datetime, timedelta
from time import sleep, strftime, localtime

parser = argparse.ArgumentParser(description="Raspberry Pi USB Cloner")
parser.add_argument("-d", "--debug", action="store_true", help="Enable verbose debug output")
args = parser.parse_args()
DEBUG = args.debug
CLONE_MODE = os.environ.get("CLONE_MODE", "raw").lower()

def log_debug(message):
            if DEBUG:
                        print(f"[DEBUG] {message}")

def resolve_device_node(device):
            if isinstance(device, str):
                        return device if device.startswith("/dev/") else f"/dev/{device}"
            return f"/dev/{device.get('name')}"

def run_checked_command(command, input_text=None):
            log_debug(f"Running command: {' '.join(command)}")
            result = subprocess.run(
                        command,
                        input=input_text,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
            )
            if result.returncode != 0:
                        stderr = result.stderr.strip()
                        stdout = result.stdout.strip()
                        message = stderr or stdout or "Command failed"
                        raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")
            return result.stdout

def copy_partition_table(src, dst):
            src_node = resolve_device_node(src)
            dst_node = resolve_device_node(dst)
            sfdisk_path = shutil.which("sfdisk")
            if not sfdisk_path:
                        raise RuntimeError("sfdisk not found")
            dump_output = run_checked_command([sfdisk_path, "--dump", src_node])
            label = None
            for line in dump_output.splitlines():
                        if line.startswith("label:"):
                                    label = line.split(":", 1)[1].strip().lower()
                                    break
            if not label:
                        raise RuntimeError("Unable to detect partition table label")
            if label == "gpt":
                        sgdisk_path = shutil.which("sgdisk")
                        if not sgdisk_path:
                                    raise RuntimeError("sgdisk not found for GPT replicate")
                        run_checked_command([sgdisk_path, f"--replicate={dst_node}", "--randomize-guids", src_node])
                        log_debug(f"GPT partition table replicated from {src_node} to {dst_node}")
                        return
            if label in ("dos", "mbr", "msdos"):
                        run_checked_command([sfdisk_path, dst_node], input_text=dump_output)
                        log_debug(f"MBR partition table cloned from {src_node} to {dst_node}")
                        return
            raise RuntimeError(f"Unsupported partition table label: {label}")

# Create the I2C interface.
i2c = busio.I2C(board.SCL, board.SDA)
# Create the SSD1306 OLED class.
disp = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)

# Input pins:
button_A = DigitalInOut(board.D5)
button_A.direction = Direction.INPUT
button_A.pull = Pull.UP

button_B = DigitalInOut(board.D6)
button_B.direction = Direction.INPUT
button_B.pull = Pull.UP

button_L = DigitalInOut(board.D27)
button_L.direction = Direction.INPUT
button_L.pull = Pull.UP

button_R = DigitalInOut(board.D23)
button_R.direction = Direction.INPUT
button_R.pull = Pull.UP

button_U = DigitalInOut(board.D17)
button_U.direction = Direction.INPUT
button_U.pull = Pull.UP

button_D = DigitalInOut(board.D22)
button_D.direction = Direction.INPUT
button_D.pull = Pull.UP

button_C = DigitalInOut(board.D4)
button_C.direction = Direction.INPUT
button_C.pull = Pull.UP

# Clear display.
disp.fill(0)
disp.show()

# Create blank image for drawing.
# Make sure to create image with mode '1' for 1-bit color.
width = disp.width
height = disp.height
splash = Image.open("splash.png").convert("1")
if splash.size != (width, height):
    splash = splash.resize((width, height))
disp.image(splash)
disp.show()
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
            footer: Optional[List[str]] = None
            footer_selected_index: Optional[int] = None
            footer_positions: Optional[List[int]] = None
            content_top: Optional[int] = None
            items_font: Optional[ImageFont.ImageFont] = None

def render_menu(menu, draw, width, height, fonts):
            draw.rectangle((0, 0, width, height), outline=0, fill=0)
            current_y = top
            if menu.title:
                        draw.text((x - 11, current_y), menu.title, font=fonts["title"], fill=255)
                        current_y += 12
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
                        is_selected = item_index == menu.selected_index
                        if is_selected:
                                    draw.rectangle((0, row_top - 1, width, row_top + row_height - 1), outline=0, fill=1)
                        for line_index, line in enumerate(lines):
                                    text_color = 0 if is_selected else 255
                                    draw.text((x - 11, row_top + line_index * line_height), line, font=items_font, fill=text_color)
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
            disp.fill(0)
            disp.show()
            devices = list_media_devices()  #This is mount.py stuff.
            if not devices:  # If nothing in devices list (No USB connected), display "INSERT USB".
                        disp.fill(0)
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
            disp.image(image)
            disp.show()
            lcdstart = datetime.now()
            run_once = 0
            if index not in (MENU_COPY, MENU_VIEW, MENU_ERASE):
                        index = MENU_NONE
            log_debug("Base menu drawn")

basemenu()  # Run Base Menu at script start

#set up a bit of a grid for mapping menu choices.
index = MENU_NONE
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
                        disp.image(image)
                        disp.show()
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
            disp.image(image)
            disp.show()

def ensure_root_for_erase():
            if os.geteuid() != 0:
                        display_lines(["Run as root"])
                        time.sleep(1)
                        basemenu()
                        return False
            return True

def wait_for_buttons_release(buttons, poll_delay=0.05):
            while any(not button.value for button in buttons):
                        time.sleep(poll_delay)

def human_size(size_bytes):
            if size_bytes is None:
                        return "0B"
            size = float(size_bytes)
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                        if size < 1024.0:
                                    return f"{size:.1f}{unit}"
                        size /= 1024.0
            return f"{size:.1f}PB"

def run_command(command, check=True):
            log_debug(f"Running command: {' '.join(command)}")
            try:
                        result = subprocess.run(command, check=check, text=True, capture_output=True)
            except subprocess.CalledProcessError as error:
                        log_debug(f"Command failed: {' '.join(command)}")
                        if error.stdout:
                                    log_debug(f"stdout: {error.stdout.strip()}")
                        if error.stderr:
                                    log_debug(f"stderr: {error.stderr.strip()}")
                        raise
            if result.stdout:
                        log_debug(f"stdout: {result.stdout.strip()}")
            if result.stderr:
                        log_debug(f"stderr: {result.stderr.strip()}")
            log_debug(f"Command completed with return code {result.returncode}")
            return result

def get_block_devices():
            try:
                        result = run_command(["lsblk", "-J", "-b", "-o", "NAME,TYPE,SIZE,MODEL,VENDOR,TRAN,RM,MOUNTPOINT,FSTYPE,LABEL"])
                        data = json.loads(result.stdout)
                        return data.get("blockdevices", [])
            except (subprocess.CalledProcessError, json.JSONDecodeError) as error:
                        display_lines(["LSBLK ERROR", str(error)])
                        log_debug(f"lsblk failed: {error}")
                        return []

ROOT_MOUNTPOINTS = {"/", "/boot", "/boot/firmware"}

def get_children(device):
            return device.get("children", []) or []

def has_root_mountpoint(device):
            mountpoint = device.get("mountpoint")
            if mountpoint in ROOT_MOUNTPOINTS:
                        return True
            for child in get_children(device):
                        if has_root_mountpoint(child):
                                    return True
            return False

def is_root_device(device):
            if device.get("type") != "disk":
                        return False
            return has_root_mountpoint(device)

def list_usb_disks():
            devices = []
            for device in get_block_devices():
                        if device.get("type") != "disk":
                                    continue
                        if is_root_device(device):
                                    continue
                        tran = device.get("tran")
                        rm = device.get("rm")
                        if tran == "usb" or rm == 1:
                                    devices.append(device)
            return devices

def get_selected_usb_name():
            global usb_list_index
            devices = list_media_devices()
            if not devices:
                        return None
            if usb_list_index >= len(devices):
                        usb_list_index = max(len(devices) - 1, 0)
            device = devices[usb_list_index]
            return get_device_name(device)

def get_usb_snapshot():
            try:
                        devices = list_media_devices()
            except Exception as error:
                        log_debug(f"Failed to list media devices: {error}")
                        return []
            snapshot = sorted(get_device_name(device) for device in devices)
            log_debug(f"USB snapshot: {snapshot}")
            return snapshot

last_usb_check = time.time()
last_seen_devices = get_usb_snapshot()

def unmount_device(device):
            mountpoint = device.get("mountpoint")
            if mountpoint:
                        try:
                                    run_command(["umount", mountpoint], check=False)
                        except subprocess.CalledProcessError:
                                    pass
            for child in get_children(device):
                        mountpoint = child.get("mountpoint")
                        if mountpoint:
                                    try:
                                                run_command(["umount", mountpoint], check=False)
                                    except subprocess.CalledProcessError:
                                                pass

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

def run_progress_command(command, total_bytes=None, title="WORKING"):
            display_lines([title, "Starting..."])
            log_debug(f"Starting command: {' '.join(command)}")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            last_update = time.time()
            while True:
                        line = process.stderr.readline()
                        if line:
                                    log_debug(f"stderr: {line.strip()}")
                                    match = re.search(r"(\d+)\s+bytes", line)
                                    if match:
                                                bytes_copied = int(match.group(1))
                                                percent = ""
                                                if total_bytes:
                                                            percent = f"{(bytes_copied / total_bytes) * 100:.1f}%"
                                                display_lines([title, f"{human_size(bytes_copied)} {percent}".strip()])
                                                last_update = time.time()
                        if process.poll() is not None:
                                    break
                        if time.time() - last_update > 5:
                                    display_lines([title, "Working..."])
                                    last_update = time.time()
            if process.returncode != 0:
                        error_output = process.stderr.read().strip()
                        message = error_output.splitlines()[-1] if error_output else "Command failed"
                        display_lines(["FAILED", message[:20]])
                        log_debug(f"Command failed with code {process.returncode}: {message}")
                        return False
            display_lines([title, "Complete"])
            log_debug("Command completed successfully")
            return True

def clone_device(source, target):
            if CLONE_MODE == "smart":
                        return clone_device_smart(source, target)
            source_node = f"/dev/{source.get('name')}"
            target_node = f"/dev/{target.get('name')}"
            unmount_device(target)
            total = source.get("size")
            dd_path = shutil.which("dd")
            if not dd_path:
                        display_lines(["ERROR", "dd not found"])
                        log_debug("Clone failed: dd not found")
                        return False
            return run_progress_command(
                        [dd_path, f"if={source_node}", f"of={target_node}", "bs=4M", "status=progress", "conv=fsync"],
                        total_bytes=total,
                        title="CLONING"
            )

def clone_device_smart(source, target):
            source_node = f"/dev/{source.get('name')}"
            target_node = f"/dev/{target.get('name')}"
            unmount_device(target)
            try:
                        display_lines(["CLONING", "Copy table"])
                        copy_partition_table(source, target)
            except RuntimeError as error:
                        display_lines(["FAILED", "Partition tbl"])
                        log_debug(f"Partition table copy failed: {error}")
                        return False
            partclone_tools = {
                        "ext2": "partclone.ext2",
                        "ext3": "partclone.ext3",
                        "ext4": "partclone.ext4",
                        "vfat": "partclone.fat",
                        "fat16": "partclone.fat",
                        "fat32": "partclone.fat",
                        "ntfs": "partclone.ntfs",
                        "exfat": "partclone.exfat",
                        "xfs": "partclone.xfs",
                        "btrfs": "partclone.btrfs",
            }
            fallback_tool = "partclone.dd"
            source_parts = [child for child in get_children(source) if child.get("type") == "part"]
            if not source_parts:
                        display_lines(["FAILED", "No partitions"])
                        log_debug("Smart clone failed: no source partitions found")
                        return False
            for index, part in enumerate(source_parts, start=1):
                        src_part = f"/dev/{part.get('name')}"
                        dst_part = src_part.replace(source.get("name"), target.get("name"), 1)
                        fstype = (part.get("fstype") or "").lower()
                        tool = partclone_tools.get(fstype, fallback_tool)
                        tool_path = shutil.which(tool)
                        if not tool_path and tool != fallback_tool:
                                    tool_path = shutil.which(fallback_tool)
                                    tool = fallback_tool
                        if not tool_path:
                                    display_lines(["ERROR", "partclone missing"])
                                    log_debug(f"Smart clone failed: {tool} not found for {src_part}")
                                    return False
                        display_lines([f"PART {index}/{len(source_parts)}", tool])
                        result = subprocess.run(
                                    [tool_path, "-s", src_part, "-o", dst_part, "-f"],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True,
                        )
                        if result.returncode != 0:
                                    message = result.stderr.strip() or result.stdout.strip() or "partclone failed"
                                    display_lines(["FAILED", message[:20]])
                                    log_debug(f"Smart clone failed ({src_part} -> {dst_part}): {message}")
                                    return False
            display_lines(["CLONING", "Complete"])
            log_debug(f"Smart clone completed from {source_node} to {target_node}")
            return True

def erase_device(target):
            target_node = f"/dev/{target.get('name')}"
            unmount_device(target)
            shred_path = shutil.which("shred")
            if shred_path:
                        return run_progress_command(
                                    [shred_path, "-v", "-n", "1", "-z", target_node],
                                    total_bytes=target.get("size"),
                                    title="ERASING"
                        )
            dd_path = shutil.which("dd")
            if not dd_path:
                        display_lines(["ERROR", "no wipe tool"])
                        log_debug("Erase failed: no wipe tool available")
                        return False
            return run_progress_command(
                        [dd_path, "if=/dev/zero", f"of={target_node}", "bs=4M", "status=progress", "conv=fsync"],
                        total_bytes=target.get("size"),
                        title="ERASING"
            )

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

def copy():
            global index
            disp.fill(0)
            disp.show()
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
            disp.image(image)
            disp.show()
            wait_for_buttons_release([button_L, button_R, button_A, button_B, button_C])
            prev_states = {
                        "L": button_L.value,
                        "R": button_R.value,
                        "A": button_A.value,
                        "B": button_B.value,
                        "C": button_C.value,
            }
            try:
                        while 1:
                                    current_R = button_R.value
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
                                                            disp.image(image)
                                                            disp.show()
                                                            time.sleep(.01)
                                    current_L = button_L.value
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
                                                            #disp.image(image)
                                                            #disp.show()
                                                            #print("YES" + str(index))
                                                            #lcdstart = datetime.now()
                                                            #run_once = 0
                                                else:
                                                            # Display image.
                                                            disp.image(image)
                                                            disp.show()
                                                            time.sleep(.01)
                                    current_B = button_B.value
                                    if prev_states["B"] and not current_B:
                                                disp.fill(0)
                                                disp.show()
                                                log_debug("Copy menu: Button B pressed")
                                                basemenu()
                                                disp.show()
                                                return
                                    current_A = button_A.value
                                    if prev_states["A"] and not current_A:
                                                disp.fill(0)
                                                disp.show()
                                                log_debug("Copy menu: Button A pressed")
                                                basemenu()
                                                disp.show()
                                                return
                                    current_C = button_C.value
                                    if prev_states["C"] and not current_C:
                                                if confirm_selection == CONFIRM_YES:
                                                            display_lines(["COPY", "Starting..."])
                                                            if clone_device(source, target):
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
                                    prev_states["R"] = current_R
                                    prev_states["L"] = current_L
                                    prev_states["B"] = current_B
                                    prev_states["A"] = current_A
                                    prev_states["C"] = current_C
                                    menu.footer_selected_index = confirm_selection
                                    render_menu(menu, draw, width, height, fonts)
                                    disp.image(image)
                                    disp.show()
            except KeyboardInterrupt:
                        raise

def view():
            view_devices()
            time.sleep(2)
            basemenu()

def erase():
            global index
            disp.fill(0)
            disp.show()
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
            title = f"ERASE {target_name}?"
            menu = Menu(
                        items=[],
                        title=title,
                        footer=["NO", "YES"],
                        footer_positions=[x + 24, x + 52],
            )
            confirm_selection = CONFIRM_NO
            menu.footer_selected_index = confirm_selection
            render_menu(menu, draw, width, height, fonts)
            disp.image(image)
            disp.show()
            wait_for_buttons_release([button_L, button_R, button_A, button_B, button_C])
            prev_states = {
                        "L": button_L.value,
                        "R": button_R.value,
                        "A": button_A.value,
                        "B": button_B.value,
                        "C": button_C.value,
            }
            try:
                        while 1:
                                    current_R = button_R.value
                                    if prev_states["R"] and not current_R:
                                                if confirm_selection == CONFIRM_NO:
                                                            confirm_selection = CONFIRM_YES
                                                            log_debug("Erase menu selection changed: YES")
                                                elif confirm_selection == CONFIRM_YES:
                                                            confirm_selection = CONFIRM_YES
                                                            log_debug("Erase menu selection changed: YES")
                                    current_L = button_L.value
                                    if prev_states["L"] and not current_L:
                                                if confirm_selection == CONFIRM_YES:
                                                            confirm_selection = CONFIRM_NO
                                                            log_debug("Erase menu selection changed: NO")
                                    current_A = button_A.value
                                    if prev_states["A"] and not current_A:
                                                basemenu()
                                                return
                                    current_B = button_B.value
                                    if prev_states["B"] and not current_B:
                                                if confirm_selection == CONFIRM_YES:
                                                            if not ensure_root_for_erase():
                                                                        return
                                                            display_lines(["ERASE", "Starting..."])
                                                            if erase_device(target):
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
                                    current_C = button_C.value
                                    if prev_states["C"] and not current_C:
                                                if confirm_selection == CONFIRM_YES:
                                                            if not ensure_root_for_erase():
                                                                        return
                                                            display_lines(["ERASE", "Starting..."])
                                                            if erase_device(target):
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
                                    prev_states["R"] = current_R
                                    prev_states["L"] = current_L
                                    prev_states["A"] = current_A
                                    prev_states["B"] = current_B
                                    prev_states["C"] = current_C
                                    menu.footer_selected_index = confirm_selection
                                    render_menu(menu, draw, width, height, fonts)
                                    disp.image(image)
                                    disp.show()
            except KeyboardInterrupt:
                        raise

def sleepdisplay():  # put the display to sleep to reduce power
            global run_once
            disp.fill(0)
            disp.show()
            draw.rectangle((0, 0, width, height), outline=0, fill=0)
            disp.image(image)
            disp.show()
            run_once = 1

def cleanup(clear_display=True):
            if clear_display:
                        disp.fill(0)
                        disp.show()
            GPIO.cleanup()

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
                        if button_U.value: # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    log_debug("Button UP pressed")
                                    devices = list_media_devices()
                                    if devices:
                                                previous_index = usb_list_index
                                                usb_list_index = max(usb_list_index - 1, 0)
                                                if usb_list_index != previous_index:
                                                            basemenu()
                                    disp.image(image)
                                    disp.show()
                                    lcdstart = datetime.now()
                                    run_once = 0
                        if button_L.value: # button is released
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
                                                disp.image(image)
                                                disp.show()
                                                time.sleep(.01)
                        if button_R.value: # button is released
                                    filler =(0)
                        else: # button is pressed:
                                    if index == MENU_NONE:
                                                index = MENU_COPY
                                                log_debug("Menu selection changed: index=0 (COPY)")
                                                basemenu()
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    elif index == MENU_COPY:
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
                                                disp.image(image)
                                                disp.show()
                                                time.sleep(.01)
                        if button_D.value: # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    log_debug("Button DOWN pressed")
                                    devices = list_media_devices()
                                    if devices:
                                                previous_index = usb_list_index
                                                usb_list_index = min(usb_list_index + 1, len(devices) - 1)
                                                if usb_list_index != previous_index:
                                                            basemenu()
                        if button_C.value: # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    filler = (0)
                                    log_debug("Button C pressed")
                        if button_A.value: # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    disp.fill(0)
                                    disp.show()
                                    log_debug("Button A pressed")
                                    basemenu()
                                    disp.show()
                        if button_B.value: # button is released
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
            disp.fill(0)
            disp.show()
            draw.rectangle((0,0,width,height), outline=0, fill=0)
            draw.text((x, top + 30), "ERROR", font=fontinsert, fill=255)
            disp.image(image)
            disp.show()
finally:
            cleanup(clear_display=not error_displayed)
