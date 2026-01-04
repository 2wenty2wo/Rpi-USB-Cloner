<p align="center">
  <img src="rpi_usb_cloner/ui/assets/logo.webp" alt="Rpi USB Cloner" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/github/license/2wenty2wo/Rpi-USB-Cloner" />
  <img src="https://img.shields.io/github/last-commit/2wenty2wo/Rpi-USB-Cloner" />
  <img src="https://img.shields.io/badge/status-WIP-yellow" />
</p>


USB Cloner/Duplicator using a Raspberry Pi Zero, [Adafruit 128x64 1.3" OLED Bonnet](https://www.adafruit.com/product/3531) and [Zero4U USB Hub](https://www.adafruit.com/product/3298).

Inspired by [lukehutch/usb-copier](https://github.com/lukehutch/usb-copier).

![Picture of the menu](rpi_usb_cloner/ui/assets/menu.jpg)

## Prerequisites

**Hardware**
- Raspberry Pi Zero
- Adafruit 128x64 1.3" OLED Bonnet
- Zero4U USB Hub

**OS**
- Raspberry Pi OS

## Quickstart

Minimal clone/install/run (see full steps below for I2C setup, options, and services):
```sh
git clone https://github.com/2wenty2wo/Rpi-USB-Cloner
cd Rpi-USB-Cloner
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip luma.oled pillow
sudo -E python3 rpi-usb-cloner.py
```

## Installation & Usage

### Installation

#### 1) Clone the repository
```sh
git clone https://github.com/2wenty2wo/Rpi-USB-Cloner
cd Rpi-USB-Cloner
```

#### 2) Install dependencies and prepare the Pi
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

#### 3) Hardware setup
1. Attach the Adafruit OLED Bonnet (OLED + buttons) to the Pi Zero GPIO header.
2. Attach the Zero4U USB Hub to the Pi Zero (per the Zero4U instructions).
3. Connect power and boot the Pi.

### Usage

#### 4) Start the cloner script
From the repo directory:
```sh
sudo -E python3 rpi-usb-cloner.py
```
To enable verbose debug logging:
```sh
sudo -E python3 rpi-usb-cloner.py --debug
```
The erase workflow requires root permissions; if you start without `sudo`, the OLED will prompt you to run as root.

#### 5) Stop the running process
If running in the foreground, press **Ctrl+C** in the terminal where it was started.

#### 6) Restart the process
1. Stop it (Ctrl+C).
2. Start it again:
   ```sh
   sudo -E python3 rpi-usb-cloner.py
   ```

#### 7) Auto-start on boot (systemd)
Create a systemd unit so the cloner starts automatically at boot. Update paths as needed for your install location.

1. Create `/etc/systemd/system/rpi-usb-cloner.service`:
   ```ini
   [Unit]
   Description=Rpi USB Cloner
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/home/pi/Rpi-USB-Cloner
   ExecStart=/home/pi/Rpi-USB-Cloner/.venv/bin/python /home/pi/Rpi-USB-Cloner/rpi-usb-cloner.py
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```
   Ensure the `User=` matches the repository owner, or make sure the repository is owned by the service user (to avoid Git dubious-ownership warnings).
   If you used Option B (system Python), change `ExecStart` to `/usr/bin/python3 /home/pi/Rpi-USB-Cloner/rpi-usb-cloner.py`.
2. Reload systemd and enable the service to start on boot:
   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable rpi-usb-cloner.service
   sudo systemctl start rpi-usb-cloner.service
   ```
3. SSH control commands:
   ```sh
   sudo systemctl stop rpi-usb-cloner.service
   sudo systemctl start rpi-usb-cloner.service
   sudo systemctl restart rpi-usb-cloner.service
   sudo systemctl status rpi-usb-cloner.service
   sudo journalctl -u rpi-usb-cloner.service -f
   ```

#### 8) Update the software
You can also trigger updates from the OLED UI via Settings → Update.
From the repo directory:
```sh
git pull
python3 -m pip install --upgrade luma.oled pillow
```
If you used Option B above, append `--break-system-packages` to the pip command.
`mount.py` ships with this repository, so no separate install is needed.

## Assets & Customization

### Screensaver GIFs
Place custom GIFs in `rpi_usb_cloner/ui/assets/gifs/` (the single folder the screensaver reads) and the screensaver will automatically pick them up. If the folder is empty, the screensaver falls back to a static placeholder screen.

### Font assets
The OLED demo uses the Font Awesome Free `fontawesome-webfont.ttf` font. The font is licensed under the SIL OFL 1.1; see `rpi_usb_cloner/ui/assets/fonts/LICENSE-FONT-AWESOME.txt` for details.
