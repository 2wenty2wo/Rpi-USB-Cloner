<p align="center">
  <img src="rpi_usb_cloner/ui/assets/demo1.png" alt="Rpi USB Cloner" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/github/license/2wenty2wo/Rpi-USB-Cloner" />
  <img src="https://img.shields.io/github/last-commit/2wenty2wo/Rpi-USB-Cloner" />
  <img src="https://img.shields.io/badge/status-WIP-red" />
</p>
Don't expect this to work yet...

USB Cloner/Duplicator using a Raspberry Pi Zero, [Adafruit 128x64 1.3" OLED Bonnet](https://www.adafruit.com/product/3531) and [Zero4U USB Hub](https://www.adafruit.com/product/3298).

Inspired by [lukehutch/usb-copier](https://github.com/lukehutch/usb-copier).

## ✅ Prerequisites

**Hardware**
- Raspberry Pi Zero / Zero 2
- Adafruit 128x64 1.3" OLED Bonnet
- Zero4U USB Hub

**OS**
- Raspberry Pi OS (Tested with Raspberry Pi OS Lite Trixie)

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

   **Optional: Set a faster I2C baud rate (1 MHz)**
   1. Open the config file (path depends on your Raspberry Pi OS version):
      ```sh
      # Newer Raspberry Pi OS releases
      sudo nano /boot/firmware/config.txt
      ```
      On some versions, the file lives at `/boot/config.txt` instead. Use whichever path exists.
   2. Add or update the following line under other `dtparam` entries:
      ```ini
      dtparam=i2c_baudrate=1000000
      ```
   3. Save and exit (`Ctrl+O`, `Enter`, then `Ctrl+X`).
   4. Reboot to apply:
      ```sh
      sudo reboot
      ```

4. Install Python and required system libraries:
   ```sh
   sudo apt install -y python3 python3-pip python3-dev python3-venv git \
     libopenjp2-7 libfreetype6 libjpeg62-turbo libpng16-16t64 zlib1g partclone
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

**Web UI debug logging:**
Append `?debug=1` to the web UI URL (e.g., `http://<pi-ip>:8000/?debug=1`) to enable browser console logs and the on-page debug log panel. You can also persist the toggle in the browser by running `localStorage.setItem("rpiUsbClonerDebug", "1")` and disable it with `localStorage.removeItem("rpiUsbClonerDebug")`.


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

**Troubleshooting update checks**
If you run update checks as sudo/root, Git may report "dubious ownership," and the UI can show `status: unable to ...`. Fix this by marking the repo as a safe directory (adjust the path to your install directory):
```sh
sudo git config --global --add safe.directory /home/pi/Rpi-USB-Cloner
```

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


## 📱 Bluetooth Tethering

Access the web UI from your iPhone or other Bluetooth-enabled device without WiFi.

### Setup Bluetooth Tethering

#### 1) Install Bluetooth dependencies

Run the installation script to install required system packages:

```sh
# Navigate to repository directory
cd Rpi-USB-Cloner

# Run installation script (requires root)
sudo ./scripts/install-bluetooth.sh
```

This installs:
- `bluez` - Bluetooth stack
- `bluez-tools` - Bluetooth utilities (bt-agent, bt-network)
- `bridge-utils` - Network bridging support
- `dnsmasq` - DHCP server for assigning IPs to connected devices

#### 2) Enable Bluetooth tethering

**Option A: Via OLED menu (recommended)**
1. Navigate to: *Main Menu → Tools → Bluetooth*
2. Select *Enable/Disable* to start Bluetooth tethering
3. The Pi will create a network bridge at `192.168.55.1`

**Option B: Via settings file**
Edit `~/.config/rpi-usb-cloner/settings.json`:
```json
{
  "bluetooth_enabled": true,
  "bluetooth_auto_start": true
}
```

#### 3) Pair your iPhone

1. On the OLED menu, select *Bluetooth → Make Discoverable*
2. On your iPhone:
   - Open *Settings → Bluetooth*
   - Look for *RPi USB Cloner* in available devices
   - Tap to pair
3. Once paired, your iPhone will automatically connect to the Pi's Bluetooth network

#### 4) Access the web UI

Open Safari on your iPhone and navigate to:
```
http://192.168.55.1:8000
```

You can now:
- View the live OLED display stream
- Monitor device operations
- Check system health (CPU, memory, disk, temperature)
- View Bluetooth connection status

### Bluetooth Menu Options

- **Enable/Disable** - Toggle Bluetooth tethering on/off
- **Status** - View Bluetooth adapter status and connection info
- **Make Discoverable** - Allow pairing for 5 minutes (default)
- **Connection Info** - Display web UI URL and connection instructions
- **Paired Devices** - List paired devices and their connection status

### Bluetooth Settings

Configure Bluetooth behavior in the menu:

- **Auto-start** - Enable Bluetooth tethering on boot
- **Device Name** - Set the Bluetooth device name (default: "RPi USB Cloner")

### Troubleshooting Bluetooth

**Bluetooth adapter not detected:**
```sh
# Check if Bluetooth is available
hciconfig -a

# Restart Bluetooth service
sudo systemctl restart bluetooth.service
```

**Connection issues:**
```sh
# View Bluetooth status
bluetoothctl show

# Check if PAN network is active
ip addr show pan0

# View DHCP leases
sudo cat /var/lib/misc/dnsmasq.leases
```

**Remove paired device:**
1. Navigate to: *Bluetooth → Paired Devices*
2. Note the device name
3. Via SSH:
   ```sh
   bluetoothctl remove <MAC_ADDRESS>
   ```

## 🎨 Assets & Customization

### 🖼️ Screensaver GIFs
Place custom GIFs in `rpi_usb_cloner/ui/assets/gifs/` and the screensaver will automatically pick them up.

### 🔤 Font assets
This project uses Lucide icons; see <https://lucide.dev/license> for license details.
