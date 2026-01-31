# Bluetooth PAN (Personal Area Network) Feature

## Overview

The Bluetooth PAN feature allows the RPi-USB-Cloner to:
1. Act as a Bluetooth Network Access Point (NAP)
2. Accept connections from phones (iPhone/Android)
3. Provide internet access via phone tethering
4. Allow access to the web UI without WiFi

This is particularly useful for service technicians who may not have access to WiFi but need to:
- Access the web UI from their phone
- Download updates on the Pi
- Monitor cloning operations remotely

## How It Works

### Architecture

```
┌─────────────────┐      Bluetooth      ┌──────────────────┐
│   iPhone/Android│<------------------->│  Raspberry Pi    │
│                 │      Pairing        │                  │
│  (Internet      │                     │  ┌─────────────┐ │
│   Hotspot)      │                     │  │  BlueZ      │ │
│                 │                     │  │  (NAP)      │ │
└─────────────────┘                     │  └──────┬──────┘ │
                                        │         │        │
                                        │  ┌──────▼──────┐ │
                                        │  │   pan0      │ │
                                        │  │  (bridge)   │ │
                                        │  │192.168.50.1 │ │
                                        │  └─────────────┘ │
                                        │                  │
                                        │  Web UI:8000     │
                                        └──────────────────┘
```

### Connection Flow

1. **Enable Bluetooth Mode** (on Pi)
   - User selects "BLUETOOTH PAN" from Settings → Connectivity
   - Pi enables Bluetooth, makes itself discoverable
   - Random 6-digit PIN is generated
   - Bridge interface `pan0` is created with IP `192.168.50.1`
   - Auto-reconnect thread starts (if trusted devices exist)

2. **Pair Phone** (on Phone)
   - User opens Bluetooth settings on phone
   - Searches for "RPI-USB-CLONER"
   - Pairs using the displayed PIN
   - Enables "Internet Sharing" for the Bluetooth connection

3. **Trust Device** (on Pi)
   - From Bluetooth menu, select "TRUST THIS DEVICE"
   - Device is added to trusted list
   - Future connections will be automatic

4. **Access Web UI**
   - User scans QR code on Pi screen with phone camera
   - QR code opens `http://192.168.50.1:8000` in browser
   - Pi has internet access through phone's data connection

### Auto-Reconnect Feature

Once a device is **trusted**, the Pi will automatically reconnect to it:

- When Bluetooth is enabled
- Every 10 seconds if disconnected
- Works for all trusted devices
- Can be disabled in "TRUSTED DEVICES" menu

### QR Code for Web UI

The Pi displays a QR code containing the web UI URL:
```
http://192.168.50.1:8000
```

**How it works**:
1. User manually pairs with the Pi via Bluetooth settings (using displayed MAC/PIN)
2. Once paired, user scans the QR code with their phone camera
3. QR code opens the web UI directly in their browser

**Note**: iOS and Android do not support auto-pairing Bluetooth from QR codes, so the QR code is for quick web UI access after manual pairing.

## User Interface

### Menu Structure

```
SETTINGS
└── CONNECTIVITY
    ├── WIFI
    ├── WEB SERVER
    └── BLUETOOTH PAN    <-- NEW
        ├── Status Screen
        │   ├── Enable/Disable Bluetooth
        │   ├── Trust This Device (when connected)
        │   └── Show QR Code
        └── Trusted Devices Menu
            ├── Auto-Reconnect: ON/OFF
            ├── List of Trusted Devices
            ├── Forget Device
            └── Forget All Devices
```

### OLED Screens

#### Bluetooth Status Screen
```
┌─────────────────────────────────────┐
│ BLUETOOTH STATUS                    │
├─────────────────────────────────────┤
│ Status: WAITING                     │
│ MAC: AA:BB:CC:DD:EE:FF              │
│ PIN: 123456                         │
│ IP: 192.168.50.1                    │
├─────────────────────────────────────┤
│ A:Back C:Disable                    │
└─────────────────────────────────────┘
```

#### QR Code Screen
```
┌─────────────────────────────────────┐
│ SCAN FOR WEB UI                     │
├─────────────────────────────────────┤
│ ┌─────┐  1.Pair manually            │
│ │ ▄▄▄ │  2.Scan QR code             │
│ │ █▄█ │  RPI-USB-CLONER             │
│ │ ▀▀▀ │  PIN: [123456]              │
│ └─────┘                             │
├─────────────────────────────────────┤
│ A:Back C:Refresh                    │
└─────────────────────────────────────┘
```

## Technical Details

### Files Added/Modified

| File | Purpose |
|------|---------|
| `rpi_usb_cloner/services/bluetooth.py` | Bluetooth PAN management, trusted devices, auto-reconnect |
| `rpi_usb_cloner/ui/screens/qr_code.py` | QR code display screen |
| `rpi_usb_cloner/actions/settings/ui_actions.py` | Bluetooth UI actions, trusted device management |
| `rpi_usb_cloner/menu/actions/settings.py` | Menu action exports |
| `rpi_usb_cloner/menu/actions/__init__.py` | Action registration |
| `rpi_usb_cloner/app/menu_builders.py` | Connectivity menu builder |
| `rpi_usb_cloner/ui/status_bar.py` | Bluetooth status indicator |
| `rpi_usb_cloner/config/settings.py` | Added `bluetooth_trusted_devices` and `bluetooth_auto_reconnect` |
| `requirements.txt` | Added `qrcode[pil]` dependency |

### Configuration

#### Transient Settings
- Bluetooth enabled/disabled state
- Random PIN (generated each session)

#### Persistent Settings (stored in `settings.json`)
- `bluetooth_trusted_devices`: List of trusted devices
  ```json
  [
    {
      "mac": "AA:BB:CC:DD:EE:FF",
      "name": "iPhone",
      "paired_at": "2026-01-31T10:00:00+00:00"
    }
  ]
  ```
- `bluetooth_auto_reconnect`: Enable/disable auto-reconnect (default: true)

### Dependencies

**Python Packages:**
- `qrcode[pil]` - QR code generation (optional fallback if not installed)

**System Packages:**
- `bluez` - Bluetooth stack
- `bridge-utils` - For network bridge
- `dbus-python` - For BlueZ D-Bus interface (usually pre-installed on Raspberry Pi OS)

### Network Configuration

- **Bridge Interface**: `pan0`
- **Pi IP Address**: `192.168.50.1/24`
- **DHCP Range**: `192.168.50.10` - `192.168.50.50` (if using dnsmasq)
- **Web UI**: `http://192.168.50.1:8000`

## Usage Instructions

### Enable Bluetooth PAN

1. Navigate to: **SETTINGS → CONNECTIVITY → BLUETOOTH PAN**
2. Press **SELECT (B)** to toggle Bluetooth on
3. Note the MAC address and PIN displayed

### Pair with iPhone

1. Open **Settings → Bluetooth** on iPhone
2. Look for "RPI-USB-CLONER" under Other Devices
3. Tap to connect, enter the PIN shown on Pi
4. Once connected, tap the ⓘ icon next to RPI-USB-CLONER
5. Enable **Internet Sharing** (if available)

### Pair with Android

1. Open **Settings → Bluetooth** on Android
2. Tap "Pair new device"
3. Select "RPI-USB-CLONER"
4. Enter the PIN shown on Pi
5. Enable "Internet access" or "Tethering" if prompted

### Access Web UI

1. Open browser on phone
2. Navigate to: `http://192.168.50.1:8000`
3. Web UI should load showing Pi's OLED screen

### Disable Bluetooth

1. From Bluetooth status screen, press **C** to disable
2. Or navigate back to menu and toggle off

### Trust a Device (for Auto-Reconnect)

1. Connect to the Pi via Bluetooth from your phone
2. On Pi: **SETTINGS → CONNECTIVITY → BLUETOOTH PAN**
3. Press **B** for menu, select **"TRUST THIS DEVICE"**
4. Device is now saved for auto-reconnect

### Manage Trusted Devices

1. From Bluetooth menu, select **"TRUSTED DEVICES..."**
2. Options:
   - **AUTO-RECONNECT**: Toggle auto-reconnect on/off
   - **Device name**: Select to forget individual device
   - **FORGET ALL DEVICES**: Clear all trusted devices

### Forget a Device

1. Go to **TRUSTED DEVICES** menu
2. Select the device you want to forget
3. Confirm "FORGET DEVICE?"

## Troubleshooting

### Bluetooth won't enable

```bash
# Check if Bluetooth adapter is available
sudo bluetoothctl show

# Check if bluetooth service is running
sudo systemctl status bluetooth

# Enable bluetooth service
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
```

### Can't pair

- Ensure Pi and phone are within 10 meters
- Check PIN is entered correctly (6 digits)
- Try disabling/enabling Bluetooth on Pi
- Check if device is already paired: `bluetoothctl devices`

### No internet access

- On iPhone: Ensure "Personal Hotspot" is enabled in Settings
- On Android: Enable "Bluetooth tethering" in Settings → Network & Internet → Hotspot & Tethering
- Check if `bnep0` interface exists on Pi: `ip link show`

### Web UI not accessible

- Ensure web server is enabled: **SETTINGS → CONNECTIVITY → WEB SERVER**
- Check Pi IP: should be `192.168.50.1`
- Verify connection: `ping 192.168.50.1` from phone

## Security Considerations

1. **Random PIN**: 6-digit random PIN generated each session
2. **No persistent pairing**: Devices not auto-reconnected after restart
3. **Local network only**: No external access (RFC 1918 address space)
4. **No encryption required**: Bluetooth pairing provides link-level security

## Future Enhancements

Potential improvements:
- Remember trusted devices for auto-reconnect
- Configurable IP subnet
- Bluetooth LE (BLE) support for lower power
- NFC pairing alternative
- Web Bluetooth API integration for one-tap pairing (limited browser support)
