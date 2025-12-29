import time
import datetime
import subprocess
import RPi.GPIO as GPIO
import os
import json
import shutil
import re
import select
from mount import *
import sys
import argparse
from dataclasses import dataclass
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from datetime import datetime, timedelta
from time import sleep, strftime, localtime

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

PIN_A = 5
PIN_B = 6
PIN_L = 27
PIN_R = 23
PIN_U = 17
PIN_D = 22
PIN_C = 4

GPIO.setup(PIN_A, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_L, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_R, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_U, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_D, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_C, GPIO.IN, pull_up_down=GPIO.PUD_UP)

parser = argparse.ArgumentParser(description="Raspberry Pi USB Cloner")
parser.add_argument("-d", "--debug", action="store_true", help="Enable verbose debug output")
args = parser.parse_args()
DEBUG = args.debug
CLONE_MODE = os.environ.get("CLONE_MODE", "smart").lower()

def normalize_clone_mode(mode):
            if not mode:
                        return "smart"
            mode = mode.lower()
            if mode == "raw":
                        return "exact"
            if mode in ("smart", "exact", "verify"):
                        return mode
            return "smart"

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

# Load fonts.
font = ImageFont.load_default()
font_title = ImageFont.truetype("rainyhearts.ttf", 14)
font_body = ImageFont.truetype("slkscr.ttf", 10)
font_small = ImageFont.truetype("slkscr.ttf", 8)
fonts = {
            "title": font_title,
            "items_primary": font_body,
            "items_secondary": font_small,
            "footer": font_body,
            "primary": font_title,
            "secondary": font_body,
            "tertiary": font_small,
}

# Get drawing object to draw on image.
draw = ImageDraw.Draw(image)
MENU_COPY = 0
MENU_VIEW = 1
MENU_ERASE = 2
MENU_NONE = -1

CONFIRM_NO = 0
CONFIRM_YES = 1
QUICK_WIPE_MIB = 32

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

def get_line_height(font, fallback=8):
            try:
                        bbox = font.getbbox("Ag")
                        return max(bbox[3] - bbox[1], fallback)
            except AttributeError:
                        if hasattr(font, "getmetrics"):
                                    ascent, descent = font.getmetrics()
                                    return max(ascent + descent, fallback)
            return fallback

def render_menu(menu, draw, width, height, fonts):
            draw.rectangle((0, 0, width, height), outline=0, fill=0)
            current_y = top
            if menu.title:
                        title_font = fonts["title"]
                        draw.text((x - 11, current_y), menu.title, font=title_font, fill=255)
                        current_y += get_line_height(title_font, 10) + 2
            if menu.content_top is not None:
                        current_y = menu.content_top

            items_primary_font = menu.items_font or fonts["items_primary"]
            items_secondary_font = fonts["items_secondary"]

            for item_index, item in enumerate(menu.items):
                        lines = item.lines
                        line_fonts = []
                        line_heights = []
                        for line_index, _line in enumerate(lines):
                                    line_font = items_primary_font if line_index == 0 else items_secondary_font
                                    line_fonts.append(line_font)
                                    line_heights.append(get_line_height(line_font, 8) + 1)
                        row_height = sum(line_heights) + 4 if line_heights else get_line_height(items_primary_font, 8) + 4
                        row_top = current_y
                        is_selected = item_index == menu.selected_index
                        if is_selected:
                                    draw.rectangle((0, row_top - 1, width, row_top + row_height - 1), outline=0, fill=1)
                        line_y = row_top
                        for line_index, line in enumerate(lines):
                                    line_font = line_fonts[line_index]
                                    text_color = 0 if is_selected else 255
                                    draw.text((x - 11, line_y), line, font=line_font, fill=text_color)
                                    line_y += line_heights[line_index]
                        current_y += row_height

            if menu.footer:
                        footer_font = fonts["footer"]
                        footer_y = height - get_line_height(footer_font, 8) - 2
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
            if not devices:  # If nothing in devices list (No USB connected), display "INSERT USB".
                        draw.rectangle((0, 0, width, height), outline=0, fill=0)
                        text = "INSERT USB"
                        text_bbox = draw.textbbox((0, 0), text, font=fonts["primary"])
                        text_width = text_bbox[2] - text_bbox[0]
                        text_height = text_bbox[3] - text_bbox[1]
                        text_x = (width - text_width) // 2
                        text_y = (height - text_height) // 2
                        draw.text((text_x, text_y), text, font=fonts["primary"], fill=255)
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
            disp.display(image)
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
                        disp.display(image)
                        time.sleep(.01)

global run_once
run_once = 0

#setup the  go to sleep timer
lcdstart = datetime.now()

# Copy USB Screen
def display_lines(lines, primary_font=None, secondary_font=None, tertiary_font=None):
            draw.rectangle((0, 0, width, height), outline=0, fill=0)
            primary_font = primary_font or fonts["primary"]
            secondary_font = secondary_font or fonts["secondary"]
            tertiary_font = tertiary_font or fonts["tertiary"]
            y = top
            for index, line in enumerate(lines[:6]):
                        if index == 0:
                                    line_font = primary_font
                        elif index == 1:
                                    line_font = secondary_font
                        else:
                                    line_font = tertiary_font
                        line_height = get_line_height(line_font, 8)
                        if y + line_height > height:
                                    break
                        draw.text((x - 11, y), line, font=line_font, fill=255)
                        y += line_height + 2
            disp.display(image)

def ensure_root_for_erase():
            if os.geteuid() != 0:
                        display_lines(["Run as root"])
                        time.sleep(1)
                        basemenu()
                        return False
            return True

def wait_for_buttons_release(buttons, poll_delay=0.05):
            while any(GPIO.input(pin) == GPIO.LOW for pin in buttons):
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

def format_device_label(device):
            if isinstance(device, dict):
                        name = device.get("name") or ""
                        size_label = human_size(device.get("size"))
            else:
                        name = str(device or "")
                        size_label = ""
            if size_label:
                        size_label = re.sub(r"\.0([A-Z])", r"\1", size_label)
                        return f"{name} {size_label}".strip()
            return name

def format_eta(seconds):
            if seconds is None:
                        return None
            seconds = int(seconds)
            if seconds < 0:
                        return None
            hours, remainder = divmod(seconds, 3600)
            minutes, secs = divmod(remainder, 60)
            if hours:
                        return f"{hours:d}:{minutes:02d}:{secs:02d}"
            return f"{minutes:02d}:{secs:02d}"

def format_progress_lines(title, device, mode, bytes_copied, total_bytes, rate, eta):
            lines = []
            if title:
                        lines.append(title)
            if device:
                        lines.append(device)
            if mode:
                        lines.append(f"Mode {mode}")
            if bytes_copied is not None:
                        percent = ""
                        if total_bytes:
                                    percent = f"{(bytes_copied / total_bytes) * 100:.1f}%"
                        written_line = f"Wrote {human_size(bytes_copied)}"
                        if percent:
                                    written_line = f"{written_line} {percent}"
                        lines.append(written_line)
            else:
                        lines.append("Working...")
            if rate:
                        rate_line = f"{human_size(rate)}/s"
                        if eta:
                                    rate_line = f"{rate_line} ETA {eta}"
                        lines.append(rate_line)
            return lines[:6]

def format_progress_display(title, device, mode, bytes_copied, total_bytes, percent, rate, eta, spinner=None):
            lines = []
            if title:
                        title_line = title
                        if spinner:
                                    title_line = f"{title} {spinner}"
                        lines.append(title_line)
            if device:
                        lines.append(device)
            if mode:
                        lines.append(f"Mode {mode}")
            if bytes_copied is not None:
                        percent_display = ""
                        if total_bytes:
                                    percent_display = f"{(bytes_copied / total_bytes) * 100:.1f}%"
                        elif percent is not None:
                                    percent_display = f"{percent:.1f}%"
                        written_line = f"Wrote {human_size(bytes_copied)}"
                        if percent_display:
                                    written_line = f"{written_line} {percent_display}"
                        lines.append(written_line)
            elif percent is not None:
                        lines.append(f"{percent:.1f}%")
            else:
                        lines.append("Working...")
            if rate:
                        rate_line = f"{human_size(rate)}/s"
                        if eta:
                                    rate_line = f"{rate_line} ETA {eta}"
                        lines.append(rate_line)
            return lines[:6]

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

def get_partition_number(name):
            if not name:
                        return None
            match = re.search(r"(?:p)?(\d+)$", name)
            if not match:
                        return None
            return int(match.group(1))

def get_device_by_name(name):
            if not name:
                        return None
            for device in get_block_devices():
                        if device.get("name") == name:
                                    return device
            return None

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

def run_progress_command(command, total_bytes=None, title="WORKING", device_label=None, mode_label=None):
            display_lines(format_progress_display(title, device_label, mode_label, 0 if total_bytes else None, total_bytes, None, None, None))
            log_debug(f"Starting command: {' '.join(command)}")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            last_update = time.time()
            last_bytes = None
            last_time = None
            last_rate = None
            last_eta = None
            last_percent = None
            spinner_frames = ["|", "/", "-", "\\"]
            spinner_index = 0
            refresh_interval = 1.0
            while True:
                        ready, _, _ = select.select([process.stderr], [], [], refresh_interval)
                        now = time.time()
                        line = None
                        if ready:
                                    line = process.stderr.readline()
                        if line:
                                    log_debug(f"stderr: {line.strip()}")
                                    bytes_match = re.search(r"(\d+)\s+bytes", line)
                                    percent_match = re.search(r"(\d+(?:\.\d+)?)%", line)
                                    rate_match = re.search(r"(\d+(?:\.\d+)?)\s*MiB/s", line)
                                    bytes_copied = last_bytes
                                    rate = last_rate
                                    eta = last_eta
                                    if bytes_match:
                                                bytes_copied = int(bytes_match.group(1))
                                                if rate_match:
                                                            rate = float(rate_match.group(1)) * 1024 * 1024
                                                else:
                                                            rate = None
                                                            if last_bytes is not None and last_time is not None:
                                                                        delta_bytes = bytes_copied - last_bytes
                                                                        delta_time = now - last_time
                                                                        if delta_bytes >= 0 and delta_time > 0:
                                                                                    rate = delta_bytes / delta_time
                                                if rate and total_bytes and bytes_copied <= total_bytes:
                                                            eta_seconds = (total_bytes - bytes_copied) / rate if rate > 0 else None
                                                            eta = format_eta(eta_seconds)
                                                last_bytes = bytes_copied
                                                last_time = now
                                                last_rate = rate or last_rate
                                                last_eta = eta or last_eta
                                    if percent_match:
                                                last_percent = float(percent_match.group(1))
                                    rate_display = rate if rate is not None else last_rate
                                    eta_display = eta if eta is not None else last_eta
                                    display_lines(format_progress_display(
                                                title,
                                                device_label,
                                                mode_label,
                                                bytes_copied,
                                                total_bytes,
                                                last_percent,
                                                rate_display,
                                                eta_display,
                                                spinner_frames[spinner_index],
                                    ))
                                    last_update = now
                        if now - last_update >= refresh_interval:
                                    spinner_index = (spinner_index + 1) % len(spinner_frames)
                                    display_lines(format_progress_display(
                                                title,
                                                device_label,
                                                mode_label,
                                                last_bytes,
                                                total_bytes,
                                                last_percent,
                                                last_rate,
                                                last_eta,
                                                spinner_frames[spinner_index],
                                    ))
                                    last_update = now
                        if process.poll() is not None and not line:
                                    break
            if process.returncode != 0:
                        error_output = process.stderr.read().strip()
                        message = error_output.splitlines()[-1] if error_output else "Command failed"
                        display_lines(["FAILED", message[:20]])
                        log_debug(f"Command failed with code {process.returncode}: {message}")
                        return False
            display_lines([title, "Complete"])
            log_debug("Command completed successfully")
            return True

def parse_progress(stderr_output, total_bytes=None, title="WORKING"):
            if not stderr_output:
                        return
            for line in stderr_output.splitlines():
                        log_debug(f"stderr: {line.strip()}")
                        bytes_match = re.search(r"(\d+)\s+bytes", line)
                        percent_match = re.search(r"(\d+(?:\.\d+)?)%", line)
                        if bytes_match:
                                    bytes_copied = int(bytes_match.group(1))
                                    percent = ""
                                    if total_bytes:
                                                percent = f"{(bytes_copied / total_bytes) * 100:.1f}%"
                                    elif percent_match:
                                                percent = f"{percent_match.group(1)}%"
                                    display_lines([title, f"{human_size(bytes_copied)} {percent}".strip()])
                                    continue
                        if percent_match and not total_bytes:
                                    display_lines([title, f"{percent_match.group(1)}%"])

def run_checked_with_progress(command, total_bytes=None, title="WORKING", stdout_target=None):
            display_lines([title, "Starting..."])
            log_debug(f"Running command: {' '.join(command)}")
            result = subprocess.run(
                        command,
                        stdout=stdout_target or subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
            )
            parse_progress(result.stderr, total_bytes=total_bytes, title=title)
            if result.returncode != 0:
                        stderr = result.stderr.strip()
                        stdout = result.stdout.strip() if result.stdout else ""
                        message = stderr or stdout or "Command failed"
                        raise RuntimeError(f"Command failed ({' '.join(command)}): {message}")
            display_lines([title, "Complete"])
            return result

def clone_dd(src, dst, total_bytes=None, title="CLONING"):
            dd_path = shutil.which("dd")
            if not dd_path:
                        raise RuntimeError("dd not found")
            src_node = resolve_device_node(src)
            dst_node = resolve_device_node(dst)
            run_checked_with_progress(
                        [dd_path, f"if={src_node}", f"of={dst_node}", "bs=4M", "status=progress", "conv=fsync"],
                        total_bytes=total_bytes,
                        title=title,
            )

def clone_partclone(source, target):
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
            source_node = resolve_device_node(source)
            target_node = resolve_device_node(target)
            source_name = os.path.basename(source_node)
            target_name = os.path.basename(target_node)
            source_device = get_device_by_name(source_name) or (source if isinstance(source, dict) else None)
            target_device = get_device_by_name(target_name) or (target if isinstance(target, dict) else None)
            if not source_device or not target_device:
                        clone_dd(source_node, target_node, total_bytes=source.get("size") if isinstance(source, dict) else None)
                        return
            source_parts = [child for child in get_children(source_device) if child.get("type") == "part"]
            if not source_parts:
                        clone_dd(source_node, target_node, total_bytes=source_device.get("size"))
                        return
            target_parts = [child for child in get_children(target_device) if child.get("type") == "part"]
            target_parts_by_number = {}
            for child in target_parts:
                        part_number = get_partition_number(child.get("name"))
                        if part_number is None:
                                    continue
                        target_parts_by_number.setdefault(part_number, child)
            for index, part in enumerate(source_parts, start=1):
                        src_part = f"/dev/{part.get('name')}"
                        part_number = get_partition_number(part.get("name"))
                        dst_part = None
                        if part_number is not None:
                                    target_part = target_parts_by_number.get(part_number)
                                    if target_part:
                                                dst_part = f"/dev/{target_part.get('name')}"
                        if not dst_part and index - 1 < len(target_parts):
                                    dst_part = f"/dev/{target_parts[index - 1].get('name')}"
                        if not dst_part:
                                    raise RuntimeError(f"Unable to map {src_part} to target partition")
                        fstype = (part.get("fstype") or "").lower()
                        tool = partclone_tools.get(fstype)
                        tool_path = shutil.which(tool) if tool else None
                        if not tool_path:
                                    clone_dd(src_part, dst_part, total_bytes=part.get("size"), title=f"DD {index}/{len(source_parts)}")
                                    continue
                        display_lines([f"PART {index}/{len(source_parts)}", tool])
                        with open(dst_part, "wb") as dst_handle:
                                    run_checked_with_progress(
                                                [tool_path, "-s", src_part, "-o", "-", "-f"],
                                                total_bytes=part.get("size"),
                                                title=f"PART {index}/{len(source_parts)}",
                                                stdout_target=dst_handle,
                                    )

def compute_sha256(device_node, total_bytes=None, title="VERIFY"):
            dd_path = shutil.which("dd")
            sha_path = shutil.which("sha256sum")
            if not dd_path or not sha_path:
                        raise RuntimeError("dd or sha256sum not found")
            log_debug(f"Computing sha256 for {device_node}")
            display_lines([title, "Starting..."])
            dd_cmd = [dd_path, f"if={device_node}", "bs=4M", "status=progress"]
            if total_bytes:
                        total_bytes = int(total_bytes)
                        dd_cmd.extend([f"count={total_bytes}", "iflag=count_bytes"])
            dd_proc = subprocess.Popen(
                        dd_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
            )
            sha_proc = subprocess.Popen(
                        [sha_path],
                        stdin=dd_proc.stdout,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
            )
            if dd_proc.stdout:
                        dd_proc.stdout.close()
            last_update = time.time()
            while True:
                        line = dd_proc.stderr.readline()
                        if line:
                                    log_debug(f"dd: {line.strip()}")
                                    match = re.search(r"(\d+)\s+bytes", line)
                                    if match:
                                                bytes_copied = int(match.group(1))
                                                percent = ""
                                                if total_bytes:
                                                            percent = f"{(bytes_copied / total_bytes) * 100:.1f}%"
                                                display_lines([title, f"{human_size(bytes_copied)} {percent}".strip()])
                                                last_update = time.time()
                        if dd_proc.poll() is not None:
                                    break
                        if time.time() - last_update > 5:
                                    display_lines([title, "Working..."])
                                    last_update = time.time()
            dd_proc.wait()
            sha_out, sha_err = sha_proc.communicate()
            if dd_proc.returncode != 0:
                        error_output = dd_proc.stderr.read().strip()
                        message = error_output.splitlines()[-1] if error_output else "dd failed"
                        raise RuntimeError(message)
            if sha_proc.returncode != 0:
                        message = sha_err.strip() or "sha256sum failed"
                        raise RuntimeError(message)
            checksum = sha_out.split()[0] if sha_out else ""
            display_lines([title, "Complete"])
            log_debug(f"sha256 for {device_node}: {checksum}")
            return checksum

def verify_clone(source, target):
            source_node = resolve_device_node(source)
            target_node = resolve_device_node(target)
            source_name = os.path.basename(source_node)
            target_name = os.path.basename(target_node)
            source_device = get_device_by_name(source_name) or (source if isinstance(source, dict) else None)
            target_device = get_device_by_name(target_name) or (target if isinstance(target, dict) else None)
            if not source_device or not target_device:
                        return verify_clone_device(source_node, target_node, source.get("size") if isinstance(source, dict) else None)
            source_parts = [child for child in get_children(source_device) if child.get("type") == "part"]
            if not source_parts:
                        return verify_clone_device(source_node, target_node, source_device.get("size"))
            target_parts = [child for child in get_children(target_device) if child.get("type") == "part"]
            target_parts_by_number = {}
            for child in target_parts:
                        part_number = get_partition_number(child.get("name"))
                        if part_number is None:
                                    continue
                        target_parts_by_number.setdefault(part_number, child)
            total_parts = len(source_parts)
            for index, part in enumerate(source_parts, start=1):
                        src_part = f"/dev/{part.get('name')}"
                        part_number = get_partition_number(part.get("name"))
                        dst_part = None
                        if part_number is not None:
                                    target_part = target_parts_by_number.get(part_number)
                                    if target_part:
                                                dst_part = f"/dev/{target_part.get('name')}"
                        if not dst_part and index - 1 < len(target_parts):
                                    dst_part = f"/dev/{target_parts[index - 1].get('name')}"
                        if not dst_part:
                                    display_lines(["VERIFY", "No target part"])
                                    log_debug(f"Verify failed: no target partition for {src_part}")
                                    return False
                        print(f"Verifying {src_part} -> {dst_part}")
                        try:
                                    src_hash = compute_sha256(src_part, total_bytes=part.get("size"), title=f"V {index}/{total_parts} SRC")
                                    dst_hash = compute_sha256(dst_part, total_bytes=part.get("size"), title=f"V {index}/{total_parts} DST")
                        except RuntimeError as error:
                                    display_lines(["VERIFY", "Error"])
                                    log_debug(f"Verify failed ({src_part} -> {dst_part}): {error}")
                                    return False
                        if src_hash != dst_hash:
                                    display_lines(["VERIFY", "Mismatch"])
                                    log_debug(f"Verify mismatch for {src_part} -> {dst_part}")
                                    print(f"Verify failed: {src_part} -> {dst_part}")
                                    return False
            display_lines(["VERIFY", "Complete"])
            print("Verify complete: all partitions match")
            return True

def verify_clone_device(source_node, target_node, total_bytes=None):
            print(f"Verifying {source_node} -> {target_node}")
            try:
                        src_hash = compute_sha256(source_node, total_bytes=total_bytes, title="VERIFY SRC")
                        dst_hash = compute_sha256(target_node, total_bytes=total_bytes, title="VERIFY DST")
            except RuntimeError as error:
                        display_lines(["VERIFY", "Error"])
                        log_debug(f"Verify failed: {error}")
                        return False
            if src_hash != dst_hash:
                        display_lines(["VERIFY", "Mismatch"])
                        log_debug(f"Verify mismatch for {source_node} -> {target_node}")
                        print("Verify failed: checksum mismatch")
                        return False
            display_lines(["VERIFY", "Complete"])
            print("Verify complete: checksums match")
            return True

def clone_device(source, target, mode=None):
            mode = normalize_clone_mode(mode or CLONE_MODE)
            if mode in ("smart", "verify"):
                        success = clone_device_smart(source, target)
                        if not success:
                                    return False
                        if mode == "verify":
                                    return verify_clone(source, target)
                        return True
            unmount_device(target)
            try:
                        clone_dd(source, target, total_bytes=source.get("size"), title="CLONING")
            except RuntimeError as error:
                        display_lines(["FAILED", str(error)[:20]])
                        log_debug(f"Clone failed: {error}")
                        return False
            return True

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
            try:
                        clone_partclone(source, target)
            except RuntimeError as error:
                        display_lines(["FAILED", str(error)[:20]])
                        log_debug(f"Smart clone failed ({source_node} -> {target_node}): {error}")
                        return False
            display_lines(["CLONING", "Complete"])
            log_debug(f"Smart clone completed from {source_node} to {target_node}")
            return True

def erase_device(target, mode):
            target_node = f"/dev/{target.get('name')}"
            unmount_device(target)
            mode = (mode or "").lower()
            device_label = format_device_label(target)
            mode_label = mode.upper() if mode else None
            if mode == "secure":
                        shred_path = shutil.which("shred")
                        if not shred_path:
                                    display_lines(["ERROR", "no shred tool"])
                                    log_debug("Erase failed: shred not available")
                                    return False
                        return run_progress_command(
                                    [shred_path, "-v", "-n", "1", "-z", target_node],
                                    total_bytes=target.get("size"),
                                    title="ERASING",
                                    device_label=device_label,
                                    mode_label=mode_label,
                        )
            if mode == "discard":
                        discard_path = shutil.which("blkdiscard")
                        if not discard_path:
                                    display_lines(["ERROR", "no discard"])
                                    log_debug("Erase failed: blkdiscard not available")
                                    return False
                        return run_progress_command(
                                    [discard_path, target_node],
                                    title="ERASING",
                                    device_label=device_label,
                                    mode_label=mode_label,
                        )
            if mode == "zero":
                        dd_path = shutil.which("dd")
                        if not dd_path:
                                    display_lines(["ERROR", "no dd tool"])
                                    log_debug("Erase failed: dd not available")
                                    return False
                        return run_progress_command(
                                    [dd_path, "if=/dev/zero", f"of={target_node}", "bs=4M", "status=progress", "conv=fsync"],
                                    total_bytes=target.get("size"),
                                    title="ERASING",
                                    device_label=device_label,
                                    mode_label=mode_label,
                        )
            if mode != "quick":
                        display_lines(["ERROR", "unknown mode"])
                        log_debug(f"Erase failed: unknown mode {mode}")
                        return False
            wipefs_path = shutil.which("wipefs")
            if not wipefs_path:
                        display_lines(["ERROR", "no wipefs"])
                        log_debug("Erase failed: wipefs not available")
                        return False
            dd_path = shutil.which("dd")
            if not dd_path:
                        display_lines(["ERROR", "no dd tool"])
                        log_debug("Erase failed: dd not available")
                        return False
            if not run_progress_command(
                        [wipefs_path, "-a", target_node],
                        title="ERASING",
                        device_label=device_label,
                        mode_label=mode_label,
            ):
                        return False
            size_bytes = target.get("size") or 0
            bytes_per_mib = 1024 * 1024
            size_mib = size_bytes // bytes_per_mib if size_bytes else 0
            wipe_mib = min(QUICK_WIPE_MIB, size_mib) if size_mib else QUICK_WIPE_MIB
            wipe_bytes = wipe_mib * bytes_per_mib
            if not run_progress_command(
                        [dd_path, "if=/dev/zero", f"of={target_node}", "bs=1M", f"count={wipe_mib}", "status=progress", "conv=fsync"],
                        total_bytes=wipe_bytes,
                        title="ERASING",
                        device_label=device_label,
                        mode_label=mode_label,
            ):
                        return False
            if size_mib > wipe_mib:
                        seek_mib = size_mib - wipe_mib
                        return run_progress_command(
                                    [dd_path, "if=/dev/zero", f"of={target_node}", "bs=1M", f"count={wipe_mib}", f"seek={seek_mib}", "status=progress", "conv=fsync"],
                                    total_bytes=wipe_bytes,
                                    title="ERASING",
                                    device_label=device_label,
                                    mode_label=mode_label,
                        )
            return True

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
                        "U": GPIO.input(PIN_U),
                        "D": GPIO.input(PIN_D),
                        "L": GPIO.input(PIN_L),
                        "R": GPIO.input(PIN_R),
                        "A": GPIO.input(PIN_A),
                        "B": GPIO.input(PIN_B),
                        "C": GPIO.input(PIN_C),
            }
            while True:
                        current_U = GPIO.input(PIN_U)
                        if prev_states["U"] and not current_U:
                                    selected_index = max(0, selected_index - 1)
                                    log_debug(f"Clone mode selection changed: {modes[selected_index]}")
                        current_D = GPIO.input(PIN_D)
                        if prev_states["D"] and not current_D:
                                    selected_index = min(len(modes) - 1, selected_index + 1)
                                    log_debug(f"Clone mode selection changed: {modes[selected_index]}")
                        current_L = GPIO.input(PIN_L)
                        if prev_states["L"] and not current_L:
                                    selected_index = max(0, selected_index - 1)
                        current_R = GPIO.input(PIN_R)
                        if prev_states["R"] and not current_R:
                                    selected_index = min(len(modes) - 1, selected_index + 1)
                        current_A = GPIO.input(PIN_A)
                        if prev_states["A"] and not current_A:
                                    return None
                        current_B = GPIO.input(PIN_B)
                        if prev_states["B"] and not current_B:
                                    return modes[selected_index]
                        current_C = GPIO.input(PIN_C)
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
                        footer=["BACK", "OK"],
                        footer_positions=[x + 12, x + 63],
            )
            render_menu(menu, draw, width, height, fonts)
            disp.display(image)
            wait_for_buttons_release([PIN_U, PIN_D, PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
            prev_states = {
                        "U": GPIO.input(PIN_U),
                        "D": GPIO.input(PIN_D),
                        "L": GPIO.input(PIN_L),
                        "R": GPIO.input(PIN_R),
                        "A": GPIO.input(PIN_A),
                        "B": GPIO.input(PIN_B),
                        "C": GPIO.input(PIN_C),
            }
            while True:
                        current_U = GPIO.input(PIN_U)
                        if prev_states["U"] and not current_U:
                                    selected_index = max(0, selected_index - 1)
                                    log_debug(f"Erase mode selection changed: {modes[selected_index]}")
                        current_D = GPIO.input(PIN_D)
                        if prev_states["D"] and not current_D:
                                    selected_index = min(len(modes) - 1, selected_index + 1)
                                    log_debug(f"Erase mode selection changed: {modes[selected_index]}")
                        current_L = GPIO.input(PIN_L)
                        if prev_states["L"] and not current_L:
                                    selected_index = max(0, selected_index - 1)
                        current_R = GPIO.input(PIN_R)
                        if prev_states["R"] and not current_R:
                                    selected_index = min(len(modes) - 1, selected_index + 1)
                        current_A = GPIO.input(PIN_A)
                        if prev_states["A"] and not current_A:
                                    return None
                        current_B = GPIO.input(PIN_B)
                        if prev_states["B"] and not current_B:
                                    return modes[selected_index]
                        current_C = GPIO.input(PIN_C)
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
                        "L": GPIO.input(PIN_L),
                        "R": GPIO.input(PIN_R),
                        "A": GPIO.input(PIN_A),
                        "B": GPIO.input(PIN_B),
                        "C": GPIO.input(PIN_C),
            }
            try:
                        while 1:
                                    current_R = GPIO.input(PIN_R)
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
                                    current_L = GPIO.input(PIN_L)
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
                                    current_A = GPIO.input(PIN_A)
                                    if prev_states["A"] and not current_A:
                                                log_debug("Copy menu: Button A pressed")
                                                basemenu()
                                                return
                                    current_B = GPIO.input(PIN_B)
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
                                    current_C = GPIO.input(PIN_C)
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
                        "L": GPIO.input(PIN_L),
                        "R": GPIO.input(PIN_R),
                        "A": GPIO.input(PIN_A),
                        "B": GPIO.input(PIN_B),
                        "C": GPIO.input(PIN_C),
            }
            try:
                        while 1:
                                    current_R = GPIO.input(PIN_R)
                                    if prev_states["R"] and not current_R:
                                                if confirm_selection == CONFIRM_NO:
                                                            confirm_selection = CONFIRM_YES
                                                            log_debug("Erase menu selection changed: YES")
                                                elif confirm_selection == CONFIRM_YES:
                                                            confirm_selection = CONFIRM_YES
                                                            log_debug("Erase menu selection changed: YES")
                                    current_L = GPIO.input(PIN_L)
                                    if prev_states["L"] and not current_L:
                                                if confirm_selection == CONFIRM_YES:
                                                            confirm_selection = CONFIRM_NO
                                                            log_debug("Erase menu selection changed: NO")
                                    current_A = GPIO.input(PIN_A)
                                    if prev_states["A"] and not current_A:
                                                basemenu()
                                                return
                                    current_B = GPIO.input(PIN_B)
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
                                    current_C = GPIO.input(PIN_C)
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

def cleanup(clear_display=True):
            if clear_display:
                        disp.clear()
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
                        if GPIO.input(PIN_U): # button is released
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
                        if GPIO.input(PIN_L): # button is released
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
                        if GPIO.input(PIN_R): # button is released
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
                                                disp.display(image)
                                                time.sleep(.01)
                        if GPIO.input(PIN_D): # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    log_debug("Button DOWN pressed")
                                    devices = list_media_devices()
                                    if devices:
                                                previous_index = usb_list_index
                                                usb_list_index = min(usb_list_index + 1, len(devices) - 1)
                                                if usb_list_index != previous_index:
                                                            basemenu()
                        if GPIO.input(PIN_C): # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    filler = (0)
                                    log_debug("Button C pressed")
                        if GPIO.input(PIN_A): # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    log_debug("Button A pressed")
                                    basemenu()
                        if GPIO.input(PIN_B): # button is released
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
            draw.text((x, top + 30), "ERROR", font=fonts["primary"], fill=255)
            disp.display(image)
finally:
            cleanup(clear_display=not error_displayed)
