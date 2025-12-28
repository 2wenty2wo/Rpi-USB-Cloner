# Rpi-USB-Cloner

**STATUS: NOT WORKING**

## Installation & Usage

### 1) Install dependencies and prepare the Pi
1. Flash Raspberry Pi OS (Lite is fine) to your microSD and boot the Pi Zero.
2. Update packages:
   ```sh
   sudo apt update
   sudo apt upgrade -y
   ```
3. Enable I2C (required for the OLED Bonnet):
   ```sh
   sudo raspi-config
   ```
   *Interface Options → I2C → Enable, then reboot.*
4. Install Python and build tools:
   ```sh
   sudo apt install -y python3 python3-pip python3-dev python3-venv git
   ```
5. Create and activate a virtual environment (required on Bookworm due to PEP 668):
   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```
6. Install Python libraries used by the script:
   ```sh
   python3 -m pip install --upgrade pip
   python3 -m pip install adafruit-blinka adafruit-circuitpython-ssd1306 pillow mount.py
   ```

### 2) Hardware setup
1. Attach the Adafruit OLED Bonnet to the Pi Zero GPIO header.
2. Attach the Zero4U USB Hub to the Pi Zero (per the Zero4U instructions).
3. Connect power and boot the Pi.

### 3) Start the cloner script
From the repo directory (with the venv active):
```sh
python3 rpi-usb-cloner.py
```

### 4) Stop the running process
If running in the foreground, press **Ctrl+C** in the terminal where it was started.

### 5) Restart the process
1. Stop it (Ctrl+C).
2. Start it again (with the venv active):
   ```sh
   python3 rpi-usb-cloner.py
   ```

### 6) Update the software
From the repo directory (with the venv active):
```sh
git pull
python3 -m pip install --upgrade adafruit-blinka adafruit-circuitpython-ssd1306 pillow mount.py
```

  USB Cloner/Duplicator using a Raspberry Pi Zero, [Adafruit OLED Bonnet](https://www.adafruit.com/product/3531) and [Zero4U USB Hub](https://www.adafruit.com/product/3298).
  
  Modified [Adafruit_OLED_Bonnet_menu](https://github.com/W5DMH/Adafruit_OLED_Bonnet_menu) for a menu and used [mount.py](https://github.com/Vallentin/mount.py) to interact with USB drives and inspired by [usb-copier](https://github.com/lukehutch/usb-copier).
  
  ![Picture of the menu](https://raw.githubusercontent.com/2wenty2wo/Rpi-USB-Cloner/main/menu.jpg)
