"""Tests for the status bar module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from rpi_usb_cloner.ui.status_bar import (
    ICON_BLUETOOTH,
    ICON_POINTER,
    ICON_WIFI,
    StatusIndicator,
    collect_status_indicators,
    get_bluetooth_indicator,
    get_drive_indicators,
    get_operation_indicator,
    get_web_server_indicator,
    get_wifi_indicator,
)


class TestStatusIndicator:
    """Tests for the StatusIndicator dataclass."""

    def test_status_indicator_creation(self):
        """Test creating a basic status indicator."""
        indicator = StatusIndicator(label="TEST")
        assert indicator.label == "TEST"
        assert indicator.priority == 0
        assert indicator.inverted is False
        assert indicator.icon_path is None

    def test_status_indicator_with_priority(self):
        """Test creating indicator with custom priority."""
        indicator = StatusIndicator(label="HIGH", priority=100)
        assert indicator.priority == 100

    def test_status_indicator_inverted(self):
        """Test creating inverted indicator."""
        indicator = StatusIndicator(label="WARN", inverted=True)
        assert indicator.inverted is True

    def test_status_indicator_with_icon_path(self):
        """Test creating indicator with icon path."""
        indicator = StatusIndicator(label="W", icon_path=ICON_WIFI)
        assert indicator.icon_path == ICON_WIFI
        assert indicator.label == "W"

    def test_status_indicator_is_frozen(self):
        """Test that StatusIndicator is immutable."""
        indicator = StatusIndicator(label="TEST")
        with pytest.raises(AttributeError):
            indicator.label = "CHANGED"

    def test_is_icon_property_with_existing_file(self):
        """Test is_icon returns True when icon_path exists."""
        # ICON_WIFI should exist in the assets folder
        indicator = StatusIndicator(label="W", icon_path=ICON_WIFI)
        assert indicator.is_icon is True

    def test_is_icon_property_with_missing_file(self):
        """Test is_icon returns False when icon_path doesn't exist."""
        indicator = StatusIndicator(label="X", icon_path=Path("/nonexistent/icon.png"))
        assert indicator.is_icon is False

    def test_is_icon_property_with_none(self):
        """Test is_icon returns False when icon_path is None."""
        indicator = StatusIndicator(label="X")
        assert indicator.is_icon is False


class TestGetBluetoothIndicator:
    """Tests for the get_bluetooth_indicator function."""

    def test_returns_none_when_no_devices(self, mocker):
        """Test returns None when no bluetooth devices connected."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = Mock(returncode=0, stdout="")
        result = get_bluetooth_indicator()
        assert result is None

    def test_returns_indicator_when_connected(self, mocker):
        """Test returns indicator with Bluetooth icon when connected."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = Mock(
            returncode=0, stdout="Device AA:BB:CC:DD:EE:FF MyDevice"
        )
        result = get_bluetooth_indicator()
        assert result is not None
        assert result.icon_path == ICON_BLUETOOTH
        assert result.priority == 25

    def test_handles_exception_gracefully(self, mocker):
        """Test handles exception gracefully."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = Exception("Bluetooth error")
        result = get_bluetooth_indicator()
        assert result is None


class TestGetWifiIndicator:
    """Tests for the get_wifi_indicator function."""

    def test_returns_none_when_not_connected(self, mocker):
        """Test returns None when WiFi is not connected."""
        mocker.patch(
            "rpi_usb_cloner.services.wifi.get_status_cached",
            return_value={"connected": False, "ssid": None, "ip": None},
        )
        result = get_wifi_indicator()
        assert result is None

    def test_returns_indicator_when_connected(self, mocker):
        """Test returns indicator with WiFi icon when connected."""
        mocker.patch(
            "rpi_usb_cloner.services.wifi.get_status_cached",
            return_value={"connected": True, "ssid": "MyNetwork", "ip": "192.168.1.100"},
        )
        result = get_wifi_indicator()
        assert result is not None
        assert result.icon_path == ICON_WIFI
        assert result.priority == 30

    def test_handles_exception_gracefully(self, mocker):
        """Test handles import/exception gracefully."""
        mocker.patch(
            "rpi_usb_cloner.services.wifi.get_status_cached",
            side_effect=Exception("WiFi error"),
        )
        result = get_wifi_indicator()
        assert result is None


class TestGetWebServerIndicator:
    """Tests for the get_web_server_indicator function."""

    def test_returns_none_when_not_running(self, mocker):
        """Test returns None when web server is not running."""
        mocker.patch(
            "rpi_usb_cloner.web.server.is_running",
            return_value=False,
        )
        result = get_web_server_indicator()
        assert result is None

    def test_returns_indicator_when_running(self, mocker):
        """Test returns indicator with pointer icon when web server is running."""
        mocker.patch(
            "rpi_usb_cloner.web.server.is_running",
            return_value=True,
        )
        result = get_web_server_indicator()
        assert result is not None
        assert result.icon_path == ICON_POINTER
        assert result.priority == 20

    def test_handles_exception_gracefully(self, mocker):
        """Test handles import/exception gracefully."""
        mocker.patch(
            "rpi_usb_cloner.web.server.is_running",
            side_effect=Exception("Server error"),
        )
        result = get_web_server_indicator()
        assert result is None


class TestGetOperationIndicator:
    """Tests for the get_operation_indicator function."""

    def test_returns_none_always(self):
        """Test operation indicator is currently hidden (returns None)."""
        # Operation indicator is hidden per user request
        result = get_operation_indicator(None)
        assert result is None

        mock_context = Mock()
        mock_context.operation_active = True
        result = get_operation_indicator(mock_context)
        assert result is None  # Still None because it's hidden


class TestGetDriveIndicators:
    """Tests for the get_drive_indicators function."""

    def test_returns_empty_when_no_drives(self, mocker):
        """Test returns empty list when no drives connected."""
        mocker.patch(
            "rpi_usb_cloner.services.drives.get_drive_counts",
            return_value=(0, 0),
        )
        result = get_drive_indicators()
        assert result == []

    def test_returns_usb_indicator_only(self, mocker):
        """Test returns only USB indicator when no repos."""
        mocker.patch(
            "rpi_usb_cloner.services.drives.get_drive_counts",
            return_value=(2, 0),
        )
        result = get_drive_indicators()
        assert len(result) == 1
        assert result[0].label == "U2"
        assert result[0].priority == 0
        assert result[0].icon_path is None  # Text indicator, no icon
        assert result[0].inverted is True  # Solid black box with white text

    def test_returns_repo_indicator_only(self, mocker):
        """Test returns only Repo indicator when no USB drives."""
        mocker.patch(
            "rpi_usb_cloner.services.drives.get_drive_counts",
            return_value=(0, 1),
        )
        result = get_drive_indicators()
        assert len(result) == 1
        assert result[0].label == "R1"
        assert result[0].priority == 1

    def test_returns_both_indicators(self, mocker):
        """Test returns both indicators when drives and repos present."""
        mocker.patch(
            "rpi_usb_cloner.services.drives.get_drive_counts",
            return_value=(3, 2),
        )
        result = get_drive_indicators()
        assert len(result) == 2
        # Repo has priority 1, USB has priority 0
        labels = {i.label for i in result}
        assert "U3" in labels
        assert "R2" in labels

    def test_handles_exception_gracefully(self, mocker):
        """Test handles import/exception gracefully."""
        mocker.patch(
            "rpi_usb_cloner.services.drives.get_drive_counts",
            side_effect=Exception("Drive error"),
        )
        result = get_drive_indicators()
        assert result == []


class TestCollectStatusIndicators:
    """Tests for the collect_status_indicators function."""

    def test_collects_indicators_without_operation(self, mocker):
        """Test collects indicators (operation is hidden by default)."""
        mocker.patch(
            "rpi_usb_cloner.services.drives.get_drive_counts",
            return_value=(1, 1),
        )
        mocker.patch(
            "rpi_usb_cloner.web.server.is_running",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi.get_status_cached",
            return_value={"connected": True, "ssid": "Test", "ip": "1.2.3.4"},
        )
        mocker.patch("subprocess.run", return_value=Mock(returncode=0, stdout=""))

        mock_context = Mock()
        mock_context.operation_active = True

        result = collect_status_indicators(mock_context)

        # Should have: U1, R1, pointer icon, wifi icon (no bluetooth, no operation)
        # Operation is hidden by default, bluetooth returns None (no connected devices)
        assert len(result) == 4
        labels = [i.label for i in result]
        icon_paths = [i.icon_path for i in result]
        # Text labels for drives
        assert "U1" in labels
        assert "R1" in labels
        # Icons for WiFi, Web
        assert ICON_WIFI in icon_paths
        assert ICON_POINTER in icon_paths

    def test_sorted_by_priority(self, mocker):
        """Test indicators are sorted by priority (lowest first)."""
        mocker.patch(
            "rpi_usb_cloner.services.drives.get_drive_counts",
            return_value=(1, 1),
        )
        mocker.patch(
            "rpi_usb_cloner.web.server.is_running",
            return_value=True,
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi.get_status_cached",
            return_value={"connected": True, "ssid": "Test", "ip": "1.2.3.4"},
        )
        mocker.patch("subprocess.run", return_value=Mock(returncode=0, stdout=""))

        result = collect_status_indicators()

        # Verify sorted by priority (ascending)
        priorities = [i.priority for i in result]
        assert priorities == sorted(priorities)

    def test_can_exclude_indicators(self, mocker):
        """Test can selectively exclude indicator types."""
        mocker.patch(
            "rpi_usb_cloner.services.drives.get_drive_counts",
            return_value=(1, 0),
        )

        result = collect_status_indicators(
            include_bluetooth=False,
            include_wifi=False,
            include_web=False,
            include_operation=False,
            include_drives=True,
        )

        assert len(result) == 1
        assert result[0].label == "U1"

    def test_empty_when_all_excluded(self):
        """Test returns empty when all indicators excluded."""
        result = collect_status_indicators(
            include_bluetooth=False,
            include_wifi=False,
            include_web=False,
            include_operation=False,
            include_drives=False,
        )

        assert result == []

    def test_includes_bluetooth_when_connected(self, mocker):
        """Test includes bluetooth indicator when device is connected."""
        mocker.patch(
            "rpi_usb_cloner.services.drives.get_drive_counts",
            return_value=(0, 0),
        )
        mocker.patch(
            "rpi_usb_cloner.web.server.is_running",
            return_value=False,
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi.get_status_cached",
            return_value={"connected": False, "ssid": None, "ip": None},
        )
        mocker.patch(
            "subprocess.run",
            return_value=Mock(returncode=0, stdout="Device AA:BB:CC:DD:EE:FF MyDevice"),
        )

        result = collect_status_indicators()

        assert len(result) == 1
        assert result[0].icon_path == ICON_BLUETOOTH

    def test_status_bar_disabled_returns_empty(self, mocker):
        """Test returns empty list when status bar is disabled via settings."""
        mocker.patch(
            "rpi_usb_cloner.config.settings.get_bool",
            side_effect=lambda key, default=None: False if key == "status_bar_enabled" else True,
        )
        mocker.patch(
            "rpi_usb_cloner.services.drives.get_drive_counts",
            return_value=(2, 1),
        )

        result = collect_status_indicators()

        assert result == []

    def test_individual_settings_respected(self, mocker):
        """Test individual indicator settings are respected."""
        def mock_get_bool(key, default=None):
            if key == "status_bar_enabled":
                return True
            if key == "status_bar_wifi_enabled":
                return False  # Disable WiFi
            if key == "status_bar_drives_enabled":
                return True
            return True

        mocker.patch(
            "rpi_usb_cloner.config.settings.get_bool",
            side_effect=mock_get_bool,
        )
        mocker.patch(
            "rpi_usb_cloner.services.drives.get_drive_counts",
            return_value=(1, 0),
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi.get_status_cached",
            return_value={"connected": True, "ssid": "Test", "ip": "1.2.3.4"},
        )
        mocker.patch(
            "rpi_usb_cloner.web.server.is_running",
            return_value=False,
        )
        mocker.patch(
            "subprocess.run",
            return_value=Mock(returncode=0, stdout=""),
        )

        result = collect_status_indicators()

        # Should only have drives (WiFi disabled via settings)
        assert len(result) == 1
        assert result[0].label == "U1"
        # WiFi should not be in the list
        for indicator in result:
            assert indicator.icon_path != ICON_WIFI
