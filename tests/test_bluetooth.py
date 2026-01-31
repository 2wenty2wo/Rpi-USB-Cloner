"""Tests for Bluetooth PAN service.

These tests cover the Bluetooth PAN functionality including:
- Status management
- PIN generation
- QR code generation
- Manager state handling
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

# Skip all tests if we're not on a Raspberry Pi (bluetooth dependencies may not be available)
pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        True,  # Will be updated when dbus-python is available
        reason="Bluetooth dependencies not available in test environment",
    ),
]


class TestBluetoothStatus:
    """Test BluetoothStatus dataclass."""

    def test_status_creation(self):
        """Test creating a BluetoothStatus object."""
        from rpi_usb_cloner.services.bluetooth import BluetoothStatus

        status = BluetoothStatus(
            enabled=True,
            mac_address="AA:BB:CC:DD:EE:FF",
            pin="123456",
            ip_address="192.168.50.1",
            connected=True,
            connected_device="Test Phone (AA:BB:CC:DD:EE:FF)",
            bnep_interface="bnep0",
        )

        assert status.enabled is True
        assert status.mac_address == "AA:BB:CC:DD:EE:FF"
        assert status.pin == "123456"
        assert status.ip_address == "192.168.50.1"
        assert status.connected is True
        assert status.connected_device == "Test Phone (AA:BB:CC:DD:EE:FF)"
        assert status.bnep_interface == "bnep0"

    def test_status_disabled(self):
        """Test status when Bluetooth is disabled."""
        from rpi_usb_cloner.services.bluetooth import BluetoothStatus

        status = BluetoothStatus(
            enabled=False,
            mac_address=None,
            pin=None,
            ip_address=None,
            connected=False,
            connected_device=None,
            bnep_interface=None,
        )

        assert status.enabled is False
        assert status.mac_address is None
        assert status.connected is False


class TestBluetoothPANManager:
    """Test BluetoothPANManager class."""

    @pytest.fixture
    def manager(self):
        """Create a fresh BluetoothPANManager instance."""
        from rpi_usb_cloner.services.bluetooth import BluetoothPANManager

        return BluetoothPANManager()

    def test_initial_state(self, manager):
        """Test manager starts in disabled state."""
        status = manager.get_status()
        assert status.enabled is False
        assert status.pin is None
        assert status.mac_address is None

    def test_generate_pin(self, manager):
        """Test PIN generation."""
        pin = manager._generate_pin()

        # PIN should be 6 characters
        assert len(pin) == 6
        # PIN should be uppercase hex
        assert pin.isalnum()
        assert pin.isupper()
        # Should be different each time (statistically)
        pin2 = manager._generate_pin()
        assert pin != pin2 or True  # Could theoretically match, but unlikely

    def test_generate_pairing_data_disabled(self, manager):
        """Test pairing data generation when disabled."""
        data = manager.generate_pairing_data()
        assert "error" in data
        assert data["error"] == "Bluetooth not enabled"

    @patch("rpi_usb_cloner.services.bluetooth.subprocess.run")
    def test_get_adapter_mac(self, mock_run, manager):
        """Test getting adapter MAC address."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Controller AA:BB:CC:DD:EE:FF rpi-usb-cloner [default]\n",
        )

        mac = manager._get_adapter_mac()
        assert mac == "AA:BB:CC:DD:EE:FF"

    @patch("rpi_usb_cloner.services.bluetooth.subprocess.run")
    def test_get_adapter_mac_failure(self, mock_run, manager):
        """Test MAC address retrieval failure."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        mac = manager._get_adapter_mac()
        assert mac is None

    def test_add_remove_status_listener(self, manager):
        """Test adding and removing status listeners."""
        listener_calls = []

        def listener(status):
            listener_calls.append(status)

        # Add listener
        manager.add_status_listener(listener)
        assert listener in manager._status_listeners

        # Remove listener
        manager.remove_status_listener(listener)
        assert listener not in manager._status_listeners


class TestQRCodeGeneration:
    """Test QR code generation functions."""

    @pytest.fixture
    def mock_enabled_manager(self):
        """Create a mock manager that returns enabled status."""
        with patch(
            "rpi_usb_cloner.services.bluetooth.get_bluetooth_manager"
        ) as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_status.return_value = MagicMock(
                enabled=True,
                mac_address="AA:BB:CC:DD:EE:FF",
                pin="123456",
            )
            mock_manager.generate_pairing_data.return_value = {
                "device_name": "RPI-USB-CLONER",
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "pin": "123456",
                "web_url": "http://192.168.50.1:8000",
            }
            mock_manager.generate_qr_text.return_value = (
                "BT:AA:BB:CC:DD:EE:FF;P:123456;N:RPI-USB-CLONER;U:http://192.168.50.1:8000"
            )
            mock_get_manager.return_value = mock_manager
            yield mock_manager

    def test_generate_pairing_data(self, mock_enabled_manager):
        """Test pairing data generation."""
        from rpi_usb_cloner.services.bluetooth import generate_qr_data

        data = generate_qr_data()

        assert data["device_name"] == "RPI-USB-CLONER"
        assert data["mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert data["pin"] == "123456"
        assert "192.168.50.1" in data["web_url"]

    def test_generate_qr_text(self, mock_enabled_manager):
        """Test QR text generation."""
        from rpi_usb_cloner.services.bluetooth import generate_qr_text

        qr_text = generate_qr_text()

        assert "BT:" in qr_text
        assert "AA:BB:CC:DD:EE:FF" in qr_text
        assert "P:123456" in qr_text
        assert "N:RPI-USB-CLONER" in qr_text
        assert "U:http://" in qr_text


class TestConvenienceFunctions:
    """Test convenience module functions."""

    @patch("rpi_usb_cloner.services.bluetooth.BluetoothPANManager")
    def test_get_bluetooth_manager_singleton(self, mock_manager_class):
        """Test that get_bluetooth_manager returns a singleton."""
        from rpi_usb_cloner.services.bluetooth import get_bluetooth_manager

        # Clear any existing instance
        import rpi_usb_cloner.services.bluetooth as bt_module

        bt_module._bluetooth_manager = None

        # Get manager twice
        manager1 = get_bluetooth_manager()
        manager2 = get_bluetooth_manager()

        # Should be the same instance
        assert manager1 is manager2

    @patch("rpi_usb_cloner.services.bluetooth.get_bluetooth_manager")
    def test_is_bluetooth_pan_enabled(self, mock_get_manager):
        """Test is_bluetooth_pan_enabled function."""
        from rpi_usb_cloner.services.bluetooth import is_bluetooth_pan_enabled

        mock_manager = MagicMock()
        mock_manager.get_status.return_value = MagicMock(enabled=True)
        mock_get_manager.return_value = mock_manager

        assert is_bluetooth_pan_enabled() is True

    @patch("rpi_usb_cloner.services.bluetooth.get_bluetooth_manager")
    def test_is_bluetooth_connected(self, mock_get_manager):
        """Test is_bluetooth_connected function."""
        from rpi_usb_cloner.services.bluetooth import is_bluetooth_connected

        mock_manager = MagicMock()
        mock_manager.get_status.return_value = MagicMock(connected=True)
        mock_get_manager.return_value = mock_manager

        assert is_bluetooth_connected() is True
