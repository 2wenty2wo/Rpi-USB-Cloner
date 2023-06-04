import board
import busio
import time
import datetime
import subprocess
import RPi.GPIO as GPIO
import os
from mount import *
import sys

from digitalio import DigitalInOut, Direction, Pull
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
from datetime import datetime, timedelta
from time import sleep, strftime, localtime

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

def basemenu():
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
            index = 0

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
def copy():
            disp.fill(0)
            disp.show()
            draw.rectangle((0,0,width,height), outline=0, fill=0)
            draw.text((x, top), "CLONE SDA to SDB?", font=fontdisks, fill=255)
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
                                                            print("NO" + str(index))
                                                            lcdstart = datetime.now()
                                                            run_once = 0
                                                if index == (6):
                                                            draw.rectangle((x + 21, 48, 57, 60), outline=0, fill=0) #Deselect No
                                                            draw.text((x + 24, top + 49), "NO", font=fontcopy, fill=1) #No White
                                                            draw.rectangle((x + 49, 48, 92, 60), outline=0, fill=1) #Select Yes
                                                            draw.text((x + 52, top + 49), "YES", font=fontcopy, fill=0) #Yes Black
                                                            index = 7
                                                            disp.image(image)
                                                            disp.show()
                                                            print("YES" + str(index))
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
                                                            print("NO" + str(index))
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
                                                print("Button B")
                                                basemenu()
                                                disp.show()
                                    if button_A.value: # button is released
                                                filler = (0)
                                    else: # button is pressed:
                                                disp.fill(0)
                                                disp.show()
                                                print("Button A")
                                                basemenu()
                                                disp.show()
            except KeyboardInterrupt:
                        GPIO.cleanup()

def view():
            draw.rectangle((0,0,width,height), outline=0, fill=0)
            disp.fill(0)
            disp.show()
            draw.text((x, top + 30), "VIEW", font=fontinsert, fill=255)

def erase():
            draw.rectangle((0,0,width,height), outline=0, fill=0)
            disp.fill(0)
            disp.show()
            draw.text((x, top + 30), "ERASE", font=fontinsert, fill=255)

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
                                    print("button up")
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
                                                print("VIEW")
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
                                                print("COPY")
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
                                                print("COPY")
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
                                                print("COPY")
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
                                                print("VIEW")
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
                                                print("ERASE")
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
                                                print("END OF MENU")
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
                                    print("button down")
                        if button_C.value: # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    filler = (0)
                                    print("button c")
                        if button_A.value: # button is released
                                    filler = (0)
                        else: # button is pressed:
                                    disp.fill(0)
                                    disp.show()
                                    print("button a")
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
