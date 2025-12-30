![Rpi USB Cloner](rpi_usb_cloner/ui/assets/logo.webp)

![Python](https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white) ![Last commit](https://img.shields.io/github/last-commit/2wenty2wo/Rpi-USB-Cloner)

**STATUS: NOT WORKING**

## Installation & Usage

### 1) Clone the repository
```sh
git clone https://github.com/2wenty2wo/Rpi-USB-Cloner
cd Rpi-USB-Cloner
```

### 2) Install dependencies and prepare the Pi
1. Flash Raspberry Pi OS (Lite is fine) to your microSD and boot the Pi Zero.
2. Update packages:
   ```sh
   sudo apt update
   sudo apt upgrade -y
   ```
3. Enable I2C (required for the Adafruit OLED Bonnet):
   ```sh
   sudo raspi-config
   ```
   *Interface Options → I2C → Enable, then reboot.*
   You can also enable I2C via `/boot/config.txt` by adding:
   ```ini
   dtparam=i2c_arm=on
   ```
   After enabling I2C, confirm the display address is either **0x3C** or **0x3D**.
   The OLED driver class depends on the panel type, so verify whether your panel is **SSD1306** or **SH1106**.
4. Install Python and build tools:
   ```sh
   sudo apt install -y python3 python3-pip python3-dev python3-venv git libopenjp2-7 libfreetype6 libjpeg62-turbo libpng16-16t64 zlib1g
   ```
5. Install Python libraries used by the script (Bookworm enforces PEP 668):
   - **Option A (recommended for isolation):** use a virtual environment.
     ```sh
     python3 -m venv .venv
     source .venv/bin/activate
     python3 -m pip install --upgrade pip
     python3 -m pip install luma.oled pillow
     ```
   - **Option B (single-use device):** install into system Python with the PEP 668 override.
     ```sh
     sudo python3 -m pip install --break-system-packages luma.oled
     sudo python3 -m pip install --break-system-packages pillow
     python3 -m pip install --upgrade pip --break-system-packages
     ```

### 3) Hardware setup
1. Attach the Adafruit OLED Bonnet (OLED + buttons) to the Pi Zero GPIO header.
2. Attach the Zero4U USB Hub to the Pi Zero (per the Zero4U instructions).
3. Connect power and boot the Pi.

### 3a) GPIO button inputs
Button inputs use `RPi.GPIO` **BCM pin numbering** with internal pull-ups enabled. Wire your buttons to pull the selected BCM pins to **GND**.

### 4) Start the cloner script
From the repo directory:
```sh
sudo -E python3 rpi-usb-cloner.py
```
To enable verbose debug logging:
```sh
sudo -E python3 rpi-usb-cloner.py --debug
```
The erase workflow requires root permissions; if you start without `sudo`, the OLED will prompt you to run as root.

### 5) Stop the running process
If running in the foreground, press **Ctrl+C** in the terminal where it was started.

### 6) Restart the process
1. Stop it (Ctrl+C).
2. Start it again:
   ```sh
   sudo -E python3 rpi-usb-cloner.py
   ```

### 7) Update the software
From the repo directory:
```sh
git pull
python3 -m pip install --upgrade luma.oled pillow
```
If you used Option B above, append `--break-system-packages` to the pip command.
`mount.py` ships with this repository, so no separate install is needed.

## UI assets
The UI expects the following files in `rpi_usb_cloner/ui/assets/`:

- `splash.png`
- `menu.jpg`
- `logo.webp`
- `usb.png`
- `rainyhearts.ttf`
- `slkscr.ttf`

  USB Cloner/Duplicator using a Raspberry Pi Zero, [Adafruit OLED Bonnet](https://www.adafruit.com/product/3531) and [Zero4U USB Hub](https://www.adafruit.com/product/3298).
  
  Modified [Adafruit_OLED_Bonnet_menu](https://github.com/W5DMH/Adafruit_OLED_Bonnet_menu) for a menu and used [mount.py](https://github.com/Vallentin/mount.py) to interact with USB drives and inspired by [usb-copier](https://github.com/lukehutch/usb-copier).
  
  ![Picture of the menu](rpi_usb_cloner/ui/assets/menu.jpg)
