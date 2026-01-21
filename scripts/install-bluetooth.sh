#!/bin/bash
#
# Bluetooth Tethering Installation Script
# For Raspberry Pi USB Cloner
#
# This script installs the necessary system packages for Bluetooth
# PAN (Personal Area Network) tethering functionality.
#
# Usage:
#   sudo ./scripts/install-bluetooth.sh
#

set -e  # Exit on error

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

echo "================================================"
echo "Bluetooth Tethering Installation"
echo "================================================"
echo ""

# Update package list
echo "[1/4] Updating package list..."
apt-get update -qq

# Install Bluetooth packages
echo "[2/4] Installing Bluetooth packages..."
apt-get install -y \
    bluez \
    bluez-tools \
    bridge-utils \
    dnsmasq

echo ""
echo "[3/4] Checking Bluetooth adapter..."
if hciconfig hci0 >/dev/null 2>&1; then
    echo "✓ Bluetooth adapter detected (hci0)"
else
    echo "⚠ Warning: No Bluetooth adapter detected"
    echo "  This is normal if running on a non-Pi system"
    echo "  or if Bluetooth hardware is not present"
fi

echo ""
echo "[4/4] Configuring Bluetooth service..."

# Enable Bluetooth service
systemctl enable bluetooth.service
systemctl start bluetooth.service

# Check if Bluetooth service is running
if systemctl is-active --quiet bluetooth.service; then
    echo "✓ Bluetooth service is running"
else
    echo "⚠ Warning: Bluetooth service is not running"
    echo "  Try: sudo systemctl start bluetooth.service"
fi

echo ""
echo "================================================"
echo "Installation Complete!"
echo "================================================"
echo ""
echo "Bluetooth tethering dependencies are installed."
echo ""
echo "Next steps:"
echo "  1. Enable Bluetooth in the OLED menu:"
echo "     Main Menu > Tools > Bluetooth > Enable/Disable"
echo ""
echo "  2. Make the device discoverable:"
echo "     Bluetooth > Make Discoverable"
echo ""
echo "  3. Pair from your iPhone:"
echo "     Settings > Bluetooth > RPi USB Cloner"
echo ""
echo "  4. Access web UI from iPhone:"
echo "     Safari: http://192.168.55.1:8000"
echo ""
echo "To enable auto-start on boot, set 'bluetooth_auto_start'"
echo "to true in the Bluetooth menu."
echo ""
