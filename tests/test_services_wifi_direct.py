"""Tests for WiFi Direct (P2P) service.

Tests cover:
- P2P support detection
- Group Owner mode
- Peer discovery
- Connection handling
"""

from __future__ import annotations

from unittest.mock import Mock, patch, call
import subprocess

import pytest

from rpi_usb_cloner.services.wifi_direct import (
    WiFiDirectService,
    P2PPeer,
    WiFiDirectError,
)


class TestWiFiDirectServiceInit:
    """Test WiFiDirectService initialization."""

    def test_default_initialization(self):
        """Test initialization with defaults."""
        service = WiFiDirectService()

        assert service.interface == "wlan0"
        assert service.p2p_interface is None
        assert service.is_group_owner is False
        assert service._dnsmasq_process is None

    def test_custom_interface_initialization(self):
        """Test initialization with custom interface."""
        service = WiFiDirectService(interface="wlan1")

        assert service.interface == "wlan1"


class TestIsP2PSupported:
    """Test P2P support detection."""

    def test_p2p_supported(self, mocker):
        """Test detection when P2P is supported."""
        service = WiFiDirectService()

        mocker.patch.object(
            service,
            "_run_wpa_cli",
            return_value="OK",
        )

        assert service.is_p2p_supported() is True

    def test_p2p_not_supported(self, mocker):
        """Test detection when P2P is not supported."""
        service = WiFiDirectService()

        mocker.patch.object(
            service,
            "_run_wpa_cli",
            return_value="FAIL",
        )

        assert service.is_p2p_supported() is False

    def test_p2p_check_exception(self, mocker):
        """Test handling exception during check."""
        service = WiFiDirectService()

        mocker.patch.object(
            service,
            "_run_wpa_cli",
            side_effect=subprocess.TimeoutExpired("wpa_cli", 10),
        )

        assert service.is_p2p_supported() is False


class TestStartGroupOwner:
    """Test starting Group Owner mode."""

    def test_start_group_owner_success(self, mocker):
        """Test successful GO creation."""
        service = WiFiDirectService()

        mocker.patch.object(service, "_run_wpa_cli", return_value="OK")
        mocker.patch.object(
            service,
            "_wait_for_p2p_interface",
            return_value="p2p-wlan0-0",
        )
        mocker.patch.object(service, "_configure_go_network")
        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.run",
            return_value=Mock(stdout="00:11:22:33:44:55"),
        )

        result = service.start_group_owner()

        assert result == "p2p-wlan0-0"
        assert service.is_group_owner is True
        assert service.p2p_interface == "p2p-wlan0-0"

    def test_start_group_owner_already_go(self, mocker):
        """Test warning when already a Group Owner."""
        service = WiFiDirectService()
        service.is_group_owner = True
        service.p2p_interface = "p2p-wlan0-0"

        mock_log = mocker.patch("rpi_usb_cloner.services.wifi_direct.log")

        result = service.start_group_owner()

        assert result == "p2p-wlan0-0"
        mock_log.warning.assert_called_once()

    def test_start_group_owner_failure(self, mocker):
        """Test handling GO creation failure."""
        service = WiFiDirectService()

        mocker.patch.object(service, "_run_wpa_cli", return_value="FAIL")

        with pytest.raises(WiFiDirectError, match="Failed to create P2P group"):
            service.start_group_owner()

    def test_start_group_owner_interface_timeout(self, mocker):
        """Test error when interface doesn't appear."""
        service = WiFiDirectService()

        mocker.patch.object(service, "_run_wpa_cli", return_value="OK")
        mocker.patch.object(
            service,
            "_wait_for_p2p_interface",
            return_value=None,
        )

        with pytest.raises(WiFiDirectError, match="P2P interface did not appear"):
            service.start_group_owner()

    def test_start_group_owner_timeout_exception(self, mocker):
        """Test handling timeout exception."""
        service = WiFiDirectService()

        mocker.patch.object(
            service,
            "_run_wpa_cli",
            side_effect=subprocess.TimeoutExpired("wpa_cli", 10),
        )

        with pytest.raises(WiFiDirectError, match="timed out"):
            service.start_group_owner()


class TestStopGroupOwner:
    """Test stopping Group Owner mode."""

    def test_stop_group_owner_success(self, mocker):
        """Test successful GO stop."""
        service = WiFiDirectService()
        service.is_group_owner = True
        service.p2p_interface = "p2p-wlan0-0"

        mocker.patch.object(service, "_stop_dnsmasq")
        mocker.patch.object(service, "_run_wpa_cli", return_value="OK")

        service.stop_group_owner()

        assert service.is_group_owner is False
        assert service.p2p_interface is None

    def test_stop_group_owner_not_go(self, mocker):
        """Test no-op when not a GO."""
        service = WiFiDirectService()

        mock_run = mocker.patch.object(service, "_run_wpa_cli")

        service.stop_group_owner()

        mock_run.assert_not_called()

    def test_stop_group_owner_error_handling(self, mocker):
        """Test error handling during stop."""
        service = WiFiDirectService()
        service.is_group_owner = True
        service.p2p_interface = "p2p-wlan0-0"

        mocker.patch.object(service, "_stop_dnsmasq")
        mocker.patch.object(
            service,
            "_run_wpa_cli",
            side_effect=Exception("Command failed"),
        )
        mock_log = mocker.patch("rpi_usb_cloner.services.wifi_direct.log")

        service.stop_group_owner()

        mock_log.error.assert_called_once()
        assert service.is_group_owner is False  # Still resets state


class TestFindPeers:
    """Test peer discovery."""

    def test_find_peers_success(self, mocker):
        """Test successful peer discovery."""
        service = WiFiDirectService()

        mocker.patch.object(service, "_run_wpa_cli", side_effect=[
            "OK",  # p2p_find
            "OK",  # p2p_stop_find
            "aa:bb:cc:dd:ee:ff\n11:22:33:44:55:66",  # p2p_peers
        ])

        mock_peer_info = mocker.patch.object(
            service,
            "_get_peer_info",
            side_effect=[
                P2PPeer(address="aa:bb:cc:dd:ee:ff", name="Device1"),
                P2PPeer(address="11:22:33:44:55:66", name="Device2"),
            ],
        )

        peers = service.find_peers(timeout=0)

        assert len(peers) == 2
        assert peers[0].name == "Device1"

    def test_find_peers_failure(self, mocker):
        """Test handling find failure."""
        service = WiFiDirectService()

        mocker.patch.object(service, "_run_wpa_cli", return_value="FAIL")
        mock_log = mocker.patch("rpi_usb_cloner.services.wifi_direct.log")

        peers = service.find_peers(timeout=0)

        assert peers == []
        mock_log.warning.assert_called_once()

    def test_find_peers_exception(self, mocker):
        """Test handling exception during find."""
        service = WiFiDirectService()

        mocker.patch.object(
            service,
            "_run_wpa_cli",
            side_effect=Exception("Command failed"),
        )
        mock_log = mocker.patch("rpi_usb_cloner.services.wifi_direct.log")

        peers = service.find_peers(timeout=0)

        assert peers == []
        mock_log.error.assert_called_once()

    def test_find_peers_no_peers(self, mocker):
        """Test finding no peers."""
        service = WiFiDirectService()

        mocker.patch.object(service, "_run_wpa_cli", side_effect=[
            "OK",
            "OK",
            "",  # Empty peers list
        ])

        peers = service.find_peers(timeout=0)

        assert peers == []


class TestConnectToGroup:
    """Test connecting to a P2P group."""

    def test_connect_success(self, mocker):
        """Test successful connection."""
        service = WiFiDirectService()

        mocker.patch.object(service, "_run_wpa_cli", return_value="OK")
        mocker.patch.object(
            service,
            "_wait_for_p2p_interface",
            return_value="p2p-wlan0-0",
        )
        mocker.patch.object(service, "_wait_for_dhcp_ip", return_value=True)

        result = service.connect_to_group("aa:bb:cc:dd:ee:ff")

        assert result is True
        assert service.p2p_interface == "p2p-wlan0-0"

    def test_connect_failure(self, mocker):
        """Test connection failure."""
        service = WiFiDirectService()

        mocker.patch.object(service, "_run_wpa_cli", return_value="FAIL")

        result = service.connect_to_group("aa:bb:cc:dd:ee:ff")

        assert result is False

    def test_connect_interface_timeout(self, mocker):
        """Test failure when interface doesn't appear."""
        service = WiFiDirectService()

        mocker.patch.object(service, "_run_wpa_cli", return_value="OK")
        mocker.patch.object(
            service,
            "_wait_for_p2p_interface",
            return_value=None,
        )

        result = service.connect_to_group("aa:bb:cc:dd:ee:ff")

        assert result is False

    def test_connect_dhcp_timeout(self, mocker):
        """Test failure when DHCP fails."""
        service = WiFiDirectService()

        mocker.patch.object(service, "_run_wpa_cli", return_value="OK")
        mocker.patch.object(
            service,
            "_wait_for_p2p_interface",
            return_value="p2p-wlan0-0",
        )
        mocker.patch.object(service, "_wait_for_dhcp_ip", return_value=False)

        result = service.connect_to_group("aa:bb:cc:dd:ee:ff")

        assert result is False


class TestDisconnect:
    """Test disconnection."""

    def test_disconnect_success(self, mocker):
        """Test successful disconnect."""
        service = WiFiDirectService()
        service.p2p_interface = "p2p-wlan0-0"

        mocker.patch.object(service, "_run_wpa_cli", return_value="OK")

        service.disconnect()

        assert service.p2p_interface is None

    def test_disconnect_no_interface(self, mocker):
        """Test no-op when no interface."""
        service = WiFiDirectService()

        mock_run = mocker.patch.object(service, "_run_wpa_cli")

        service.disconnect()

        mock_run.assert_not_called()

    def test_disconnect_error(self, mocker):
        """Test error handling during disconnect."""
        service = WiFiDirectService()
        service.p2p_interface = "p2p-wlan0-0"

        mocker.patch.object(
            service,
            "_run_wpa_cli",
            side_effect=Exception("Command failed"),
        )
        mock_log = mocker.patch("rpi_usb_cloner.services.wifi_direct.log")

        service.disconnect()

        mock_log.error.assert_called_once()
        assert service.p2p_interface is None  # Still resets


class TestGetP2PIP:
    """Test getting P2P IP address."""

    def test_get_ip_success(self, mocker):
        """Test successful IP retrieval."""
        service = WiFiDirectService()
        service.p2p_interface = "p2p-wlan0-0"

        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.run",
            return_value=Mock(
                stdout="inet 192.168.49.1/24 brd 192.168.49.255",
                returncode=0,
            ),
        )

        ip = service.get_p2p_ip()

        assert ip == "192.168.49.1"

    def test_get_ip_no_match(self, mocker):
        """Test no IP found in output."""
        service = WiFiDirectService()
        service.p2p_interface = "p2p-wlan0-0"

        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.run",
            return_value=Mock(stdout="no ip here", returncode=0),
        )

        ip = service.get_p2p_ip()

        assert ip is None

    def test_get_ip_no_interface(self):
        """Test None when no P2P interface."""
        service = WiFiDirectService()

        ip = service.get_p2p_ip()

        assert ip is None

    def test_get_ip_exception(self, mocker):
        """Test handling exception."""
        service = WiFiDirectService()
        service.p2p_interface = "p2p-wlan0-0"

        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.run",
            side_effect=Exception("Command failed"),
        )
        mock_log = mocker.patch("rpi_usb_cloner.services.wifi_direct.log")

        ip = service.get_p2p_ip()

        assert ip is None
        mock_log.error.assert_called_once()


class TestGetGroupName:
    """Test getting group name."""

    def test_get_group_name_success(self, mocker):
        """Test successful group name retrieval."""
        service = WiFiDirectService()
        service.is_group_owner = True

        mocker.patch.object(
            service,
            "_run_wpa_cli",
            return_value="wpa_state=COMPLETED\nssid=DIRECT-RpiCloner-1234",
        )

        name = service.get_group_name()

        assert name == "DIRECT-RpiCloner-1234"

    def test_get_group_name_not_go(self):
        """Test None when not a GO."""
        service = WiFiDirectService()
        service.is_group_owner = False

        name = service.get_group_name()

        assert name is None

    def test_get_group_name_not_found(self, mocker):
        """Test None when SSID not in status."""
        service = WiFiDirectService()
        service.is_group_owner = True

        mocker.patch.object(
            service,
            "_run_wpa_cli",
            return_value="wpa_state=COMPLETED",
        )

        name = service.get_group_name()

        assert name is None


class TestWaitForP2PInterface:
    """Test waiting for P2P interface."""

    def test_wait_interface_found(self, mocker):
        """Test interface found immediately."""
        service = WiFiDirectService()

        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.run",
            return_value=Mock(
                stdout="3: p2p-wlan0-0: <BROADCAST,MULTICAST> mtu 1500",
                returncode=0,
            ),
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.time.sleep",
        )

        iface = service._wait_for_p2p_interface(timeout=5)

        assert iface == "p2p-wlan0-0"

    def test_wait_interface_timeout(self, mocker):
        """Test timeout when interface doesn't appear."""
        service = WiFiDirectService()

        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.run",
            return_value=Mock(stdout="no p2p interface", returncode=0),
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.time.time",
            side_effect=[0, 1, 2, 20],  # Simulate time passing
        )

        iface = service._wait_for_p2p_interface(timeout=1)

        assert iface is None


class TestConfigureGONetwork:
    """Test Group Owner network configuration."""

    def test_configure_network_success(self, mocker):
        """Test successful network configuration."""
        service = WiFiDirectService()
        service.p2p_interface = "p2p-wlan0-0"

        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.run",
            return_value=Mock(returncode=0),
        )
        mocker.patch.object(service, "_start_dnsmasq")

        service._configure_go_network()

    def test_configure_network_no_interface(self, mocker):
        """Test no-op when no interface."""
        service = WiFiDirectService()
        service.p2p_interface = None

        mock_run = mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.run"
        )

        service._configure_go_network()

        mock_run.assert_not_called()


class TestDnsmasq:
    """Test dnsmasq DHCP server management."""

    def test_start_dnsmasq(self, mocker):
        """Test starting dnsmasq."""
        service = WiFiDirectService()
        service.p2p_interface = "p2p-wlan0-0"

        mock_popen = mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.Popen",
            return_value=Mock(),
        )

        service._start_dnsmasq()

        assert service._dnsmasq_process is not None
        mock_popen.assert_called_once()
        # Verify it was called with dnsmasq command
        args = mock_popen.call_args[0][0]
        assert args[0] == "dnsmasq"

    def test_stop_dnsmasq(self, mocker):
        """Test stopping dnsmasq."""
        service = WiFiDirectService()
        mock_process = Mock()
        service._dnsmasq_process = mock_process

        service._stop_dnsmasq()

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once()
        assert service._dnsmasq_process is None

    def test_stop_dnsmasq_kill_on_timeout(self, mocker):
        """Test kill when terminate times out."""
        service = WiFiDirectService()
        mock_process = Mock()
        mock_process.wait.side_effect = Exception("Timeout")
        service._dnsmasq_process = mock_process

        service._stop_dnsmasq()

        mock_process.kill.assert_called_once()

    def test_stop_dnsmasq_not_running(self):
        """Test no-op when not running."""
        service = WiFiDirectService()
        service._dnsmasq_process = None

        # Should not raise
        service._stop_dnsmasq()


class TestWaitForDHCPIP:
    """Test waiting for DHCP IP."""

    def test_wait_dhcp_success(self, mocker):
        """Test successful DHCP acquisition."""
        service = WiFiDirectService()
        service.p2p_interface = "p2p-wlan0-0"

        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.Popen",
            return_value=Mock(),
        )
        mocker.patch.object(
            service,
            "get_p2p_ip",
            side_effect=[None, None, "192.168.49.50"],  # Gets IP on 3rd try
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.time.time",
            side_effect=[0, 0.5, 1.0, 1.5],
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.time.sleep",
        )

        result = service._wait_for_dhcp_ip(timeout=5)

        assert result is True

    def test_wait_dhcp_timeout(self, mocker):
        """Test timeout waiting for DHCP."""
        service = WiFiDirectService()
        service.p2p_interface = "p2p-wlan0-0"

        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.Popen",
            return_value=Mock(),
        )
        mocker.patch.object(service, "get_p2p_ip", return_value=None)
        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.time.time",
            side_effect=[0, 1, 2, 20],  # Times out
        )

        result = service._wait_for_dhcp_ip(timeout=1)

        assert result is False

    def test_wait_dhcp_no_interface(self):
        """Test False when no interface."""
        service = WiFiDirectService()
        service.p2p_interface = None

        result = service._wait_for_dhcp_ip(timeout=5)

        assert result is False

    def test_wait_dhcp_dhclient_error(self, mocker):
        """Test error starting dhclient."""
        service = WiFiDirectService()
        service.p2p_interface = "p2p-wlan0-0"

        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.Popen",
            side_effect=Exception("Command not found"),
        )
        mock_log = mocker.patch("rpi_usb_cloner.services.wifi_direct.log")

        result = service._wait_for_dhcp_ip(timeout=5)

        assert result is False
        mock_log.error.assert_called_once()


class TestGetPeerInfo:
    """Test getting peer information."""

    def test_get_peer_info_success(self, mocker):
        """Test successful peer info retrieval."""
        service = WiFiDirectService()

        mocker.patch.object(
            service,
            "_run_wpa_cli",
            return_value="device_name=TestDevice\ngroup_owner=1",
        )

        peer = service._get_peer_info("aa:bb:cc:dd:ee:ff")

        assert peer is not None
        assert peer.name == "TestDevice"
        assert peer.is_group_owner is True
        assert peer.address == "aa:bb:cc:dd:ee:ff"

    def test_get_peer_info_no_group_owner(self, mocker):
        """Test peer info without group owner flag."""
        service = WiFiDirectService()

        mocker.patch.object(
            service,
            "_run_wpa_cli",
            return_value="device_name=TestDevice",
        )

        peer = service._get_peer_info("aa:bb:cc:dd:ee:ff")

        assert peer is not None
        assert peer.is_group_owner is False

    def test_get_peer_info_exception(self, mocker):
        """Test handling exception."""
        service = WiFiDirectService()

        mocker.patch.object(
            service,
            "_run_wpa_cli",
            side_effect=Exception("Command failed"),
        )
        mock_log = mocker.patch("rpi_usb_cloner.services.wifi_direct.log")

        peer = service._get_peer_info("aa:bb:cc:dd:ee:ff")

        assert peer is None
        mock_log.error.assert_called_once()


class TestGetDeviceShortID:
    """Test device short ID generation."""

    def test_get_id_from_mac(self, mocker):
        """Test ID from MAC address."""
        service = WiFiDirectService()

        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.run",
            return_value=Mock(
                stdout="b8:27:eb:12:34:56",
                returncode=0,
            ),
        )

        device_id = service._get_device_short_id()

        assert device_id == "3456"

    def test_get_id_random_fallback(self, mocker):
        """Test random ID when MAC unavailable."""
        service = WiFiDirectService()

        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.subprocess.run",
            side_effect=Exception("File not found"),
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi_direct.random.randint",
            return_value=0xABCD,
        )

        device_id = service._get_device_short_id()

        assert device_id == "ABCD"
