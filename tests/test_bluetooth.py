"""Tests for Bluetooth tethering functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess

from rpi_usb_cloner.services.bluetooth import (
    BluetoothService,
    BluetoothStatus,
    BluetoothDevice,
    get_bluetooth_service,
    is_bluetooth_available,
    enable_bluetooth_tethering,
    disable_bluetooth_tethering,
)


@pytest.fixture
def bluetooth_service():
    """Create a fresh Bluetooth service instance for testing."""
    return BluetoothService()


@pytest.fixture
def mock_bluetoothctl_list_success(mocker):
    """Mock successful bluetoothctl list command."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = Mock(
        returncode=0, stdout="Controller AA:BB:CC:DD:EE:FF hci0 [default]\n"
    )
    return mock_run


@pytest.fixture
def mock_bluetoothctl_list_failure(mocker):
    """Mock failed bluetoothctl list command."""
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = Mock(returncode=1, stdout="")
    return mock_run


class TestBluetoothService:
    """Test Bluetooth service functionality."""

    def test_get_adapter_name_success(self, bluetooth_service, mock_bluetoothctl_list_success):
        """Test successful adapter detection."""
        adapter = bluetooth_service.get_adapter_name()
        assert adapter == "hci0"
        mock_bluetoothctl_list_success.assert_called_once()

    def test_get_adapter_name_failure(self, bluetooth_service, mock_bluetoothctl_list_failure):
        """Test adapter detection when no adapter present."""
        adapter = bluetooth_service.get_adapter_name()
        assert adapter is None

    def test_get_adapter_name_cached(self, bluetooth_service, mock_bluetoothctl_list_success):
        """Test that adapter name is cached after first call."""
        adapter1 = bluetooth_service.get_adapter_name()
        adapter2 = bluetooth_service.get_adapter_name()

        assert adapter1 == "hci0"
        assert adapter2 == "hci0"
        # Should only call subprocess once due to caching
        assert mock_bluetoothctl_list_success.call_count == 1

    def test_is_available_with_adapter(self, bluetooth_service, mock_bluetoothctl_list_success):
        """Test is_available returns True when adapter present."""
        assert bluetooth_service.is_available() is True

    def test_is_available_without_adapter(self, bluetooth_service, mock_bluetoothctl_list_failure):
        """Test is_available returns False when no adapter."""
        assert bluetooth_service.is_available() is False

    def test_power_on_success(self, bluetooth_service, mocker):
        """Test powering on Bluetooth adapter."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = Mock(returncode=0)
        mocker.patch(
            "rpi_usb_cloner.services.bluetooth.shutil.which",
            side_effect=lambda cmd: None if cmd in {"rfkill", "systemctl"} else "/usr/bin",
        )

        result = bluetooth_service.power_on()

        assert result is True
        mock_run.assert_called_once_with(
            ["bluetoothctl", "power", "on"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )

    def test_power_on_failure(self, bluetooth_service, mocker):
        """Test power on failure handling."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.CalledProcessError(1, "bluetoothctl")

        result = bluetooth_service.power_on()

        assert result is False

    def test_power_off_success(self, bluetooth_service, mocker):
        """Test powering off Bluetooth adapter."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = Mock(returncode=0)

        result = bluetooth_service.power_off()

        assert result is True
        mock_run.assert_called_once_with(
            ["bluetoothctl", "power", "off"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )

    def test_set_discoverable_enabled(self, bluetooth_service, mocker):
        """Test enabling discoverable mode."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = Mock(returncode=0)

        result = bluetooth_service.set_discoverable(True, timeout=300)

        assert result is True
        assert mock_run.call_count == 3  # pairable, discoverable, timeout
        mock_run.assert_has_calls(
            [
                mocker.call(
                    ["bluetoothctl", "pairable", "on"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                ),
                mocker.call(
                    ["bluetoothctl", "discoverable", "on"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                ),
                mocker.call(
                    ["bluetoothctl", "discoverable-timeout", "300"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                ),
            ]
        )

    def test_set_discoverable_disabled(self, bluetooth_service, mocker):
        """Test disabling discoverable mode."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = Mock(returncode=0)

        result = bluetooth_service.set_discoverable(False)

        assert result is True
        assert mock_run.call_count == 2  # pairable, discoverable (no timeout)
        mock_run.assert_has_calls(
            [
                mocker.call(
                    ["bluetoothctl", "pairable", "off"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                ),
                mocker.call(
                    ["bluetoothctl", "discoverable", "off"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                ),
            ]
        )

    def test_list_paired_devices_empty(self, bluetooth_service, mocker):
        """Test listing paired devices when none paired."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = Mock(returncode=0, stdout="")

        devices = bluetooth_service.list_paired_devices()

        assert devices == []

    def test_list_paired_devices_with_devices(self, bluetooth_service, mocker):
        """Test listing paired devices with results."""
        mock_run = mocker.patch("subprocess.run")

        # Mock paired devices list
        devices_output = "Device AA:BB:CC:DD:EE:FF iPhone\nDevice 11:22:33:44:55:66 iPad\n"

        # Mock device info calls
        info_output_iphone = "Name: iPhone\nConnected: yes\nTrusted: yes\nPaired: yes\n"
        info_output_ipad = "Name: iPad\nConnected: no\nTrusted: yes\nPaired: yes\n"

        mock_run.side_effect = [
            Mock(returncode=0, stdout=devices_output),  # devices Paired
            Mock(returncode=0, stdout=info_output_iphone),  # info iPhone
            Mock(returncode=0, stdout=info_output_ipad),  # info iPad
        ]

        devices = bluetooth_service.list_paired_devices()

        assert len(devices) == 2
        assert devices[0].name == "iPhone"
        assert devices[0].connected is True
        assert devices[1].name == "iPad"
        assert devices[1].connected is False

    def test_trust_device_success(self, bluetooth_service, mocker):
        """Test trusting a device."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = Mock(returncode=0)

        result = bluetooth_service.trust_device("AA:BB:CC:DD:EE:FF")

        assert result is True
        mock_run.assert_called_once_with(
            ["bluetoothctl", "trust", "AA:BB:CC:DD:EE:FF"],
            capture_output=True,
            timeout=5,
            check=True,
        )

    def test_remove_device_success(self, bluetooth_service, mocker):
        """Test removing a paired device."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = Mock(returncode=0)

        result = bluetooth_service.remove_device("AA:BB:CC:DD:EE:FF")

        assert result is True
        mock_run.assert_called_once_with(
            ["bluetoothctl", "remove", "AA:BB:CC:DD:EE:FF"],
            capture_output=True,
            timeout=5,
            check=True,
        )

    def test_get_status_no_adapter(self, bluetooth_service, mock_bluetoothctl_list_failure):
        """Test getting status when no adapter present."""
        status = bluetooth_service.get_status()

        assert status.adapter_present is False
        assert status.powered is False
        assert status.pan_active is False

    def test_get_status_with_adapter(self, bluetooth_service, mocker):
        """Test getting status with adapter present."""
        # Mock adapter detection
        mocker.patch.object(bluetooth_service, "get_adapter_name", return_value="hci0")

        # Mock bluetoothctl show
        mock_run = mocker.patch("subprocess.run")
        show_output = "Powered: yes\nDiscoverable: yes\nPairable: yes\n"
        mock_run.return_value = Mock(returncode=0, stdout=show_output)

        # Mock interface checks
        mocker.patch.object(bluetooth_service, "_is_interface_up", return_value=True)
        mocker.patch.object(bluetooth_service, "_get_interface_ip", return_value="192.168.55.1")
        mocker.patch.object(bluetooth_service, "list_paired_devices", return_value=[])

        status = bluetooth_service.get_status()

        assert status.adapter_present is True
        assert status.powered is True
        assert status.discoverable is True
        assert status.pairable is True
        assert status.pan_active is True
        assert status.ip_address == "192.168.55.1"

    def test_create_bridge_success(self, bluetooth_service, mocker):
        """Test creating bridge interface."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = Mock(returncode=0)
        mocker.patch.object(bluetooth_service, "_is_interface_up", return_value=False)

        result = bluetooth_service._create_bridge()

        assert result is True
        assert mock_run.call_count == 2  # create + bring up

    def test_create_bridge_already_exists(self, bluetooth_service, mocker):
        """Test creating bridge when it already exists."""
        mocker.patch.object(bluetooth_service, "_is_interface_up", return_value=True)

        result = bluetooth_service._create_bridge()

        assert result is True

    def test_netmask_to_cidr(self):
        """Test netmask to CIDR conversion."""
        assert BluetoothService._netmask_to_cidr("255.255.255.0") == 24
        assert BluetoothService._netmask_to_cidr("255.255.0.0") == 16
        assert BluetoothService._netmask_to_cidr("255.0.0.0") == 8
        assert BluetoothService._netmask_to_cidr("255.255.255.255") == 24  # default


class TestBluetoothConvenienceFunctions:
    """Test convenience functions."""

    def test_is_bluetooth_available(self, mocker):
        """Test is_bluetooth_available convenience function."""
        mock_service = Mock()
        mock_service.is_available.return_value = True
        mocker.patch(
            "rpi_usb_cloner.services.bluetooth.get_bluetooth_service",
            return_value=mock_service,
        )

        assert is_bluetooth_available() is True
        mock_service.is_available.assert_called_once()

    def test_enable_bluetooth_tethering(self, mocker):
        """Test enable_bluetooth_tethering convenience function."""
        mock_service = Mock()
        mock_service.setup_pan.return_value = True
        mocker.patch(
            "rpi_usb_cloner.services.bluetooth.get_bluetooth_service",
            return_value=mock_service,
        )

        assert enable_bluetooth_tethering() is True
        mock_service.setup_pan.assert_called_once()

    def test_disable_bluetooth_tethering(self, mocker):
        """Test disable_bluetooth_tethering convenience function."""
        mock_service = Mock()
        mock_service.teardown_pan.return_value = True
        mocker.patch(
            "rpi_usb_cloner.services.bluetooth.get_bluetooth_service",
            return_value=mock_service,
        )

        assert disable_bluetooth_tethering() is True
        mock_service.teardown_pan.assert_called_once()


class TestBluetoothDataClasses:
    """Test Bluetooth data classes."""

    def test_bluetooth_device_creation(self):
        """Test BluetoothDevice dataclass."""
        device = BluetoothDevice(
            mac_address="AA:BB:CC:DD:EE:FF",
            name="iPhone",
            paired=True,
            connected=True,
            trusted=True,
        )

        assert device.mac_address == "AA:BB:CC:DD:EE:FF"
        assert device.name == "iPhone"
        assert device.paired is True
        assert device.connected is True
        assert device.trusted is True

    def test_bluetooth_status_creation(self):
        """Test BluetoothStatus dataclass."""
        status = BluetoothStatus(
            adapter_present=True,
            powered=True,
            discoverable=False,
            pairable=True,
            pan_active=True,
            ip_address="192.168.55.1",
            connected_devices=[],
        )

        assert status.adapter_present is True
        assert status.powered is True
        assert status.discoverable is False
        assert status.pan_active is True
        assert status.ip_address == "192.168.55.1"
        assert status.connected_devices == []
