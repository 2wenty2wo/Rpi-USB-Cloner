"""Bluetooth PAN (Personal Area Network) service for RPi-USB-Cloner.

This module provides Bluetooth tethering functionality allowing the Pi to:
1. Act as a Bluetooth NAP (Network Access Point)
2. Accept connections from phones (iPhone/Android)
3. Provide internet access via phone tethering
4. Display QR codes for easy pairing

The flow:
1. Enable Bluetooth mode -> Pi becomes discoverable with random PIN
2. User scans QR code or manually pairs with PIN
3. Phone connects and enables internet sharing
4. Pi gets network access via bnep0 interface
"""

from __future__ import annotations

import ipaddress
import secrets
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable

from rpi_usb_cloner.logging import LoggerFactory

log = LoggerFactory.for_system()

# Bluetooth PAN configuration
DEFAULT_PAN_IP = "192.168.50.1"
DEFAULT_PAN_SUBNET = "192.168.50.0/24"
DEFAULT_DHCP_RANGE_START = "192.168.50.10"
DEFAULT_DHCP_RANGE_END = "192.168.50.50"
BTPAN_BRIDGE_NAME = "pan0"
BTPAN_DEVICE_NAME = "RPI-USB-CLONER"
PIN_LENGTH = 6

# D-Bus constants for BlueZ Network Server
BLUEZ_SERVICE = "org.bluez"
NETWORK_SERVER_INTERFACE = "org.bluez.NetworkServer1"
ADAPTER_INTERFACE = "org.bluez.Adapter1"
DEVICE_INTERFACE = "org.bluez.Device1"
DBUS_OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"


@dataclass
class BluetoothStatus:
    """Current Bluetooth PAN status."""

    enabled: bool
    mac_address: str | None
    pin: str | None
    ip_address: str | None
    connected: bool
    connected_device: str | None
    bnep_interface: str | None


class BluetoothPANManager:
    """Manages Bluetooth PAN functionality.

    This class handles:
    - Enabling/disabling Bluetooth PAN mode
    - Generating random PINs for secure pairing
    - Creating QR codes for easy pairing
    - Monitoring connection status
    - Managing the network bridge
    - Auto-reconnecting to trusted devices
    """

    def __init__(self) -> None:
        self._enabled = False
        self._pin: str | None = None
        self._mac_address: str | None = None
        self._bnep_interface: str | None = None
        self._connected_device: str | None = None
        self._status_lock = threading.Lock()
        self._status_listeners: list[Callable[[BluetoothStatus], None]] = []
        self._monitor_thread: threading.Thread | None = None
        self._stop_monitor = threading.Event()
        self._reconnect_thread: threading.Thread | None = None
        self._trusted_devices: list[dict] = []

    def _get_adapter_mac(self) -> str | None:
        """Get the Bluetooth adapter MAC address."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "show"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "Controller" in line and ":" in line:
                        # Line format: "Controller AA:BB:CC:DD:EE:FF rpi-usb-cloner"
                        parts = line.split()
                        if len(parts) >= 2:
                            return parts[1].upper()
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError) as e:
            log.debug(f"Failed to get Bluetooth MAC: {e}")
        return None

    def _generate_pin(self) -> str:
        """Generate a random PIN for pairing."""
        return secrets.token_hex(PIN_LENGTH // 2).upper()[:PIN_LENGTH]

    def _run_command(
        self, cmd: list[str], check: bool = True, timeout: int = 10
    ) -> subprocess.CompletedProcess[str]:
        """Run a shell command with logging."""
        log.debug(f"Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=check, timeout=timeout
            )
            if result.stdout:
                log.debug(f"stdout: {result.stdout.strip()}")
            if result.stderr:
                log.debug(f"stderr: {result.stderr.strip()}")
            return result
        except subprocess.CalledProcessError as e:
            log.warning(f"Command failed: {' '.join(cmd)} - {e}")
            raise

    def _setup_bridge(self) -> bool:
        """Create and configure the bridge interface for PAN."""
        try:
            # Check if bridge already exists
            result = subprocess.run(
                ["ip", "link", "show", BTPAN_BRIDGE_NAME],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                log.info(f"Bridge {BTPAN_BRIDGE_NAME} already exists")
                # Ensure it has an IP
                self._run_command(
                    ["ip", "addr", "add", f"{DEFAULT_PAN_IP}/24", "dev", BTPAN_BRIDGE_NAME],
                    check=False,
                )
                self._run_command(["ip", "link", "set", BTPAN_BRIDGE_NAME, "up"])
                return True

            # Create bridge
            self._run_command(["ip", "link", "add", BTPAN_BRIDGE_NAME, "type", "bridge"])
            self._run_command(["ip", "addr", "add", f"{DEFAULT_PAN_IP}/24", "dev", BTPAN_BRIDGE_NAME])
            self._run_command(["ip", "link", "set", BTPAN_BRIDGE_NAME, "up"])
            log.info(f"Created bridge {BTPAN_BRIDGE_NAME} with IP {DEFAULT_PAN_IP}")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            log.error(f"Failed to setup bridge: {e}")
            return False

    def _remove_bridge(self) -> None:
        """Remove the bridge interface."""
        try:
            self._run_command(["ip", "link", "set", BTPAN_BRIDGE_NAME, "down"], check=False)
            self._run_command(["ip", "link", "delete", BTPAN_BRIDGE_NAME], check=False)
            log.info(f"Removed bridge {BTPAN_BRIDGE_NAME}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            log.debug(f"Error removing bridge: {e}")

    def _enable_bluetooth(self) -> bool:
        """Enable Bluetooth adapter and set it to discoverable."""
        try:
            # Power on
            self._run_command(["bluetoothctl", "power", "on"], check=False)
            # Set discoverable
            self._run_command(["bluetoothctl", "discoverable", "on"], check=False)
            # Set pairable
            self._run_command(["bluetoothctl", "pairable", "on"], check=False)
            # Set agent to DisplayYesNo for PIN display
            self._run_command(["bluetoothctl", "agent", "DisplayYesNo"], check=False)
            # Set device name
            self._run_command(["bluetoothctl", "system-alias", BTPAN_DEVICE_NAME], check=False)
            log.info("Bluetooth enabled and discoverable")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            log.error(f"Failed to enable Bluetooth: {e}")
            return False

    def _disable_bluetooth(self) -> None:
        """Disable Bluetooth discoverability."""
        try:
            self._run_command(["bluetoothctl", "discoverable", "off"], check=False)
            self._run_command(["bluetoothctl", "pairable", "off"], check=False)
            log.info("Bluetooth discoverability disabled")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            log.debug(f"Error disabling Bluetooth: {e}")

    def _register_nap_service(self) -> bool:
        """Register the NAP service with BlueZ via D-Bus."""
        try:
            import dbus

            bus = dbus.SystemBus()
            manager = dbus.Interface(
                bus.get_object(BLUEZ_SERVICE, "/"), DBUS_OBJECT_MANAGER
            )

            # Find the adapter
            adapters = []
            for path, ifaces in manager.GetManagedObjects().items():
                if ADAPTER_INTERFACE in ifaces:
                    adapters.append(path)

            if not adapters:
                log.error("No Bluetooth adapter found")
                return False

            adapter_path = adapters[0]
            log.debug(f"Using Bluetooth adapter: {adapter_path}")

            # Register NAP service
            network_server = dbus.Interface(
                bus.get_object(BLUEZ_SERVICE, adapter_path),
                NETWORK_SERVER_INTERFACE,
            )

            # Unregister first to avoid conflicts
            try:
                network_server.Unregister("nap")
            except dbus.DBusException:
                pass

            # Register NAP with bridge
            network_server.Register("nap", BTPAN_BRIDGE_NAME)
            log.info(f"Registered NAP service on bridge {BTPAN_BRIDGE_NAME}")
            return True

        except ImportError:
            log.error("dbus-python not installed, cannot register NAP service")
            return False
        except dbus.DBusException as e:
            log.error(f"D-Bus error registering NAP: {e}")
            return False

    def _unregister_nap_service(self) -> None:
        """Unregister the NAP service."""
        try:
            import dbus

            bus = dbus.SystemBus()
            manager = dbus.Interface(
                bus.get_object(BLUEZ_SERVICE, "/"), DBUS_OBJECT_MANAGER
            )

            for path, ifaces in manager.GetManagedObjects().items():
                if ADAPTER_INTERFACE in ifaces:
                    network_server = dbus.Interface(
                        bus.get_object(BLUEZ_SERVICE, path),
                        NETWORK_SERVER_INTERFACE,
                    )
                    try:
                        network_server.Unregister("nap")
                        log.info("Unregistered NAP service")
                    except dbus.DBusException:
                        pass
        except Exception as e:
            log.debug(f"Error unregistering NAP: {e}")

    def _find_bnep_interface(self) -> str | None:
        """Find the bnep interface created by the Bluetooth connection."""
        try:
            result = subprocess.run(
                ["ip", "link", "show", "type", "bridge_slave"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "bnep" in line:
                        # Extract interface name
                        parts = line.split(":")
                        if len(parts) >= 2:
                            return parts[1].strip()

            # Alternative: look for bnep interfaces directly
            result = subprocess.run(
                ["ip", "link", "show"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                if "bnep" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        return parts[1].strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            log.debug(f"Error finding bnep interface: {e}")
        return None

    def _check_connection_status(self) -> tuple[bool, str | None]:
        """Check if a device is connected via Bluetooth PAN."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "devices", "Connected"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Parse connected devices
                lines = result.stdout.strip().splitlines()
                for line in lines:
                    if "Device" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            mac = parts[1]
                            name = " ".join(parts[2:])
                            return True, f"{name} ({mac})"
                return True, "Unknown device"
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError) as e:
            log.debug(f"Error checking connection status: {e}")
        return False, None

    def _monitor_loop(self) -> None:
        """Background thread to monitor connection status."""
        while not self._stop_monitor.wait(timeout=2.0):
            connected, device = self._check_connection_status()
            bnep = self._find_bnep_interface()

            with self._status_lock:
                changed = (
                    connected != self._connected_device
                    or bnep != self._bnep_interface
                )
                self._connected_device = device if connected else None
                self._bnep_interface = bnep

            if changed:
                self._notify_listeners()

    def _notify_listeners(self) -> None:
        """Notify all status listeners of a status change."""
        status = self.get_status()
        for listener in self._status_listeners:
            try:
                listener(status)
            except Exception as e:
                log.warning(f"Error in status listener: {e}")

    def add_status_listener(self, callback: Callable[[BluetoothStatus], None]) -> None:
        """Add a callback to be called when status changes."""
        self._status_listeners.append(callback)

    def remove_status_listener(self, callback: Callable[[BluetoothStatus], None]) -> None:
        """Remove a status callback."""
        if callback in self._status_listeners:
            self._status_listeners.remove(callback)

    def enable(self) -> bool:
        """Enable Bluetooth PAN mode.

        Returns:
            True if successfully enabled, False otherwise.
        """
        if self._enabled:
            log.info("Bluetooth PAN already enabled")
            return True

        log.info("Enabling Bluetooth PAN mode...")

        # Generate new PIN
        self._pin = self._generate_pin()

        # Get MAC address
        self._mac_address = self._get_adapter_mac()
        if not self._mac_address:
            log.error("Could not get Bluetooth MAC address")
            return False

        # Enable Bluetooth
        if not self._enable_bluetooth():
            return False

        # Setup bridge
        if not self._setup_bridge():
            self._disable_bluetooth()
            return False

        # Register NAP service
        if not self._register_nap_service():
            log.warning("Could not register NAP service via D-Bus, continuing anyway")
            # Don't fail - bluetoothctl might still work for basic pairing

        self._enabled = True

        # Load trusted devices
        self._trusted_devices = self._load_trusted_devices()

        # Start monitoring thread
        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

        # Start auto-reconnect thread if enabled
        if self._is_auto_reconnect_enabled() and self._trusted_devices:
            self._reconnect_thread = threading.Thread(
                target=self._reconnect_loop, daemon=True
            )
            self._reconnect_thread.start()

        log.info(f"Bluetooth PAN enabled. PIN: {self._pin}, MAC: {self._mac_address}")
        self._notify_listeners()
        return True

    def disable(self) -> None:
        """Disable Bluetooth PAN mode."""
        if not self._enabled:
            return

        log.info("Disabling Bluetooth PAN mode...")

        # Stop monitoring threads
        self._stop_monitor.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=3)
        if self._reconnect_thread:
            self._reconnect_thread.join(timeout=3)

        # Unregister NAP
        self._unregister_nap_service()

        # Disable Bluetooth discoverability
        self._disable_bluetooth()

        # Remove bridge
        self._remove_bridge()

        self._enabled = False
        self._pin = None
        self._connected_device = None
        self._bnep_interface = None

        self._notify_listeners()
        log.info("Bluetooth PAN disabled")

    def toggle(self) -> bool:
        """Toggle Bluetooth PAN mode on/off.

        Returns:
            New state (True = enabled, False = disabled).
        """
        if self._enabled:
            self.disable()
            return False
        else:
            return self.enable()

    def get_status(self) -> BluetoothStatus:
        """Get current Bluetooth PAN status."""
        with self._status_lock:
            return BluetoothStatus(
                enabled=self._enabled,
                mac_address=self._mac_address,
                pin=self._pin,
                ip_address=DEFAULT_PAN_IP if self._enabled else None,
                connected=self._connected_device is not None,
                connected_device=self._connected_device,
                bnep_interface=self._bnep_interface,
            )

    def generate_pairing_data(self) -> dict[str, str]:
        """Generate pairing information for QR code.

        Returns:
            Dictionary with pairing information.
        """
        status = self.get_status()
        if not status.enabled:
            return {"error": "Bluetooth not enabled"}

        return {
            "device_name": BTPAN_DEVICE_NAME,
            "mac_address": status.mac_address or "Unknown",
            "pin": status.pin or "000000",
            "web_url": f"http://{DEFAULT_PAN_IP}:8000",
        }

    def generate_qr_text(self) -> str:
        """Generate QR code content string.

        Returns the web UI URL for easy access after manual Bluetooth pairing.
        Note: iOS/Android don't support auto-pairing from QR codes, so users
        manually pair via Bluetooth settings, then scan this QR to open the web UI.
        """
        data = self.generate_pairing_data()
        if "error" in data:
            return ""

        # Just the URL - scan to open web UI in browser
        return data['web_url']

    # -------------------------------------------------------------------------
    # Trusted Devices & Auto-Reconnect
    # -------------------------------------------------------------------------

    def _load_trusted_devices(self) -> list[dict]:
        """Load trusted devices from settings."""
        try:
            from rpi_usb_cloner.config.settings import get_setting

            devices = get_setting("bluetooth_trusted_devices", [])
            if isinstance(devices, list):
                return devices
        except Exception as e:
            log.debug(f"Failed to load trusted devices: {e}")
        return []

    def _save_trusted_devices(self) -> None:
        """Save trusted devices to settings."""
        try:
            from rpi_usb_cloner.config.settings import set_setting

            set_setting("bluetooth_trusted_devices", self._trusted_devices)
        except Exception as e:
            log.debug(f"Failed to save trusted devices: {e}")

    def get_trusted_devices(self) -> list[dict]:
        """Get list of trusted devices.

        Returns:
            List of device dicts with keys: mac, name, paired_at
        """
        return list(self._trusted_devices)

    def add_trusted_device(self, mac_address: str, name: str = "") -> None:
        """Add a device to the trusted list.

        Args:
            mac_address: Device MAC address (normalized to uppercase)
            name: Optional device name
        """
        mac = mac_address.upper().strip()

        # Remove existing entry for this MAC
        self._trusted_devices = [
            d for d in self._trusted_devices if d.get("mac", "").upper() != mac
        ]

        # Add new entry
        from datetime import datetime, timezone

        self._trusted_devices.append({
            "mac": mac,
            "name": name or f"Device {mac[-5:].replace(':', '')}",
            "paired_at": datetime.now(timezone.utc).isoformat(),
        })

        self._save_trusted_devices()
        log.info(f"Added trusted Bluetooth device: {mac} ({name})")

    def remove_trusted_device(self, mac_address: str) -> bool:
        """Remove a device from the trusted list.

        Args:
            mac_address: Device MAC address

        Returns:
            True if device was removed, False if not found
        """
        mac = mac_address.upper().strip()
        original_count = len(self._trusted_devices)

        self._trusted_devices = [
            d for d in self._trusted_devices if d.get("mac", "").upper() != mac
        ]

        if len(self._trusted_devices) < original_count:
            self._save_trusted_devices()
            log.info(f"Removed trusted Bluetooth device: {mac}")
            return True
        return False

    def is_device_trusted(self, mac_address: str) -> bool:
        """Check if a device is in the trusted list.

        Args:
            mac_address: Device MAC address

        Returns:
            True if device is trusted
        """
        mac = mac_address.upper().strip()
        return any(
            d.get("mac", "").upper() == mac for d in self._trusted_devices
        )

    def forget_all_devices(self) -> None:
        """Remove all trusted devices."""
        self._trusted_devices = []
        self._save_trusted_devices()
        log.info("Cleared all trusted Bluetooth devices")

    def _is_auto_reconnect_enabled(self) -> bool:
        """Check if auto-reconnect is enabled in settings."""
        try:
            from rpi_usb_cloner.config.settings import get_bool

            return get_bool("bluetooth_auto_reconnect", default=True)
        except Exception:
            return True

    def _get_connected_devices(self) -> list[tuple[str, str]]:
        """Get list of currently connected Bluetooth devices.

        Returns:
            List of (mac, name) tuples
        """
        devices = []
        try:
            result = subprocess.run(
                ["bluetoothctl", "devices", "Connected"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    if "Device" in line:
                        parts = line.split(maxsplit=2)
                        if len(parts) >= 3:
                            mac = parts[1]
                            name = parts[2]
                            devices.append((mac, name))
        except Exception as e:
            log.debug(f"Failed to get connected devices: {e}")
        return devices

    def _get_paired_devices(self) -> list[tuple[str, str]]:
        """Get list of paired (but not necessarily connected) Bluetooth devices.

        Returns:
            List of (mac, name) tuples
        """
        devices = []
        try:
            result = subprocess.run(
                ["bluetoothctl", "devices", "Paired"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    if "Device" in line:
                        parts = line.split(maxsplit=2)
                        if len(parts) >= 3:
                            mac = parts[1]
                            name = parts[2]
                            devices.append((mac, name))
        except Exception as e:
            log.debug(f"Failed to get paired devices: {e}")
        return devices

    def _auto_connect_device(self, mac_address: str) -> bool:
        """Attempt to connect to a specific device.

        Args:
            mac_address: Device MAC address

        Returns:
            True if connection initiated successfully
        """
        try:
            mac = mac_address.upper().strip()
            log.info(f"Auto-connecting to trusted device: {mac}")

            # Trust the device
            self._run_command(["bluetoothctl", "trust", mac], check=False)

            # Attempt connection
            result = subprocess.run(
                ["bluetoothctl", "connect", mac],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 or "Connection successful" in result.stdout:
                log.info(f"Successfully connected to {mac}")
                return True
            else:
                log.debug(f"Connection attempt result: {result.stdout} {result.stderr}")
        except Exception as e:
            log.debug(f"Failed to auto-connect to {mac_address}: {e}")
        return False

    def _reconnect_loop(self) -> None:
        """Background thread for auto-reconnecting to trusted devices."""
        log.info("Starting Bluetooth auto-reconnect thread")

        # Initial delay to let Bluetooth fully initialize
        time.sleep(5)

        while not self._stop_monitor.is_set():
            if not self._is_auto_reconnect_enabled():
                time.sleep(5)
                continue

            if not self._enabled:
                time.sleep(5)
                continue

            # If already connected, nothing to do
            connected_devices = self._get_connected_devices()
            if connected_devices:
                time.sleep(5)
                continue

            # Try to connect to trusted devices
            trusted_macs = {d.get("mac", "").upper() for d in self._trusted_devices}

            if trusted_macs:
                log.debug(f"Attempting auto-reconnect to {len(trusted_macs)} trusted devices")

                # First check paired devices
                paired = self._get_paired_devices()
                for mac, name in paired:
                    if mac.upper() in trusted_macs:
                        if self._auto_connect_device(mac):
                            # Add to trusted if not already
                            if not self.is_device_trusted(mac):
                                self.add_trusted_device(mac, name)
                            time.sleep(2)
                            break  # Connected successfully

            # Wait before next attempt
            time.sleep(10)

        log.info("Bluetooth auto-reconnect thread stopped")

    def enable_auto_reconnect(self) -> None:
        """Enable auto-reconnect in settings."""
        try:
            from rpi_usb_cloner.config.settings import set_bool
            set_bool("bluetooth_auto_reconnect", True)
            log.info("Bluetooth auto-reconnect enabled")
        except Exception as e:
            log.debug(f"Failed to enable auto-reconnect: {e}")

    def disable_auto_reconnect(self) -> None:
        """Disable auto-reconnect in settings."""
        try:
            from rpi_usb_cloner.config.settings import set_bool
            set_bool("bluetooth_auto_reconnect", False)
            log.info("Bluetooth auto-reconnect disabled")
        except Exception as e:
            log.debug(f"Failed to disable auto-reconnect: {e}")

    def is_auto_reconnect_enabled(self) -> bool:
        """Check if auto-reconnect is enabled."""
        return self._is_auto_reconnect_enabled()

    def trust_current_device(self) -> bool:
        """Trust the currently connected device.

        Returns:
            True if a device was found and trusted
        """
        connected = self._get_connected_devices()
        if not connected:
            return False

        for mac, name in connected:
            self.add_trusted_device(mac, name)
            # Also trust in bluetoothctl
            try:
                self._run_command(["bluetoothctl", "trust", mac], check=False)
            except Exception:
                pass

        return True


# Global manager instance
_bluetooth_manager: BluetoothPANManager | None = None
_manager_lock = threading.Lock()


def get_bluetooth_manager() -> BluetoothPANManager:
    """Get the global Bluetooth PAN manager instance."""
    global _bluetooth_manager
    with _manager_lock:
        if _bluetooth_manager is None:
            _bluetooth_manager = BluetoothPANManager()
        return _bluetooth_manager


def enable_bluetooth_pan() -> bool:
    """Enable Bluetooth PAN mode (convenience function)."""
    return get_bluetooth_manager().enable()


def disable_bluetooth_pan() -> None:
    """Disable Bluetooth PAN mode (convenience function)."""
    get_bluetooth_manager().disable()


def toggle_bluetooth_pan() -> bool:
    """Toggle Bluetooth PAN mode (convenience function)."""
    return get_bluetooth_manager().toggle()


def get_bluetooth_status() -> BluetoothStatus:
    """Get Bluetooth PAN status (convenience function)."""
    return get_bluetooth_manager().get_status()


def generate_qr_data() -> dict[str, str]:
    """Generate pairing data for QR code (convenience function)."""
    return get_bluetooth_manager().generate_pairing_data()


def generate_qr_text() -> str:
    """Generate QR code text (convenience function)."""
    return get_bluetooth_manager().generate_qr_text()


def is_bluetooth_pan_enabled() -> bool:
    """Check if Bluetooth PAN is enabled."""
    return get_bluetooth_manager().get_status().enabled


def is_bluetooth_connected() -> bool:
    """Check if a device is connected via Bluetooth PAN."""
    return get_bluetooth_manager().get_status().connected


def get_trusted_bluetooth_devices() -> list[dict]:
    """Get list of trusted Bluetooth devices."""
    return get_bluetooth_manager().get_trusted_devices()


def add_trusted_bluetooth_device(mac_address: str, name: str = "") -> None:
    """Add a device to the trusted list for auto-reconnect."""
    get_bluetooth_manager().add_trusted_device(mac_address, name)


def remove_trusted_bluetooth_device(mac_address: str) -> bool:
    """Remove a device from the trusted list."""
    return get_bluetooth_manager().remove_trusted_device(mac_address)


def forget_all_bluetooth_devices() -> None:
    """Remove all trusted Bluetooth devices."""
    get_bluetooth_manager().forget_all_devices()


def trust_current_bluetooth_device() -> bool:
    """Trust the currently connected Bluetooth device."""
    return get_bluetooth_manager().trust_current_device()


def is_bluetooth_auto_reconnect_enabled() -> bool:
    """Check if auto-reconnect is enabled."""
    return get_bluetooth_manager().is_auto_reconnect_enabled()


def set_bluetooth_auto_reconnect(enabled: bool) -> None:
    """Enable/disable auto-reconnect."""
    if enabled:
        get_bluetooth_manager().enable_auto_reconnect()
    else:
        get_bluetooth_manager().disable_auto_reconnect()
