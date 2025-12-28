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

from digitalio import DigitalInOut, Direction, Pull
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
from datetime import datetime, timedelta
from time import sleep, strftime, localtime

parser = argparse.ArgumentParser(description="Raspberry Pi USB Cloner")
parser.add_argument("-d", "--debug", action="store_true", help="Enable verbose debug output")
args = parser.parse_args()
DEBUG = args.debug

def log_debug(message):
            if DEBUG:
                        print(f"[DEBUG] {message}")

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

# Get drawing object to draw on image.
draw = ImageDraw.Draw(image)
index = 0

# Draw a black filled box to clear the image.
draw.rectangle((0, 0, width, height), outline=0, fill=0)

usb = 0
ENABLE_SLEEP = False
USB_REFRESH_INTERVAL = 2.0

def basemenu():
            global lcdstart
            global run_once
            disp.fill(0)
            disp.show()
            devices = list_media_devices()  #This is mount.py stuff.
            seconditem = 0  # This was to ensure the second USB drive info displayed after and not over the top of the first drives info. Got a better way? Please help.
            if not devices:  # If nothing in devices list (No USB connected), display "INSERT USB".
                        disp.fill(0)
                        # draw.rectangle((0,0,width,height), outline=0, fill=0)
                        # splash1 = Image.open('usb.png').convert('1')
                        # disp.image(splash1)
                        draw.rectangle((0, 0, width, height), outline=0, fill=0)  # To hide previous USB information after USB removal.
                        draw.text((x, top + 30), "INSERT USB", font=fontinsert, fill=255)
                        usb = 0
            else:  # If USB is connected.
                        draw.rectangle((0, 0, width, height), outline=0, fill=0)
                        for device in devices:  # This is mount.py stuff.
                                    draw.text((x - 11, top + 2 + seconditem),(get_device_name(device)) + " " + "%.2f" % (get_size(device) / 1024 ** 3) + "GB", font=fontdisks, fill=255)
                                    draw.text((x - 11, top + 10 + seconditem),(get_vendor(device)) + " " + (get_model(device)), font=fontdisks, fill=255)
                                    seconditem = 20  # This is to get the second USB info drawn lower down the screen to stop overlap.
                        usb = 1
                        draw.text((x - 11, top + 49), "COPY", font=fontcopy, fill=255)
                        draw.text((x + 32, top + 49), "VIEW", font=fontcopy, fill=255)
                        draw.text((x + 71, top + 49), "ERASE", font=fontcopy, fill=255)
            disp.image(image)
            disp.show()
            lcdstart = datetime.now()
            run_once = 0
            index = 0
            log_debug("Base menu drawn; index reset to 0")

basemenu()  # Run Base Menu at script start

#set up a bit of a grid for mapping menu choices.
index = 0
latindex = 0
filler = 0
va = 1
vb = 2
vc = 3
vd = 6

# Menu Selection
def menuselect():
            if index == (va):
                        copy()
            if index == (vb):
                        view()
            if index == (vc):
                        erase()
            if index == (vd):
                        basemenu()
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

def list_usb_disks():
            devices = []
            for device in get_block_devices():
                        if device.get("type") != "disk":
                                    continue
                        tran = device.get("tran")
                        rm = device.get("rm")
                        if tran == "usb" or rm == 1:
                                    devices.append(device)
            return devices

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

def get_children(device):
            return device.get("children", []) or []

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
            devices = list_usb_disks()
            if len(devices) < 2:
                        return None, None
            devices = sorted(devices, key=lambda d: d.get("name", ""))
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
            disp.fill(0)
            disp.show()
            draw.rectangle((0,0,width,height), outline=0, fill=0)
            source, target = pick_source_target()
            if not source or not target:
                        display_lines(["COPY", "Need 2 USBs"])
                        time.sleep(1)
                        basemenu()
                        return
            source_name = source.get("name")
            target_name = target.get("name")
            draw.text((x, top), f"CLONE {source_name} to {target_name}?", font=fontdisks, fill=255)
            draw.text((x + 24, top + 49), "NO", font=fontcopy, fill=255)
            draw.text((x + 52, top + 49), "YES", font=fontcopy, fill=255)
            disp.image(image)
            disp.show()
            index = 5
            try:
                        while 1:
                                    if button_R.value: # button is released
                                                filler =(0)
                                    else: # button is pressed:
                                                if index == (5):
                                                            draw.rectangle((x + 21, 48, 57, 60), outline=0, fill=1) #Select No
                                                            draw.text((x + 24, top + 49), "NO", font=fontcopy, fill=0) #No Black
                                                            index = 6
                                                            disp.image(image)
                                                            disp.show()
                                                            log_debug(f"Copy menu selection changed: index={index} (NO)")
                                                            run_once = 0
                                                if index == (6):
                                                            draw.rectangle((x + 21, 48, 57, 60), outline=0, fill=0) #Deselect No
                                                            draw.text((x + 24, top + 49), "NO", font=fontcopy, fill=1) #No White
                                                            draw.rectangle((x + 49, 48, 92, 60), outline=0, fill=1) #Select Yes
                                                            draw.text((x + 52, top + 49), "YES", font=fontcopy, fill=0) #Yes Black
                                                            index = 7
                                                            disp.image(image)
                                                            disp.show()
                                                            log_debug(f"Copy menu selection changed: index={index} (YES)")
                                                            lcdstart = datetime.now()
                                                            run_once = 0
                                                else:
                                                            # Display image.
                                                            disp.image(image)
                                                            disp.show()
                                                            time.sleep(.01)
                                    if button_L.value: # button is released
                                                filler =(0)
                                    else: # button is pressed:
                                                if index == (7):
                                                            draw.rectangle((x + 49, 48, 92, 60), outline=0, fill=0) #Deselect Yes
                                                            draw.text((x + 52, top + 49), "YES", font=fontcopy, fill=1) #Yes White
                                                            draw.rectangle((x + 21, 48, 57, 60), outline=0, fill=1) #Select No
                                                            draw.text((x + 24, top + 49), "NO", font=fontcopy, fill=0) #No Black
                                                            index = 6
                                                            disp.image(image)
                                                            disp.show()
                                                            log_debug(f"Copy menu selection changed: index={index} (NO)")
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
                                    if button_B.value: # button is released
                                                filler = (0)
                                    else: # button is pressed:
                                                disp.fill(0)
                                                disp.show()
                                                log_debug("Copy menu: Button B pressed")
                                                basemenu()
                                                disp.show()
                                    if button_A.value: # button is released
                                                filler = (0)
                                    else: # button is pressed:
                                                disp.fill(0)
                                                disp.show()
                                                log_debug("Copy menu: Button A pressed")
                                                basemenu()
                                                disp.show()
                                    if button_C.value: # button is released
                                                filler = (0)
                                    else: # button is pressed:
                                                if index == (7):
                                                            display_lines(["COPY", "Starting..."])
                                                            if clone_device(source, target):
                                                                        display_lines(["COPY", "Done"])
                                                            else:
                                                                        log_debug("Copy failed")
                                                                        display_lines(["COPY", "Failed"])
                                                            time.sleep(1)
                                                            basemenu()
                                                elif index == (6):
                                                            basemenu()
            except KeyboardInterrupt:
                        GPIO.cleanup()

def view():
            view_devices()
            time.sleep(2)
            basemenu()

def erase():
            disp.fill(0)
            disp.show()
            target_devices = list_usb_disks()
            if not target_devices:
                        display_lines(["ERASE", "No USB found"])
                        time.sleep(1)
                        basemenu()
                        return
            target = sorted(target_devices, key=lambda d: d.get("name", ""))[-1]
            target_name = target.get("name")
            draw.rectangle((0,0,width,height), outline=0, fill=0)
            draw.text((x, top), f"ERASE {target_name}?", font=fontdisks, fill=255)
            draw.text((x + 24, top + 49), "NO", font=fontcopy, fill=255)
            draw.text((x + 52, top + 49), "YES", font=fontcopy, fill=255)
            disp.image(image)
            disp.show()
            index = 5
            try:
                        while 1:
                                    if button_R.value: # button is released
                                                filler =(0)
                                    else: # button is pressed:
                                                if index == (5):
                                                            draw.rectangle((x + 21, 48, 57, 60), outline=0, fill=1) #Select No
                                                            draw.text((x + 24, top + 49), "NO", font=fontcopy, fill=0) #No Black
                                                            index = 6
                                                            disp.image(image)
                                                            disp.show()
                                                            log_debug(f"Erase menu selection changed: index={index} (NO)")
                                                if index == (6):
                                                            draw.rectangle((x + 21, 48, 57, 60), outline=0, fill=0) #Deselect No
                                                            draw.text((x + 24, top + 49), "NO", font=fontcopy, fill=1) #No White
                                                            draw.rectangle((x + 49, 48, 92, 60), outline=0, fill=1) #Select Yes
                                                            draw.text((x + 52, top + 49), "YES", font=fontcopy, fill=0) #Yes Black
                                                            index = 7
                                                            disp.image(image)
                                                            disp.show()
                                                            log_debug(f"Erase menu selection changed: index={index} (YES)")
                                    if button_L.value: # button is released
                                                filler =(0)
                                    else: # button is pressed:
                                                if index == (7):
                                                            draw.rectangle((x + 49, 48, 92, 60), outline=0, fill=0) #Deselect Yes
                                                            draw.text((x + 52, top + 49), "YES", font=fontcopy, fill=1) #Yes White
                                                            draw.rectangle((x + 21, 48, 57, 60), outline=0, fill=1) #Select No
                                                            draw.text((x + 24, top + 49), "NO", font=fontcopy, fill=0) #No Black
                                                            index = 6
                                                            disp.image(image)
                                                            disp.show()
                                                            log_debug(f"Erase menu selection changed: index={index} (NO)")
                                    if button_A.value: # button is released
                                                filler = (0)
                                    else: # button is pressed:
                                                basemenu()
                                    if button_B.value: # button is released
                                                filler = (0)
                                    else: # button is pressed:
                                                basemenu()
                                    if button_C.value: # button is released
                                                filler = (0)
                                    else: # button is pressed:
                                                if index == (7):
                                                            display_lines(["ERASE", "Starting..."])
                                                            if erase_device(target):
                                                                        display_lines(["ERASE", "Done"])
                                                            else:
                                                                        log_debug("Erase failed")
                                                                        display_lines(["ERASE", "Failed"])
                                                            time.sleep(1)
                                                            basemenu()
                                                elif index == (6):
                                                            basemenu()
            except KeyboardInterrupt:
                        GPIO.cleanup()

def sleepdisplay():  # put the display to sleep to reduce power
            global run_once
            disp.fill(0)
            disp.show()
            draw.rectangle((0, 0, width, height), outline=0, fill=0)
            disp.image(image)
            disp.show()
            run_once = 1

# Button Commands
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
                                    disp.image(image)
                                    disp.show()
                                    log_debug("Button UP pressed")
                                    lcdstart = datetime.now()
                                    run_once = 0
                        if button_L.value: # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    if index == (3):
                                                draw.rectangle((x + 69, 48, 127, 60), outline=0, fill=0)  # Deselect Erase
                                                draw.text((x + 71, top + 49), "ERASE", font=fontcopy, fill=1)  # Erase White
                                                draw.rectangle((x + 66, 48, 40, 60), outline=0, fill=1) #Select View
                                                draw.text((x + 32, top + 49), "VIEW", font=fontcopy, fill=0) #View Black
                                                index = 2
                                                disp.image(image)
                                                disp.show()
                                                log_debug("Menu selection changed: index=2 (VIEW)")
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    elif index == (2):
                                                draw.rectangle((x + 66, 48, 40, 60), outline=0, fill=0)  # Deselect View
                                                draw.text((x + 32, top + 49), "VIEW", font=fontcopy, fill=1)  # View White
                                                draw.rectangle((x - 12, 48, 39, 60), outline=0, fill=1)  # Select Copy
                                                draw.text((x - 11, top + 49), "COPY", font=fontcopy, fill=0)  # Copy Black
                                                index = 1
                                                disp.image(image)
                                                disp.show()
                                                log_debug("Menu selection changed: index=1 (COPY)")
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    elif index == (1):
                                                draw.rectangle((x + 66, 48, 40, 60), outline=0, fill=0)  # Deselect View
                                                draw.text((x + 32, top + 49), "VIEW", font=fontcopy, fill=1)  # View White
                                                draw.rectangle((x - 12, 48, 39, 60), outline=0, fill=1)  # Select Copy
                                                draw.text((x - 11, top + 49), "COPY", font=fontcopy, fill=0)  # Copy Black
                                                index = 1
                                                disp.image(image)
                                                disp.show()
                                                log_debug("Menu selection changed: index=1 (COPY)")
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
                                    if index == (0):
                                                draw.rectangle((x - 12, 48, 39, 60), outline=0, fill=1) #Select Copy
                                                draw.text((x - 11, top + 49), "COPY", font=fontcopy, fill=0) #Copy Black
                                                index = 1
                                                disp.image(image)
                                                disp.show()
                                                log_debug("Menu selection changed: index=1 (COPY)")
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    elif index == (1):
                                                draw.rectangle((x - 12, 48, 39, 60), outline=0, fill=0) #Deselect Copy
                                                draw.text((x - 11, top + 49), "COPY", font=fontcopy, fill=1) #Copy White
                                                draw.rectangle((x + 66, 48, 40, 60), outline=0, fill=1) #Select View
                                                draw.text((x + 32, top + 49), "VIEW", font=fontcopy, fill=0) #View Black
                                                index = 2
                                                disp.image(image)
                                                disp.show()
                                                log_debug("Menu selection changed: index=2 (VIEW)")
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    elif index == (2):
                                                draw.rectangle((x + 66, 48, 40, 60), outline=0, fill=0) #Deselect View
                                                draw.text((x + 32, top + 49), "VIEW", font=fontcopy, fill=1) #View White
                                                draw.rectangle((x + 69, 48, 127, 60), outline=0, fill=1) #Select Erase
                                                draw.text((x + 71, top + 49), "ERASE", font=fontcopy, fill=0) #Erase Black
                                                index = 3
                                                disp.image(image)
                                                disp.show()
                                                log_debug("Menu selection changed: index=3 (ERASE)")
                                                lcdstart = datetime.now()
                                                run_once = 0
                                    elif index == (3):
                                                draw.rectangle((x + 66, 48, 40, 60), outline=0, fill=0) #Deselect View
                                                draw.text((x + 32, top + 49), "VIEW", font=fontcopy, fill=1) #View White
                                                draw.rectangle((x + 69, 48, 127, 60), outline=0, fill=1) #Select Erase
                                                draw.text((x + 71, top + 49), "ERASE", font=fontcopy, fill=0) #Erase Black
                                                index = 3
                                                disp.image(image)
                                                disp.show()
                                                log_debug("Menu selection changed: index=3 (END OF MENU)")
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
            GPIO.cleanup()

except Exception as e:
    # This will print the type of exception and error message to the terminal
    print(f"An error occurred: {type(e).__name__}")
    print(str(e))

    # This will display a simple error message on the OLED screen
    disp.fill(0)
    disp.show()
    draw.rectangle((0,0,width,height), outline=0, fill=0)
    draw.text((x, top + 30), "ERROR", font=fontinsert, fill=255)
    disp.image(image)
    disp.show()
