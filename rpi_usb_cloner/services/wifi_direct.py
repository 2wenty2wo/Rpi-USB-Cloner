"""WiFi Direct (P2P) service for peer-to-peer wireless transfers.

Uses wpa_cli commands to manage WiFi Direct groups and connections.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from rpi_usb_cloner.logging import get_logger

log = get_logger(source=__name__)


class WiFiDirectError(Exception):
    """Raised when WiFi Direct operations fail."""

    pass


@dataclass
class P2PPeer:
    """Represents a discovered WiFi Direct peer."""

    address: str  # MAC address
    name: str  # Device name (e.g., "DIRECT-RpiCloner-8A5B")
    is_group_owner: bool = False


class WiFiDirectService:
    """Manages WiFi Direct P2P connections via wpa_cli."""

    def __init__(self, interface: str = "wlan0"):
        """Initialize WiFi Direct service.

        Args:
            interface: WiFi interface name (default "wlan0")
        """
        self.interface = interface
        self.p2p_interface: str | None = None
        self.is_group_owner = False
        self._dnsmasq_process: subprocess.Popen | None = None

    def is_p2p_supported(self) -> bool:
        """Check if P2P is supported on this device.

        Returns:
            True if P2P is available
        """
        try:
            result = self._run_wpa_cli("p2p_find", timeout=3)
            # If p2p_find doesn't error, P2P is supported
            return "FAIL" not in result
        except Exception as e:
            log.warning(f"P2P support check failed: {e}")
            return False

    def start_group_owner(self, device_name: str = "RpiCloner") -> str:
        """Start as WiFi Direct Group Owner (Autonomous GO).

        Args:
            device_name: Device name suffix (will be prefixed with "DIRECT-")

        Returns:
            P2P interface name (e.g., "p2p-wlan0-0")

        Raises:
            WiFiDirectError: If P2P group creation fails
        """
        if self.is_group_owner:
            log.warning("Already a Group Owner")
            return self.p2p_interface or ""

        # Set device name
        short_id = self._get_device_short_id()
        full_name = f"DIRECT-{device_name}-{short_id}"

        try:
            self._run_wpa_cli(f"set device_name {full_name}")

            # Create autonomous GO
            result = self._run_wpa_cli("p2p_group_add")

            if "FAIL" in result:
                raise WiFiDirectError(f"Failed to create P2P group: {result}")

            # Wait for interface to appear
            self.p2p_interface = self._wait_for_p2p_interface()

            if not self.p2p_interface:
                raise WiFiDirectError("P2P interface did not appear")

            self.is_group_owner = True

            # Configure IP on P2P interface
            self._configure_go_network()

            log.info(f"Started as Group Owner on {self.p2p_interface}")
            return self.p2p_interface

        except subprocess.TimeoutExpired:
            raise WiFiDirectError("P2P group creation timed out")

    def stop_group_owner(self) -> None:
        """Stop P2P group and cleanup."""
        if not self.is_group_owner or not self.p2p_interface:
            return

        try:
            # Stop DHCP server
            self._stop_dnsmasq()

            # Remove P2P group
            self._run_wpa_cli(f"p2p_group_remove {self.p2p_interface}")

            log.info(f"Stopped Group Owner, removed {self.p2p_interface}")

        except Exception as e:
            log.error(f"Error stopping GO: {e}")

        finally:
            self.p2p_interface = None
            self.is_group_owner = False

    def find_peers(self, timeout: int = 10) -> list[P2PPeer]:
        """Scan for WiFi Direct groups.

        Args:
            timeout: Scan duration in seconds

        Returns:
            List of discovered P2P devices/groups
        """
        try:
            # Start P2P find
            result = self._run_wpa_cli("p2p_find")

            if "FAIL" in result:
                log.warning(f"P2P find failed: {result}")
                return []

            # Wait for discovery
            time.sleep(timeout)

            # Stop find
            self._run_wpa_cli("p2p_stop_find")

            # Get peers
            peers_output = self._run_wpa_cli("p2p_peers")
            peer_addresses = [addr.strip() for addr in peers_output.strip().split("\n") if addr.strip()]

            peers = []
            for addr in peer_addresses:
                peer_info = self._get_peer_info(addr)
                if peer_info:
                    peers.append(peer_info)

            log.info(f"Found {len(peers)} P2P peer(s)")
            return peers

        except Exception as e:
            log.error(f"P2P find error: {e}")
            return []

    def connect_to_group(self, peer_address: str, method: str = "pbc") -> bool:
        """Connect to a P2P Group Owner.

        Args:
            peer_address: MAC address of GO
            method: "pbc" (push button) or "pin"

        Returns:
            True if connected successfully
        """
        try:
            cmd = f"p2p_connect {peer_address} {method} join"
            result = self._run_wpa_cli(cmd)

            if "FAIL" in result:
                log.error(f"P2P connect failed: {result}")
                return False

            # Wait for connection and IP
            self.p2p_interface = self._wait_for_p2p_interface()

            if not self.p2p_interface:
                log.error("P2P interface did not appear after connect")
                return False

            # Wait for DHCP
            if not self._wait_for_dhcp_ip():
                log.error("Failed to get IP from DHCP")
                return False

            log.info(f"Connected to {peer_address} on {self.p2p_interface}")
            return True

        except Exception as e:
            log.error(f"P2P connect error: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from P2P group."""
        if self.p2p_interface:
            try:
                self._run_wpa_cli(f"p2p_group_remove {self.p2p_interface}")
            except Exception as e:
                log.error(f"Disconnect error: {e}")
            finally:
                self.p2p_interface = None

    def get_p2p_ip(self) -> str | None:
        """Get IP address on P2P interface.

        Returns:
            IPv4 address or None
        """
        if not self.p2p_interface:
            return None

        try:
            result = subprocess.run(
                ["ip", "-4", "addr", "show", self.p2p_interface],
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Parse IP from output
            match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)

        except Exception as e:
            log.error(f"Failed to get P2P IP: {e}")

        return None

    def get_group_name(self) -> str | None:
        """Get the current group name if acting as GO.

        Returns:
            Group name or None
        """
        if not self.is_group_owner:
            return None

        try:
            result = self._run_wpa_cli("status")
            for line in result.split("\n"):
                if line.startswith("ssid="):
                    return line.split("=", 1)[1]
        except Exception:
            pass

        return None

    def _run_wpa_cli(self, command: str, timeout: int = 10) -> str:
        """Run wpa_cli command.

        Args:
            command: Command to run (without 'wpa_cli -i interface')
            timeout: Command timeout in seconds

        Returns:
            Command output

        Raises:
            subprocess.TimeoutExpired: If command times out
        """
        full_cmd = ["wpa_cli", "-i", self.interface, *command.split()]

        log.debug(f"Running: {' '.join(full_cmd)}")

        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)

        output = result.stdout.strip()
        if result.returncode != 0:
            log.warning(f"wpa_cli returned {result.returncode}: {result.stderr}")

        return output

    def _wait_for_p2p_interface(self, timeout: int = 15) -> str | None:
        """Wait for P2P interface to appear.

        Returns:
            Interface name or None if timeout
        """
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = subprocess.run(["ip", "link", "show"], capture_output=True, text=True, timeout=5)

                # Look for p2p-wlan0-X pattern
                match = re.search(r"(p2p-\w+-\d+)", result.stdout)
                if match:
                    return match.group(1)

            except Exception:
                pass

            time.sleep(0.5)

        return None

    def _configure_go_network(self) -> None:
        """Configure network for Group Owner mode."""
        if not self.p2p_interface:
            return

        try:
            # Assign static IP
            subprocess.run(
                ["ip", "addr", "add", "192.168.49.1/24", "dev", self.p2p_interface],
                timeout=5,
                check=True,
            )

            # Bring interface up
            subprocess.run(
                ["ip", "link", "set", self.p2p_interface, "up"],
                timeout=5,
                check=True,
            )

            # Start DHCP server
            self._start_dnsmasq()

            log.info(f"Configured GO network on {self.p2p_interface}")

        except Exception as e:
            log.error(f"Failed to configure GO network: {e}")

    def _start_dnsmasq(self) -> None:
        """Start dnsmasq DHCP server for P2P clients."""
        if not self.p2p_interface:
            return

        try:
            cmd = [
                "dnsmasq",
                f"--interface={self.p2p_interface}",
                "--dhcp-range=192.168.49.10,192.168.49.50,24h",
                "--bind-interfaces",
                "--no-daemon",
            ]

            self._dnsmasq_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            log.info("Started dnsmasq DHCP server")

        except Exception as e:
            log.error(f"Failed to start dnsmasq: {e}")

    def _stop_dnsmasq(self) -> None:
        """Stop dnsmasq DHCP server."""
        if self._dnsmasq_process:
            try:
                self._dnsmasq_process.terminate()
                self._dnsmasq_process.wait(timeout=5)
            except Exception:
                self._dnsmasq_process.kill()

            self._dnsmasq_process = None
            log.info("Stopped dnsmasq")

    def _wait_for_dhcp_ip(self, timeout: int = 15) -> bool:
        """Wait for DHCP to assign IP on P2P interface.

        Returns:
            True if IP obtained
        """
        if not self.p2p_interface:
            return False

        # Request DHCP
        try:
            subprocess.Popen(
                ["dhclient", self.p2p_interface],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log.error(f"Failed to start dhclient: {e}")
            return False

        # Wait for IP
        start = time.time()
        while time.time() - start < timeout:
            if self.get_p2p_ip():
                return True
            time.sleep(0.5)

        return False

    def _get_peer_info(self, address: str) -> P2PPeer | None:
        """Get info about a specific peer.

        Args:
            address: MAC address of peer

        Returns:
            P2PPeer or None
        """
        try:
            result = self._run_wpa_cli(f"p2p_peer {address}")

            name = "Unknown"
            is_go = False

            for line in result.split("\n"):
                if line.startswith("device_name="):
                    name = line.split("=", 1)[1]
                elif "group_owner" in line.lower():
                    is_go = True

            return P2PPeer(address=address, name=name, is_group_owner=is_go)

        except Exception as e:
            log.error(f"Failed to get peer info for {address}: {e}")
            return None

    def _get_device_short_id(self) -> str:
        """Generate short device ID from MAC address.

        Returns:
            4-character hex ID
        """
        try:
            result = subprocess.run(
                ["cat", f"/sys/class/net/{self.interface}/address"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            mac = result.stdout.strip().replace(":", "")
            return mac[-4:].upper()
        except Exception:
            import random

            return f"{random.randint(0, 0xFFFF):04X}"
