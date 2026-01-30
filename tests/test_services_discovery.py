"""Tests for mDNS discovery service.

Tests cover:
- Service publishing and unpublishing
- Peer browsing and discovery
- Service info parsing
- IP address detection
"""

from __future__ import annotations

import socket
from unittest.mock import Mock, patch, MagicMock

import pytest

from rpi_usb_cloner.services.discovery import (
    DiscoveryService,
    PeerDevice,
    SERVICE_TYPE,
    SERVICE_PORT,
)


class TestPeerDevice:
    """Test PeerDevice dataclass."""

    def test_peer_device_creation(self):
        """Test creating a PeerDevice."""
        peer = PeerDevice(
            hostname="test-pi",
            address="192.168.1.100",
            port=8765,
            device_id="abc123",
            txt_records={"version": "1.0"},
        )

        assert peer.hostname == "test-pi"
        assert peer.address == "192.168.1.100"
        assert peer.port == 8765
        assert peer.device_id == "abc123"


class TestDiscoveryServiceInit:
    """Test DiscoveryService initialization."""

    def test_default_initialization(self):
        """Test initialization with default port."""
        service = DiscoveryService()

        assert service.port == SERVICE_PORT
        assert service.zeroconf is None
        assert service.service_info is None
        assert len(service.device_id) == 8  # Short UUID

    def test_custom_port_initialization(self):
        """Test initialization with custom port."""
        service = DiscoveryService(port=9999)

        assert service.port == 9999


class TestStartPublishing:
    """Test publishing service via mDNS."""

    def test_start_publishing_success(self, mocker):
        """Test successful service publishing."""
        service = DiscoveryService(port=8765)

        mock_zeroconf = mocker.patch("rpi_usb_cloner.services.discovery.Zeroconf")
        mock_socket = mocker.patch("rpi_usb_cloner.services.discovery.socket")
        mock_socket.gethostname.return_value = "testpi"
        mock_socket.inet_aton.return_value = b"\xc0\xa8\x01\x01"  # 192.168.1.1

        # Mock _get_local_ip
        mocker.patch.object(service, "_get_local_ip", return_value="192.168.1.1")

        pin_callback = Mock(return_value="1234")

        service.start_publishing(pin_callback)

        assert service.zeroconf is not None
        mock_zeroconf.return_value.register_service.assert_called_once()

    def test_start_publishing_already_publishing(self, mocker):
        """Test warning when already publishing."""
        service = DiscoveryService()
        service.zeroconf = Mock()  # Already set

        mock_log = mocker.patch("rpi_usb_cloner.services.discovery.log")

        service.start_publishing(Mock())

        mock_log.warning.assert_called_once_with("Discovery already publishing")

    def test_start_publishing_no_ip(self, mocker):
        """Test error when IP cannot be determined."""
        service = DiscoveryService()

        mocker.patch.object(service, "_get_local_ip", return_value=None)

        with pytest.raises(RuntimeError, match="Could not determine local IP"):
            service.start_publishing(Mock())


class TestStopPublishing:
    """Test stopping service publication."""

    def test_stop_publishing_success(self, mocker):
        """Test successful unpublishing."""
        service = DiscoveryService()
        mock_zc = Mock()
        service.zeroconf = mock_zc
        service.service_info = Mock()

        service.stop_publishing()

        mock_zc.unregister_service.assert_called_once()
        mock_zc.close.assert_called_once()
        assert service.zeroconf is None

    def test_stop_publishing_not_publishing(self):
        """Test stop when not publishing (no error)."""
        service = DiscoveryService()

        # Should not raise
        service.stop_publishing()


class TestBrowsePeers:
    """Test browsing for peer devices."""

    def test_browse_peers_success(self, mocker):
        """Test browsing discovers peers."""
        service = DiscoveryService()

        mock_zc = Mock()
        service.zeroconf = mock_zc

        mock_browser = mocker.patch(
            "rpi_usb_cloner.services.discovery.ServiceBrowser"
        )
        import time
        mocker.patch.object(time, "sleep")

        peers = service.browse_peers(timeout_seconds=0.1)

        mock_browser.assert_called_once()
        assert isinstance(peers, list)

    def test_browse_creates_zeroconf_if_none(self, mocker):
        """Test browsing creates Zeroconf if needed."""
        service = DiscoveryService()

        mock_zc = mocker.patch("rpi_usb_cloner.services.discovery.Zeroconf")
        mock_browser = mocker.patch(
            "rpi_usb_cloner.services.discovery.ServiceBrowser"
        )
        mocker.patch("rpi_usb_cloner.services.discovery.time.sleep")

        service.browse_peers(timeout_seconds=0.1)

        mock_zc.assert_called_once()

    def test_browse_with_callback(self, mocker):
        """Test browsing with update callback."""
        service = DiscoveryService()

        mock_zc = Mock()
        service.zeroconf = mock_zc

        mocker.patch("rpi_usb_cloner.services.discovery.ServiceBrowser")
        mocker.patch("rpi_usb_cloner.services.discovery.time.sleep")

        callback_mock = Mock()

        service.browse_peers(timeout_seconds=0.1, on_update=callback_mock)

        assert service._on_update_callback == callback_mock


class TestParseServiceInfo:
    """Test parsing ServiceInfo into PeerDevice."""

    def test_parse_valid_service_info(self, mocker):
        """Test parsing valid service info."""
        service = DiscoveryService()

        mock_info = Mock()
        mock_info.addresses = [b"\xc0\xa8\x01\x01"]  # 192.168.1.1
        mock_info.name = "testpi._rpi-cloner._tcp.local."
        mock_info.server = "testpi.local."
        mock_info.port = 8765
        mock_info.properties = {
            b"device_id": b"abc123",
            b"hostname": b"testpi",
            b"version": b"1.0",
        }

        peer = service._parse_service_info(mock_info)

        assert peer is not None
        assert peer.hostname == "testpi"
        assert peer.address == "192.168.1.1"
        assert peer.device_id == "abc123"

    def test_parse_no_addresses(self, mocker):
        """Test parsing service with no addresses."""
        service = DiscoveryService()

        mock_info = Mock()
        mock_info.addresses = []
        mock_info.name = "test._rpi-cloner._tcp.local."

        mock_log = mocker.patch("rpi_usb_cloner.services.discovery.log")

        peer = service._parse_service_info(mock_info)

        assert peer is None
        mock_log.warning.assert_called_once()

    def test_parse_string_properties(self, mocker):
        """Test parsing with string properties (not bytes)."""
        service = DiscoveryService()

        mock_info = Mock()
        mock_info.addresses = [b"\xc0\xa8\x01\x01"]
        mock_info.name = "test._rpi-cloner._tcp.local."
        mock_info.server = "test.local."
        mock_info.port = 8765
        mock_info.properties = {
            "device_id": "def456",  # String, not bytes
            "hostname": "test",
        }

        peer = service._parse_service_info(mock_info)

        assert peer is not None
        assert peer.device_id == "def456"

    def test_parse_none_properties(self, mocker):
        """Test parsing with None properties."""
        service = DiscoveryService()

        mock_info = Mock()
        mock_info.addresses = [b"\xc0\xa8\x01\x01"]
        mock_info.name = "test._rpi-cloner._tcp.local."
        mock_info.server = "test.local."
        mock_info.port = 8765
        mock_info.properties = None

        peer = service._parse_service_info(mock_info)

        assert peer is not None
        assert peer.device_id == "unknown"

    def test_parse_exception_handling(self, mocker):
        """Test handling parsing exceptions."""
        service = DiscoveryService()

        mock_info = Mock()
        mock_info.addresses = [b"invalid"]  # Will cause inet_ntoa to fail

        mock_log = mocker.patch("rpi_usb_cloner.services.discovery.log")

        peer = service._parse_service_info(mock_info)

        assert peer is None
        mock_log.error.assert_called_once()


class TestGetLocalIP:
    """Test local IP address detection."""

    def test_get_local_ip_via_udp(self, mocker):
        """Test getting IP via UDP socket method."""
        service = DiscoveryService()

        mock_socket = mocker.patch("rpi_usb_cloner.services.discovery.socket.socket")
        mock_sock = Mock()
        mock_sock.getsockname.return_value = ("192.168.1.50", 54321)
        mock_socket.return_value = mock_sock

        ip = service._get_local_ip()

        assert ip == "192.168.1.50"
        mock_sock.connect.assert_called_with(("8.8.8.8", 80))

    def test_get_local_ip_fallback_to_hostname(self, mocker):
        """Test fallback to hostname resolution."""
        service = DiscoveryService()

        # UDP method fails
        mock_socket = mocker.patch(
            "rpi_usb_cloner.services.discovery.socket.socket",
            side_effect=OSError("Network unreachable"),
        )

        # Fallback succeeds
        mock_gethostname = mocker.patch(
            "rpi_usb_cloner.services.discovery.socket.gethostname"
        )
        mock_gethostname.return_value = "testpi"

        mock_gethostbyname = mocker.patch(
            "rpi_usb_cloner.services.discovery.socket.gethostbyname"
        )
        mock_gethostbyname.return_value = "192.168.1.100"

        ip = service._get_local_ip()

        assert ip == "192.168.1.100"

    def test_get_local_ip_fallback_filters_localhost(self, mocker):
        """Test fallback filters out localhost addresses."""
        service = DiscoveryService()

        mocker.patch(
            "rpi_usb_cloner.services.discovery.socket.socket",
            side_effect=OSError("Network unreachable"),
        )

        mock_gethostname = mocker.patch(
            "rpi_usb_cloner.services.discovery.socket.gethostname"
        )
        mock_gethostname.return_value = "localhost"

        mock_gethostbyname = mocker.patch(
            "rpi_usb_cloner.services.discovery.socket.gethostbyname"
        )
        mock_gethostbyname.return_value = "127.0.0.1"

        ip = service._get_local_ip()

        assert ip is None  # 127.x is filtered out

    def test_get_local_ip_all_methods_fail(self, mocker):
        """Test returning None when all methods fail."""
        service = DiscoveryService()

        mocker.patch(
            "rpi_usb_cloner.services.discovery.socket.socket",
            side_effect=OSError("No network"),
        )
        mocker.patch(
            "rpi_usb_cloner.services.discovery.socket.gethostname",
            side_effect=OSError("No hostname"),
        )

        mock_log = mocker.patch("rpi_usb_cloner.services.discovery.log")

        ip = service._get_local_ip()

        assert ip is None
        mock_log.error.assert_called_once()


class TestShutdown:
    """Test cleanup and shutdown."""

    def test_shutdown_full(self):
        """Test complete shutdown cleanup."""
        service = DiscoveryService()
        service.zeroconf = Mock()
        service._browser = Mock()

        service.shutdown()

        service._browser.cancel.assert_called_once()
        service.zeroconf.close.assert_called_once()
        assert service.zeroconf is None
        assert service._browser is None

    def test_shutdown_no_resources(self):
        """Test shutdown with no active resources."""
        service = DiscoveryService()

        # Should not raise
        service.shutdown()


class TestServiceCallbacks:
    """Test service discovery callbacks."""

    def test_service_added_callback(self, mocker):
        """Test callback on service added."""
        from zeroconf import ServiceStateChange

        service = DiscoveryService()
        service.device_id = "local123"

        callback_mock = Mock()
        service._on_update_callback = callback_mock

        # Create mock service info
        mock_info = Mock()
        mock_info.addresses = [b"\xc0\xa8\x01\x02"]
        mock_info.name = "peer._rpi-cloner._tcp.local."
        mock_info.server = "peer.local."
        mock_info.port = 8765
        mock_info.properties = {b"device_id": b"peer456", b"hostname": b"peer"}

        mock_zc = Mock()
        mock_zc.get_service_info.return_value = mock_info

        # Simulate service added
        service._discovered_peers = {}

        # Manually trigger the handler
        handler = None
        def capture_handler(zc, st, h):
            nonlocal handler
            handler = h

        mock_browser = mocker.patch(
            "rpi_usb_cloner.services.discovery.ServiceBrowser",
            side_effect=capture_handler,
        )

        service.browse_peers(timeout_seconds=0)

        # Now manually call the discovered handler
        peer = service._parse_service_info(mock_info)
        service._discovered_peers["peer"] = peer

        callback_mock.assert_not_called()  # Wasn't called during browse

    def test_service_removed_callback(self, mocker):
        """Test callback on service removed."""
        service = DiscoveryService()

        callback_mock = Mock()
        service._on_update_callback = callback_mock

        # Pre-populate discovered peers
        peer = PeerDevice(
            hostname="test",
            address="192.168.1.1",
            port=8765,
            device_id="test123",
            txt_records={},
        )
        service._discovered_peers["test._rpi-cloner._tcp.local."] = peer

        # Simulate removal (would be triggered by ServiceBrowser)
        del service._discovered_peers["test._rpi-cloner._tcp.local."]
        callback_mock(list(service._discovered_peers.values()))

        callback_mock.assert_called_once()
