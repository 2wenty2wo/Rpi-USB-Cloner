<p align="center">
  <img src="rpi_usb_cloner/ui/assets/logo.webp" alt="Rpi USB Cloner" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/github/license/2wenty2wo/Rpi-USB-Cloner" />
  <img src="https://img.shields.io/github/last-commit/2wenty2wo/Rpi-USB-Cloner" />
  <img src="https://img.shields.io/badge/status-WIP-red" />
  <br/>
  <img src="https://github.com/2wenty2wo/Rpi-USB-Cloner/actions/workflows/tests.yml/badge.svg" alt="Tests" />
  <img src="https://img.shields.io/badge/coverage-22.50%25-yellow" alt="Coverage" />
  <img src="https://img.shields.io/badge/tests-608%20passing-brightgreen" alt="Tests Passing" />
</p>
Don't expect this to work yet...

USB Cloner/Duplicator using a Raspberry Pi Zero, [Adafruit 128x64 1.3" OLED Bonnet](https://www.adafruit.com/product/3531) and [Zero4U USB Hub](https://www.adafruit.com/product/3298).

Inspired by [lukehutch/usb-copier](https://github.com/lukehutch/usb-copier).


## ✨ Features

### Core Functionality
- **USB-to-USB Cloning**: Direct drive-to-drive copying with multiple clone modes (smart copy, dd, etc.)
- **Drive Erasing**: Secure drive wiping with confirmation prompts
- **Clonezilla Image Support**: Backup and restore drives using Clonezilla-format disk images
  - Automatic detection of partition tables (sfdisk, sgdisk, parted)
  - MBR and GPT support
  - Multiple partition restore modes (k0, k, k1, k2)
- **Drive Information**: View detailed device info including vendor, model, size, and partitions

### Hardware Interface
- **OLED Menu Navigation**: Intuitive menu system displayed on 128x64 OLED screen
- **Button Controls**: Navigate using 6 hardware buttons (Up/Down/Left/Right + A/B/C)
- **USB Hotplug Detection**: Automatic device detection when drives are inserted or removed
- **Screensaver**: Customizable GIF screensaver with automatic idle timeout

### System Management
- **WiFi Configuration**: Configure wireless network settings directly from the OLED interface
- **Persistent Settings**: Configuration saved to `~/.config/rpi-usb-cloner/settings.json`
- **Auto-start Support**: Systemd service configuration for automatic startup on boot
- **Power Management**: Restart/shutdown system or service from the menu
- **Logging & Diagnostics**: Built-in log viewer and debug mode for troubleshooting

### User Experience
- **Multi-drive Support**: Automatically detects and lists all connected USB drives
- **Confirmation Prompts**: Safety checks before destructive operations
- **Progress Tracking**: Real-time status updates during clone/restore operations
- **Smart Drive Selection**: Remembers active drive selection across menu navigation

## ⚠️ Safety Warnings

**IMPORTANT: Read before use!**

This tool performs destructive disk operations that can result in **permanent data loss**. Please observe these safety precautions:

### Before You Begin
- ⚠️ **Backup all important data** before performing any clone, erase, or restore operations
- ⚠️ **Double-check source and target drives** - selecting the wrong drive will result in irreversible data loss
- ⚠️ **Test with non-critical drives first** to familiarize yourself with the interface and workflows
- ⚠️ **Verify drive identification** using the Drive Info feature before proceeding with operations

### Destructive Operations
The following operations **cannot be undone**:
- **Drive Erasing**: Permanently wipes all data from the selected drive
- **Clone/Copy**: Overwrites the entire target drive, destroying all existing data
- **Image Restore**: Replaces target drive contents with the disk image

### Best Practices
- ✅ Label your drives clearly to avoid confusion
- ✅ Remove unnecessary USB drives before operations to reduce risk of selecting the wrong drive
- ✅ Use the confirmation prompts carefully - read them thoroughly before confirming
- ✅ Keep the device powered during operations - unexpected shutdowns may corrupt data
- ✅ Verify successful completion before disconnecting drives

### Limitations
- The Pi Zero uses USB 2.0, which limits transfer speeds
- Large drives may take considerable time to clone
- Root permissions are required for all disk operations

## 📑 Table of Contents

- [Features](#-features)
- [Safety Warnings](#️-safety-warnings)
- [Prerequisites](#-prerequisites)
- [Quickstart](#-quickstart)
- [Installation & Usage](#-installation--usage)
  - [Installation](#-installation)
    - [1) Clone the repository](#1-clone-the-repository)
    - [2) Install dependencies and prepare the Pi](#2-install-dependencies-and-prepare-the-pi)
    - [3) Hardware setup](#3-hardware-setup)
  - [Usage](#️-usage)
    - [4) Start the cloner script](#4-start-the-cloner-script)
    - [5) Stop the running process](#5-stop-the-running-process)
    - [6) Restart the process](#6-restart-the-process)
    - [7) Auto-start on boot (systemd)](#7-auto-start-on-boot-systemd)
    - [8) Update the software](#8-update-the-software)
- [Assets & Customization](#-assets--customization)
  - [Screensaver GIFs](#️-screensaver-gifs)
  - [Font assets](#-font-assets)

## ✅ Prerequisites

**Hardware**
- Raspberry Pi Zero
- Adafruit 128x64 1.3" OLED Bonnet
- Zero4U USB Hub

**OS**
- Raspberry Pi OS

## 🚀 Quickstart

Quick setup for experienced users (see full installation guide below for I2C setup, hardware details, and systemd configuration):

```sh
# Clone the repository
git clone https://github.com/2wenty2wo/Rpi-USB-Cloner
cd Rpi-USB-Cloner

# Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the cloner (requires root for disk operations)
sudo -E python3 rpi-usb-cloner.py
```

> **Prerequisites:** I2C must be enabled and hardware must be properly connected. See the full Installation section below for details.

## 🧰 Installation & Usage

### 🧱 Installation

#### 1) Clone the repository
Download the source code to your Raspberry Pi:
```sh
# Clone the repository
git clone https://github.com/2wenty2wo/Rpi-USB-Cloner

# Navigate to the project directory
cd Rpi-USB-Cloner
```

#### 2) Install dependencies and prepare the Pi
1. Flash Raspberry Pi OS (Lite is fine) to your microSD and boot the Pi Zero.

2. Update system packages to the latest versions:
   ```sh
   sudo apt update
   sudo apt upgrade -y
   ```

3. Enable I2C (required for the Adafruit OLED Bonnet):

   **Option A:** Use raspi-config interactive tool:
   ```sh
   sudo raspi-config
   ```
   Navigate to: *Interface Options → I2C → Enable*, then reboot.

   **Option B:** Manually edit `/boot/config.txt`:
   ```ini
   # Enable I2C for OLED display
   dtparam=i2c_arm=on
   ```

   After enabling I2C, confirm the display address is either **0x3C** or **0x3D**.
   The OLED driver class depends on the panel type, so verify whether your panel is **SSD1306** or **SH1106**.

4. Install Python and required system libraries:
   ```sh
   sudo apt install -y python3 python3-pip python3-dev python3-venv git \
     libopenjp2-7 libfreetype6 libjpeg62-turbo libpng16-16t64 zlib1g
   ```

5. Install Python dependencies (Bookworm enforces PEP 668):

   **Option A (recommended):** Use a virtual environment for isolation:
   ```sh
   # Create virtual environment
   python3 -m venv .venv

   # Activate virtual environment
   source .venv/bin/activate

   # Install Python packages
   pip install -r requirements.txt
   ```

   **Option B (single-use device):** Install to system Python:
   ```sh
   # Install with PEP 668 override (use only for dedicated devices)
   sudo pip install --break-system-packages -r requirements.txt
   ```

#### 3) Hardware setup
1. Attach the Adafruit OLED Bonnet (OLED + buttons) to the Pi Zero GPIO header.
2. Attach the Zero4U USB Hub to the Pi Zero (per the Zero4U instructions).
3. Connect power and boot the Pi.

### ▶️ Usage

#### 4) Start the cloner script
Run the cloner from the repository directory:

**Basic usage:**
```sh
# Start the cloner (root required for disk operations)
sudo -E python3 rpi-usb-cloner.py
```

**Debug mode:**
```sh
# Enable verbose debug logging for troubleshooting
sudo -E python3 rpi-usb-cloner.py --debug
```

> **Note:** The `-E` flag preserves your environment variables. Root permissions are required for disk operations; if you start without `sudo`, the OLED will display a prompt to run as root.


#### 5) Stop the running process
If running in the foreground, press **Ctrl+C** in the terminal where it was started.

#### 6) Restart the process
To restart the cloner:
1. Stop the running process by pressing **Ctrl+C** in the terminal
2. Start it again:
   ```sh
   # Restart the cloner
   sudo -E python3 rpi-usb-cloner.py
   ```

#### 7) Auto-start on boot (systemd)
Configure the cloner to start automatically at boot using systemd.

1. Create the systemd service file `/etc/systemd/system/rpi-usb-cloner.service`:
   ```ini
   [Unit]
   Description=Rpi USB Cloner
   After=network.target

   [Service]
   Type=simple
   User=root
   # Update paths to match your installation directory
   WorkingDirectory=/home/pi/Rpi-USB-Cloner
   # For virtual environment (Option A), use the venv Python:
   ExecStart=/home/pi/Rpi-USB-Cloner/.venv/bin/python /home/pi/Rpi-USB-Cloner/rpi-usb-cloner.py
   # For system Python (Option B), use: /usr/bin/python3 /home/pi/Rpi-USB-Cloner/rpi-usb-cloner.py
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

   > **Important:** Ensure the `User=` field matches the repository owner to avoid Git dubious-ownership warnings. Update all paths to match your actual installation location.

2. Enable and start the service:
   ```sh
   # Reload systemd to recognize the new service
   sudo systemctl daemon-reload

   # Enable service to start on boot
   sudo systemctl enable rpi-usb-cloner.service

   # Start service immediately
   sudo systemctl start rpi-usb-cloner.service
   ```

3. Manage the service via SSH:
   ```sh
   # Stop the service
   sudo systemctl stop rpi-usb-cloner.service

   # Start the service
   sudo systemctl start rpi-usb-cloner.service

   # Restart the service
   sudo systemctl restart rpi-usb-cloner.service

   # Check service status
   sudo systemctl status rpi-usb-cloner.service

   # View live logs
   sudo journalctl -u rpi-usb-cloner.service -f
   ```

#### 8) Update the software
Keep your cloner up to date with the latest features and bug fixes.

**Method 1: Update via OLED UI**
- Navigate to: *Settings → Update*

**Method 2: Update via command line**

If using **Option A (virtual environment)**:
```sh
# Navigate to repository directory
cd /path/to/Rpi-USB-Cloner

# Pull latest changes
git pull

# Activate virtual environment
source .venv/bin/activate

# Update Python dependencies
pip install -r requirements.txt
```

If using **Option B (system Python)**:
```sh
# Navigate to repository directory
cd /path/to/Rpi-USB-Cloner

# Pull latest changes
git pull

# Update Python dependencies
sudo pip install --break-system-packages -r requirements.txt
```


## 🎨 Assets & Customization

### 🖼️ Screensaver GIFs
Place custom GIFs in `rpi_usb_cloner/ui/assets/gifs/` and the screensaver will automatically pick them up.

### 🔤 Font assets
This project uses Lucide icons; see <https://lucide.dev/license> for license details.
