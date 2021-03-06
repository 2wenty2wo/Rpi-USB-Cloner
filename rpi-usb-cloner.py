import board
import busio
import time
import datetime
import subprocess
import RPi.GPIO as GPIO
import os
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
fontmain = ImageFont.load_default()

# Get drawing object to draw on image.
draw = ImageDraw.Draw(image)
index = 0

# Draw a black filled box to clear the image.
draw.rectangle((0, 0, width, height), outline=0, fill=0)

def basemenu():
            disp.fill(0)
            disp.show()
            draw.text((x - 11, top + 49), "COPY", font=fontcopy, fill=255)
            draw.text((x + 32, top + 49), "VIEW", font=fontcopy, fill=255)
            draw.text((x + 71, top + 49), "ERASE", font=fontcopy, fill=255)
            disp.image(image)
            disp.show()
            index = 0

#set up a bit of a grid for mapping menu choices, each "V" variable is a   horizontal line
#each latindex is
index = 0
latindex = 0
filler = 0
va = 0
vb = 8
vc = 16
vd = 24
ve = 32
vf = 40
vg = 48

def menuselect():
    if index == (va):
        status()
    if index == (vb):
        beaconsettings()
    if index == (vc):
        beaconstatus()
    if index == (vd):
        closedisplay()
    if index == (ve):
        reboot()
    if index == (vf):
        shutdown()

    else:
        # Display image.
        disp.image(image)
        disp.show()
        time.sleep(.01)

global run_once
run_once = 0

#setup the  go to sleep timer
lcdstart = datetime.now()

def sleepdisplay():  # put the display to sleep to reduce power
    global run_once
    disp.fill(0)
    disp.show()
    draw.rectangle((0, 0, width, height), outline=0, fill=0)
    disp.image(image)
    disp.show()
    run_once = 1



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
            basemenu()
            # draw.text((x-8, index),       "*", fill=0)
            # index = (index-8)
            # draw.text((x-8, index),       "*", fill=1)
            disp.image(image)
            disp.show()
            print("button up")
            lcdstart = datetime.now()
            run_once = 0
        if button_L.value: # button is released
            latindex = (latindex)
        else: # button is pressed:
            #basemenu()
            if index == (3):
                draw.rectangle((x + 69, 48, 127, 60), outline=0, fill=0)  # Deselect Erase
                draw.text((x + 71, top + 49), "ERASE", font=fontcopy, fill=1)  # Erase White
                draw.rectangle((x + 66, 48, 40, 60), outline=0, fill=1) #Select View
                draw.text((x + 32, top + 49), "VIEW", font=fontcopy, fill=0) #View Black
                index = 2
                disp.image(image)
                disp.show()
                print("button right")
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
                print("button right")
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
                print("button right")
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
            #basemenu()
            if index == (0):
                draw.rectangle((x - 12, 48, 39, 60), outline=0, fill=1) #Select Copy
                draw.text((x - 11, top + 49), "COPY", font=fontcopy, fill=0) #Copy Black
                index = 1
                disp.image(image)
                disp.show()
                print("button right")
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
                print("button right")
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
                print("button right")
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
                print("button right")
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
            basemenu()
            #draw.rectangle((0, 0, width, height), outline=0, fill=0)
            #draw.text((x-8, top),       "*", fill=0)
            #draw.text((x-8, index),       "*", fill=0)
            #index = (index +8)
            #draw.text((x-8, index),       "*", fill=1)
            #disp.image(image)
            disp.show()
            print("button down")
            lcdstart = datetime.now()
            run_once = 0
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
        if not button_A.value and not button_B.value and not button_C.value:
            catImage = Image.open('happycat_oled_64.ppm').convert('1')
            disp.image(catImage)
        else:
            filler=(0)

except KeyboardInterrupt:
    GPIO.cleanup()
