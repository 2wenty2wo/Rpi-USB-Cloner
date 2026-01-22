"""
Bluetooth tethering service for network connectivity.

Provides Bluetooth PAN (Personal Area Network) functionality to allow
iPhone and other devices to connect to the Raspberry Pi via Bluetooth
and access the web UI.

Requires system packages:
    - bluez (Bluetooth stack)
    - bluez-tools (bt-agent, bt-network)
    - bridge-utils (brctl)
    - dnsmasq (DHCP server)
"""

import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from rpi_usb_cloner.logging import get_logger


logger = get_logger(source="bluetooth", tags=["bluetooth"])


@dataclass
class BluetoothDevice:
    """Represents a Bluetooth device."""

    mac_address: str
    name: str
    paired: bool
    connected: bool
    trusted: bool


@dataclass
class BluetoothStatus:
    """Current Bluetooth adapter status."""

    adapter_present: bool
    powered: bool
    discoverable: bool
    pairable: bool
    pan_active: bool
    ip_address: Optional[str]
    connected_devices: List[BluetoothDevice]


class BluetoothService:
    """Manages Bluetooth PAN (Personal Area Network) for tethering."""

    # Network configuration for Bluetooth PAN
    BRIDGE_INTERFACE = "pan0"
    BRIDGE_IP = "192.168.55.1"
    BRIDGE_NETMASK = "255.255.255.0"
    DHCP_RANGE_START = "192.168.55.50"
    DHCP_RANGE_END = "192.168.55.150"
    DHCP_LEASE_TIME = "12h"

    def __init__(self):
        """Initialize Bluetooth service."""
        self._adapter_name: Optional[str] = None
        self._pan_process: Optional[subprocess.Popen] = None
        self._dnsmasq_process: Optional[subprocess.Popen] = None
        self._last_error: Optional[str] = None

    @property
    def last_error(self) -> Optional[str]:
        """Return the most recent Bluetooth error message, if any."""
        return self._last_error

    def _clear_last_error(self) -> None:
        """Clear the stored Bluetooth error message."""
        self._last_error = None

    def _extract_process_reason(self, error: Exception) -> str:
        """Extract a user-friendly reason from a subprocess error."""
        stdout = getattr(error, "stdout", None)
        stderr = getattr(error, "stderr", None)
        for candidate in (stderr, stdout):
            if candidate:
                reason = candidate.strip()
                if reason:
                    return reason
        return str(error)

    def _format_process_error(self, error: Exception) -> str:
        """Format subprocess error details for logs."""
        stdout = getattr(error, "stdout", None)
        stderr = getattr(error, "stderr", None)
        details = []
        if stdout:
            details.append(f"stdout: {stdout.strip()}")
        if stderr:
            details.append(f"stderr: {stderr.strip()}")
        if details:
            return f"{error} ({'; '.join(details)})"
        return str(error)

    def _unblock_bluetooth_rfkill(self) -> Optional[bool]:
        """Attempt to unblock Bluetooth via rfkill if available."""
        if not shutil.which("rfkill"):
            logger.info("rfkill not available; skipping bluetooth unblock")
            return None
        try:
            subprocess.run(
                ["rfkill", "unblock", "bluetooth"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            logger.info("rfkill unblock bluetooth executed")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(
                "Failed to unblock Bluetooth via rfkill: %s",
                self._format_process_error(e),
            )
            return False

    def _get_bluetooth_service_state(self) -> Optional[str]:
        """Return the Bluetooth systemd service state when available."""
        if not shutil.which("systemctl"):
            return None
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "bluetooth"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Failed to check bluetooth service state: %s", e)
            return None
        state = result.stdout.strip() or result.stderr.strip()
        return state or "unknown"

    def _start_bluetooth_service(self) -> bool:
        """Attempt to start the Bluetooth systemd service."""
        if not shutil.which("systemctl"):
            return False
        try:
            subprocess.run(
                ["systemctl", "start", "bluetooth"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            logger.info("Bluetooth service started")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(
                "Failed to start bluetooth service: %s",
                self._format_process_error(e),
            )
            return False

    def _ensure_bluetooth_service_active(self) -> Tuple[Optional[str], Optional[bool]]:
        """Ensure the Bluetooth service is active when systemctl is available."""
        state = self._get_bluetooth_service_state()
        if state and state != "active":
            started = self._start_bluetooth_service()
            return state, started
        return state, None

    def get_adapter_name(self) -> Optional[str]:
        """
        Get the default Bluetooth adapter name.

        Returns:
            Adapter name (e.g., 'hci0') or None if not found
        """
        if self._adapter_name:
            return self._adapter_name

        try:
            result = subprocess.run(
                ["bluetoothctl", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                # Parse output: "Controller XX:XX:XX:XX:XX:XX hci0 [default]"
                for line in result.stdout.splitlines():
                    if "Controller" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            # Extract adapter name (e.g., 'hci0')
                            adapter = parts[2]
                            self._adapter_name = adapter
                            return adapter
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Failed to get Bluetooth adapter: {e}")

        return None

    def is_available(self) -> bool:
        """
        Check if Bluetooth is available on the system.

        Returns:
            True if Bluetooth adapter is present
        """
        adapter = self.get_adapter_name()
        return adapter is not None

    def get_status(self) -> BluetoothStatus:
        """
        Get current Bluetooth adapter status.

        Returns:
            BluetoothStatus object with current state
        """
        adapter = self.get_adapter_name()

        if not adapter:
            return BluetoothStatus(
                adapter_present=False,
                powered=False,
                discoverable=False,
                pairable=False,
                pan_active=False,
                ip_address=None,
                connected_devices=[],
            )

        # Get adapter info
        powered = self._get_adapter_property("Powered")
        discoverable = self._get_adapter_property("Discoverable")
        pairable = self._get_adapter_property("Pairable")

        # Check if PAN interface exists
        pan_active = self._is_interface_up(self.BRIDGE_INTERFACE)

        # Get IP address of bridge interface
        ip_address = None
        if pan_active:
            ip_address = self._get_interface_ip(self.BRIDGE_INTERFACE)

        # Get connected devices
        connected_devices = self.list_paired_devices()

        return BluetoothStatus(
            adapter_present=True,
            powered=powered,
            discoverable=discoverable,
            pairable=pairable,
            pan_active=pan_active,
            ip_address=ip_address,
            connected_devices=connected_devices,
        )

    def _get_adapter_property(self, property_name: str) -> bool:
        """
        Get a boolean property from the Bluetooth adapter.

        Args:
            property_name: Property to query (e.g., 'Powered', 'Discoverable')

        Returns:
            True if property is 'yes', False otherwise
        """
        adapter = self.get_adapter_name()
        if not adapter:
            return False

        try:
            result = subprocess.run(
                ["bluetoothctl", "show"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if property_name in line:
                        return "yes" in line.lower()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return False

    def power_on(self) -> bool:
        """
        Power on the Bluetooth adapter.

        Returns:
            True if successful
        """
        self._unblock_bluetooth_rfkill()
        self._ensure_bluetooth_service_active()
        try:
            subprocess.run(
                ["bluetoothctl", "power", "on"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            self._clear_last_error()
            logger.info("Bluetooth adapter powered on")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            rfkill_result = self._unblock_bluetooth_rfkill()
            service_state, service_started = self._ensure_bluetooth_service_active()
            remediation_steps = []
            details = []
            if shutil.which("rfkill"):
                remediation_steps.append("rfkill unblock bluetooth")
                if rfkill_result is True:
                    details.append("rfkill unblock attempted")
                elif rfkill_result is False:
                    details.append("rfkill unblock failed")
            if shutil.which("systemctl"):
                remediation_steps.append("systemctl start bluetooth")
                if service_state:
                    details.append(f"bluetooth service state: {service_state}")
                if service_state and service_state != "active" and service_started is not None:
                    if service_started:
                        details.append("systemctl start attempted")
                    else:
                        details.append("systemctl start failed")
            detail_text = " ".join(details).strip()
            remediation_text = ""
            if remediation_steps:
                remediation_text = f" Next steps: {', '.join(remediation_steps)}."
            base_reason = self._extract_process_reason(e)
            if detail_text:
                self._last_error = f"{base_reason}. {detail_text}.{remediation_text}".strip()
            else:
                self._last_error = f"{base_reason}.{remediation_text}".strip()
            logger.error(
                f"Failed to power on Bluetooth: {self._format_process_error(e)}"
            )
            return False

    def power_off(self) -> bool:
        """
        Power off the Bluetooth adapter.

        Returns:
            True if successful
        """
        try:
            subprocess.run(
                ["bluetoothctl", "power", "off"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            self._clear_last_error()
            logger.info("Bluetooth adapter powered off")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self._last_error = self._extract_process_reason(e)
            logger.error(
                f"Failed to power off Bluetooth: {self._format_process_error(e)}"
            )
            return False

    def set_discoverable(self, enabled: bool, timeout: int = 0) -> bool:
        """
        Make the device discoverable for pairing.

        Args:
            enabled: True to enable discoverable mode
            timeout: Timeout in seconds (0 = infinite)

        Returns:
            True if successful
        """
        try:
            # Set pairable first
            subprocess.run(
                ["bluetoothctl", "pairable", "on" if enabled else "off"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )

            # Set discoverable
            subprocess.run(
                ["bluetoothctl", "discoverable", "on" if enabled else "off"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )

            # Set discoverable timeout if specified
            if enabled and timeout > 0:
                subprocess.run(
                    ["bluetoothctl", "discoverable-timeout", str(timeout)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                )

            self._clear_last_error()
            logger.info(f"Discoverable mode: {'enabled' if enabled else 'disabled'}")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self._last_error = self._extract_process_reason(e)
            logger.error(
                f"Failed to set discoverable mode: {self._format_process_error(e)}"
            )
            return False

    def list_paired_devices(self) -> List[BluetoothDevice]:
        """
        List all paired Bluetooth devices.

        Returns:
            List of BluetoothDevice objects
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
                for line in result.stdout.splitlines():
                    # Parse: "Device XX:XX:XX:XX:XX:XX Device Name"
                    if line.startswith("Device"):
                        parts = line.split(maxsplit=2)
                        if len(parts) >= 3:
                            mac = parts[1]
                            name = parts[2] if len(parts) > 2 else "Unknown"

                            # Get device info
                            info = self._get_device_info(mac)

                            devices.append(
                                BluetoothDevice(
                                    mac_address=mac,
                                    name=name,
                                    paired=True,
                                    connected=info.get("Connected", False),
                                    trusted=info.get("Trusted", False),
                                )
                            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Failed to list paired devices: {e}")

        return devices

    def _get_device_info(self, mac_address: str) -> Dict[str, bool]:
        """
        Get detailed information about a Bluetooth device.

        Args:
            mac_address: MAC address of device

        Returns:
            Dictionary with device properties
        """
        info = {"Connected": False, "Trusted": False, "Paired": False}

        try:
            result = subprocess.run(
                ["bluetoothctl", "info", mac_address],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "Connected:" in line:
                        info["Connected"] = "yes" in line.lower()
                    elif "Trusted:" in line:
                        info["Trusted"] = "yes" in line.lower()
                    elif "Paired:" in line:
                        info["Paired"] = "yes" in line.lower()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return info

    def trust_device(self, mac_address: str) -> bool:
        """
        Trust a paired device for automatic connection.

        Args:
            mac_address: MAC address of device to trust

        Returns:
            True if successful
        """
        try:
            subprocess.run(
                ["bluetoothctl", "trust", mac_address],
                capture_output=True,
                timeout=5,
                check=True,
            )
            logger.info(f"Trusted device: {mac_address}")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Failed to trust device {mac_address}: {e}")
            return False

    def remove_device(self, mac_address: str) -> bool:
        """
        Remove (unpair) a device.

        Args:
            mac_address: MAC address of device to remove

        Returns:
            True if successful
        """
        try:
            subprocess.run(
                ["bluetoothctl", "remove", mac_address],
                capture_output=True,
                timeout=5,
                check=True,
            )
            logger.info(f"Removed device: {mac_address}")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Failed to remove device {mac_address}: {e}")
            return False

    def setup_pan(self) -> bool:
        """
        Set up Bluetooth PAN (Personal Area Network).

        This creates a network bridge that allows connected Bluetooth
        devices to access the web UI.

        Returns:
            True if successful
        """
        try:
            # 1. Power on Bluetooth
            if not self.power_on():
                return False

            # 2. Create bridge interface
            if not self._create_bridge():
                self.teardown_pan()
                return False

            # 3. Configure IP address
            if not self._configure_bridge_ip():
                self.teardown_pan()
                return False

            # 4. Start DHCP server
            if not self._start_dhcp_server():
                self.teardown_pan()
                return False

            # 5. Enable NAP (Network Access Point) profile
            if not self._enable_nap():
                self.teardown_pan()
                return False

            logger.info("Bluetooth PAN setup complete")
            return True

        except Exception as e:
            logger.error(f"Failed to setup Bluetooth PAN: {e}")
            self.teardown_pan()
            return False

    def _create_bridge(self) -> bool:
        """Create the network bridge interface."""
        try:
            # Check if bridge already exists
            if self._is_interface_up(self.BRIDGE_INTERFACE):
                logger.info(f"Bridge {self.BRIDGE_INTERFACE} already exists")
                return True

            # Create bridge using ip command
            subprocess.run(
                ["ip", "link", "add", "name", self.BRIDGE_INTERFACE, "type", "bridge"],
                capture_output=True,
                timeout=5,
                check=True,
            )

            # Bring bridge up
            subprocess.run(
                ["ip", "link", "set", "dev", self.BRIDGE_INTERFACE, "up"],
                capture_output=True,
                timeout=5,
                check=True,
            )

            logger.info(f"Created bridge interface: {self.BRIDGE_INTERFACE}")
            return True

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Failed to create bridge: {e}")
            return False

    def _configure_bridge_ip(self) -> bool:
        """Configure IP address for the bridge interface."""
        try:
            # Add IP address to bridge
            subprocess.run(
                [
                    "ip",
                    "addr",
                    "add",
                    f"{self.BRIDGE_IP}/{self._netmask_to_cidr(self.BRIDGE_NETMASK)}",
                    "dev",
                    self.BRIDGE_INTERFACE,
                ],
                capture_output=True,
                timeout=5,
                check=True,
            )

            logger.info(f"Configured bridge IP: {self.BRIDGE_IP}")
            return True

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Failed to configure bridge IP: {e}")
            return False

    def _start_dhcp_server(self) -> bool:
        """Start DHCP server for PAN clients."""
        try:
            # Stop any existing dnsmasq instance for this interface
            subprocess.run(
                ["pkill", "-f", f"dnsmasq.*{self.BRIDGE_INTERFACE}"],
                capture_output=True,
                timeout=5,
            )

            # Start dnsmasq as DHCP server
            self._dnsmasq_process = subprocess.Popen(
                [
                    "dnsmasq",
                    "--interface=" + self.BRIDGE_INTERFACE,
                    "--bind-interfaces",
                    "--dhcp-range="
                    + f"{self.DHCP_RANGE_START},{self.DHCP_RANGE_END},{self.DHCP_LEASE_TIME}",
                    "--no-daemon",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            logger.info("Started DHCP server (dnsmasq)")
            return True

        except Exception as e:
            logger.error(f"Failed to start DHCP server: {e}")
            return False

    def _enable_nap(self) -> bool:
        """Enable Bluetooth NAP (Network Access Point) profile."""
        try:
            # Register NAP service with bluetoothd
            # This allows devices to connect via Bluetooth tethering
            adapter = self.get_adapter_name()
            if not adapter:
                return False

            # Use bt-network if available (from bluez-tools)
            result = subprocess.run(
                ["which", "bt-network"], capture_output=True, timeout=5
            )

            if result.returncode != 0:
                self._last_error = "bt-network not installed (bluez-tools required)"
                logger.error(self._last_error)
                return False

            # Start bt-network server
            self._pan_process = subprocess.Popen(
                ["bt-network", "-s", "nap", self.BRIDGE_INTERFACE],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._clear_last_error()
            logger.info("Started Bluetooth NAP server (bt-network)")
            return True

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to enable NAP: {e}")
            return False

    def teardown_pan(self) -> bool:
        """
        Tear down Bluetooth PAN and clean up resources.

        Returns:
            True if successful
        """
        try:
            # Stop processes
            if self._pan_process:
                self._pan_process.terminate()
                self._pan_process.wait(timeout=5)
                self._pan_process = None

            if self._dnsmasq_process:
                self._dnsmasq_process.terminate()
                self._dnsmasq_process.wait(timeout=5)
                self._dnsmasq_process = None

            # Kill any remaining dnsmasq instances for this interface
            subprocess.run(
                ["pkill", "-f", f"dnsmasq.*{self.BRIDGE_INTERFACE}"],
                capture_output=True,
                timeout=5,
            )

            # Remove bridge interface
            if self._is_interface_up(self.BRIDGE_INTERFACE):
                subprocess.run(
                    ["ip", "link", "set", "dev", self.BRIDGE_INTERFACE, "down"],
                    capture_output=True,
                    timeout=5,
                )
                subprocess.run(
                    ["ip", "link", "delete", self.BRIDGE_INTERFACE],
                    capture_output=True,
                    timeout=5,
                )

            logger.info("Bluetooth PAN teardown complete")
            return True

        except Exception as e:
            logger.error(f"Error during PAN teardown: {e}")
            return False

    def _is_interface_up(self, interface: str) -> bool:
        """Check if a network interface exists and is up."""
        try:
            result = subprocess.run(
                ["ip", "link", "show", interface],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _get_interface_ip(self, interface: str) -> Optional[str]:
        """Get the IP address of a network interface."""
        try:
            result = subprocess.run(
                ["ip", "-4", "addr", "show", interface],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("inet "):
                        # Parse: "inet 192.168.55.1/24 ..."
                        ip_with_cidr = line.split()[1]
                        ip = ip_with_cidr.split("/")[0]
                        return ip
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None

    @staticmethod
    def _netmask_to_cidr(netmask: str) -> int:
        """Convert netmask to CIDR notation."""
        # Simple conversion for common netmasks
        netmask_map = {
            "255.255.255.0": 24,
            "255.255.0.0": 16,
            "255.0.0.0": 8,
        }
        return netmask_map.get(netmask, 24)


# Global service instance
_bluetooth_service: Optional[BluetoothService] = None
_availability_cache: Optional[Dict[str, float]] = None
_availability_cache_ttl_seconds = 30.0


def get_bluetooth_service() -> BluetoothService:
    """
    Get the global Bluetooth service instance.

    Returns:
        BluetoothService instance
    """
    global _bluetooth_service
    if _bluetooth_service is None:
        _bluetooth_service = BluetoothService()
    return _bluetooth_service


# Convenience functions for common operations
def is_bluetooth_available() -> bool:
    """Check if Bluetooth is available."""
    global _availability_cache
    now = time.time()
    if _availability_cache:
        cached_at = _availability_cache.get("checked_at", 0.0)
        cached_value = _availability_cache.get("available")
        if cached_value is not None and now - cached_at < _availability_cache_ttl_seconds:
            return bool(cached_value)

    available = get_bluetooth_service().is_available()
    _availability_cache = {"checked_at": now, "available": available}
    return available


def get_bluetooth_status() -> BluetoothStatus:
    """Get current Bluetooth status."""
    return get_bluetooth_service().get_status()


def get_bluetooth_last_error() -> Optional[str]:
    """Get the most recent Bluetooth error message, if any."""
    return get_bluetooth_service().last_error


def enable_bluetooth_tethering() -> bool:
    """Enable Bluetooth tethering (PAN)."""
    return get_bluetooth_service().setup_pan()


def disable_bluetooth_tethering() -> bool:
    """Disable Bluetooth tethering (PAN)."""
    return get_bluetooth_service().teardown_pan()


def make_discoverable(timeout: int = 300) -> bool:
    """
    Make device discoverable for pairing.

    Args:
        timeout: Timeout in seconds (default: 5 minutes)

    Returns:
        True if successful
    """
    service = get_bluetooth_service()
    return service.set_discoverable(True, timeout)


def hide_discoverable() -> bool:
    """Hide device from discovery."""
    return get_bluetooth_service().set_discoverable(False)


def get_paired_devices() -> List[BluetoothDevice]:
    """Get list of paired devices."""
    return get_bluetooth_service().list_paired_devices()


def trust_device(mac_address: str) -> bool:
    """Trust a paired device."""
    return get_bluetooth_service().trust_device(mac_address)


def remove_paired_device(mac_address: str) -> bool:
    """Remove a paired device."""
    return get_bluetooth_service().remove_device(mac_address)
