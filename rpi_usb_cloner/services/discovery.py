"""mDNS service discovery for peer-to-peer image transfers.

Uses python-zeroconf to publish and browse for other Pi Cloner devices
on the local network.
"""

from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass
from typing import Callable

from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

from rpi_usb_cloner.logging import get_logger

log = get_logger(source=__name__)

# Service type for Pi USB Cloner transfers
SERVICE_TYPE = "_rpi-cloner._tcp.local."
SERVICE_PORT = 8765


@dataclass
class PeerDevice:
    """Represents a discovered peer device."""

    hostname: str
    address: str  # IPv4 address
    port: int
    device_id: str  # Unique per-boot identifier
    txt_records: dict[str, str]  # Additional metadata


class DiscoveryService:
    """Manages mDNS service discovery for peer transfers."""

    def __init__(self, port: int = SERVICE_PORT):
        """Initialize discovery service.

        Args:
            port: Port number for transfer server (default 8765)
        """
        self.port = port
        self.zeroconf: Zeroconf | None = None
        self.service_info: ServiceInfo | None = None
        self.device_id = str(uuid.uuid4())[:8]  # Short unique ID per session
        self._discovered_peers: dict[str, PeerDevice] = {}
        self._browser: ServiceBrowser | None = None

    def start_publishing(self, pin_callback: Callable[[], str]) -> None:
        """Publish this device as available for transfers.

        Args:
            pin_callback: Function to generate fresh PIN on demand

        Publishes service with:
            - Service name: hostname
            - Service type: _rpi-cloner._tcp.local.
            - TXT records: device_id, version, hostname
        """
        if self.zeroconf is not None:
            log.warning("Discovery already publishing")
            return

        hostname = socket.gethostname()
        local_ip = self._get_local_ip()

        if not local_ip:
            raise RuntimeError("Could not determine local IP address")

        # Create service info
        server_name = f"{hostname}.{SERVICE_TYPE}"

        # TXT records for metadata
        txt_records = {
            "device_id": self.device_id,
            "version": "1.0",
            "hostname": hostname,
        }

        self.service_info = ServiceInfo(
            SERVICE_TYPE,
            server_name,
            addresses=[socket.inet_aton(local_ip)],
            port=self.port,
            properties=txt_records,
            server=f"{hostname}.local.",
        )

        # Start zeroconf and register
        self.zeroconf = Zeroconf()
        self.zeroconf.register_service(self.service_info)

        log.info(
            f"Published mDNS service: {server_name} at {local_ip}:{self.port} "
            f"(device_id: {self.device_id})"
        )

    def stop_publishing(self) -> None:
        """Stop advertising this device."""
        if self.zeroconf and self.service_info:
            log.info("Unpublishing mDNS service")
            self.zeroconf.unregister_service(self.service_info)
            self.zeroconf.close()
            self.zeroconf = None
            self.service_info = None

    def browse_peers(
        self,
        timeout_seconds: float = 5.0,
        on_update: Callable[[list[PeerDevice]], None] | None = None,
    ) -> list[PeerDevice]:
        """Find other Pi Cloners on network.

        Args:
            timeout_seconds: How long to scan for devices
            on_update: Optional callback called when devices list changes

        Returns:
            List of discovered devices (filtered to exclude self)
        """
        if self.zeroconf is None:
            self.zeroconf = Zeroconf()

        self._discovered_peers.clear()
        self._on_update_callback = on_update

        def on_service_state_change(
            zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange
        ) -> None:
            """Handler for service discovery events."""
            if state_change == ServiceStateChange.Added:
                info = zeroconf.get_service_info(service_type, name)
                if info:
                    peer = self._parse_service_info(info)
                    if peer and peer.device_id != self.device_id:
                        # Filter out self
                        self._discovered_peers[name] = peer
                        log.info(f"Discovered peer: {peer.hostname} at {peer.address}")
                        
                        if self._on_update_callback:
                            self._on_update_callback(list(self._discovered_peers.values()))

            elif state_change == ServiceStateChange.Removed:
                if name in self._discovered_peers:
                    removed = self._discovered_peers.pop(name)
                    log.info(f"Peer removed: {removed.hostname}")
                    
                    if self._on_update_callback:
                        self._on_update_callback(list(self._discovered_peers.values()))

        # Start browsing
        self._browser = ServiceBrowser(self.zeroconf, SERVICE_TYPE, handlers=[on_service_state_change])

        # Wait for discovery
        import time

        time.sleep(timeout_seconds)

        # Stop browsing
        self._browser.cancel()
        self._browser = None

        peers = list(self._discovered_peers.values())
        log.info(f"Discovery complete. Found {len(peers)} peer(s)")
        return peers

    def shutdown(self) -> None:
        """Clean up all resources."""
        self.stop_publishing()
        if self._browser:
            self._browser.cancel()
            self._browser = None
        if self.zeroconf:
            self.zeroconf.close()
            self.zeroconf = None

    def _parse_service_info(self, info: ServiceInfo) -> PeerDevice | None:
        """Parse ServiceInfo into PeerDevice.

        Args:
            info: ServiceInfo from zeroconf

        Returns:
            PeerDevice or None if parsing failed
        """
        try:
            # Get IPv4 address
            if not info.addresses:
                log.warning(f"Service {info.name} has no addresses")
                return None

            address = socket.inet_ntoa(info.addresses[0])

            # Parse TXT records
            txt_records = {}
            if info.properties:
                for key, value in info.properties.items():
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")
                    if isinstance(value, bytes):
                        value = value.decode("utf-8")
                    txt_records[key] = value

            device_id = txt_records.get("device_id", "unknown")
            hostname = txt_records.get("hostname", info.server.rstrip("."))

            return PeerDevice(
                hostname=hostname,
                address=address,
                port=info.port,
                device_id=device_id,
                txt_records=txt_records,
            )

        except Exception as e:
            log.error(f"Failed to parse service info: {e}")
            return None

    def _get_local_ip(self) -> str | None:
        """Determine local IP address for publishing.

        Returns:
            IPv4 address string, or None if unavailable
        """
        try:
            # Try to get IP by connecting to public DNS (doesn't actually send data)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0)
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
            sock.close()
            return local_ip
        except Exception:
            # Fallback: try to get from hostname
            try:
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
                if local_ip and not local_ip.startswith("127."):
                    return local_ip
            except Exception:
                pass

        log.error("Could not determine local IP address")
        return None
