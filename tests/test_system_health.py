"""Tests for web/system_health.py module.

This module tests system health monitoring functions.
"""

from pathlib import Path
from unittest.mock import Mock, patch


class TestSystemHealthDataclass:
    """Tests for SystemHealth dataclass."""

    def test_create_system_health(self):
        """Test creating SystemHealth instance."""
        from rpi_usb_cloner.web.system_health import SystemHealth

        health = SystemHealth(
            cpu_percent=25.5,
            memory_percent=60.0,
            memory_used_mb=2048,
            memory_total_mb=4096,
            disk_percent=45.0,
            disk_used_gb=50.5,
            disk_total_gb=100.0,
            temperature_celsius=45.0,
        )

        assert health.cpu_percent == 25.5
        assert health.memory_percent == 60.0
        assert health.memory_used_mb == 2048
        assert health.memory_total_mb == 4096
        assert health.disk_percent == 45.0
        assert health.disk_used_gb == 50.5
        assert health.disk_total_gb == 100.0
        assert health.temperature_celsius == 45.0

    def test_create_system_health_no_temperature(self):
        """Test creating SystemHealth with no temperature."""
        from rpi_usb_cloner.web.system_health import SystemHealth

        health = SystemHealth(
            cpu_percent=10.0,
            memory_percent=30.0,
            memory_used_mb=1024,
            memory_total_mb=4096,
            disk_percent=20.0,
            disk_used_gb=10.0,
            disk_total_gb=50.0,
            temperature_celsius=None,
        )

        assert health.temperature_celsius is None


class TestGetCpuTemperature:
    """Tests for get_cpu_temperature function."""

    def test_get_cpu_temperature_from_thermal_zone(self, mocker, tmp_path):
        """Test reading temperature from thermal zone."""
        from rpi_usb_cloner.web.system_health import get_cpu_temperature

        # Create mock thermal zone file
        thermal_zone = tmp_path / "thermal_zone0" / "temp"
        thermal_zone.parent.mkdir(parents=True)
        thermal_zone.write_text("45000")  # 45.0 degrees in millidegrees

        with patch.object(Path, "__new__") as mock_path:
            mock_path.return_value = thermal_zone
            mock_thermal = Mock()
            mock_thermal.exists.return_value = True
            mock_thermal.read_text.return_value = "45000"
            mocker.patch(
                "rpi_usb_cloner.web.system_health.Path",
                return_value=mock_thermal,
            )

            temp = get_cpu_temperature()
            assert temp == 45.0

    def test_get_cpu_temperature_thermal_zone_not_exists(self, mocker):
        """Test when thermal zone file doesn't exist."""
        from rpi_usb_cloner.web.system_health import get_cpu_temperature

        mock_thermal = Mock()
        mock_thermal.exists.return_value = False
        mocker.patch(
            "rpi_usb_cloner.web.system_health.Path",
            return_value=mock_thermal,
        )

        # Mock subprocess for vcgencmd (which should also fail)
        mock_subprocess = mocker.patch("subprocess.run")
        mock_subprocess.side_effect = FileNotFoundError("vcgencmd not found")

        temp = get_cpu_temperature()
        assert temp is None

    def test_get_cpu_temperature_from_vcgencmd(self, mocker):
        """Test reading temperature from vcgencmd (Raspberry Pi)."""
        from rpi_usb_cloner.web.system_health import get_cpu_temperature

        # Mock thermal zone doesn't exist
        mock_thermal = Mock()
        mock_thermal.exists.return_value = False
        mocker.patch(
            "rpi_usb_cloner.web.system_health.Path",
            return_value=mock_thermal,
        )

        # Mock vcgencmd success
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "temp=52.3'C"
        mock_subprocess = mocker.patch("subprocess.run", return_value=mock_result)

        temp = get_cpu_temperature()
        assert temp == 52.3
        mock_subprocess.assert_called_once()

    def test_get_cpu_temperature_vcgencmd_fails(self, mocker):
        """Test when vcgencmd command fails."""
        from rpi_usb_cloner.web.system_health import get_cpu_temperature

        # Mock thermal zone doesn't exist
        mock_thermal = Mock()
        mock_thermal.exists.return_value = False
        mocker.patch(
            "rpi_usb_cloner.web.system_health.Path",
            return_value=mock_thermal,
        )

        # Mock vcgencmd failure
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mocker.patch("subprocess.run", return_value=mock_result)

        temp = get_cpu_temperature()
        assert temp is None

    def test_get_cpu_temperature_thermal_zone_value_error(self, mocker):
        """Test when thermal zone contains invalid value."""
        from rpi_usb_cloner.web.system_health import get_cpu_temperature

        mock_thermal = Mock()
        mock_thermal.exists.return_value = True
        mock_thermal.read_text.return_value = "invalid"
        mocker.patch(
            "rpi_usb_cloner.web.system_health.Path",
            return_value=mock_thermal,
        )

        # Mock vcgencmd also fails
        mocker.patch("subprocess.run", side_effect=FileNotFoundError())

        temp = get_cpu_temperature()
        assert temp is None

    def test_get_cpu_temperature_vcgencmd_timeout(self, mocker):
        """Test when vcgencmd times out."""
        import subprocess

        from rpi_usb_cloner.web.system_health import get_cpu_temperature

        # Mock thermal zone doesn't exist
        mock_thermal = Mock()
        mock_thermal.exists.return_value = False
        mocker.patch(
            "rpi_usb_cloner.web.system_health.Path",
            return_value=mock_thermal,
        )

        # Mock vcgencmd timeout
        mocker.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("vcgencmd", 1.0),
        )

        temp = get_cpu_temperature()
        assert temp is None


class TestGetSystemHealth:
    """Tests for get_system_health function."""

    def test_get_system_health_returns_metrics(self, mocker):
        """Test that get_system_health returns all metrics."""
        from rpi_usb_cloner.web.system_health import SystemHealth, get_system_health

        # Mock psutil functions
        mocker.patch("psutil.cpu_percent", return_value=25.5)
        mock_memory = Mock()
        mock_memory.percent = 60.0
        mock_memory.used = 2 * 1024 * 1024 * 1024  # 2GB
        mock_memory.total = 4 * 1024 * 1024 * 1024  # 4GB
        mocker.patch("psutil.virtual_memory", return_value=mock_memory)

        mock_disk = Mock()
        mock_disk.percent = 45.0
        mock_disk.used = 50 * 1024**3  # 50GB
        mock_disk.total = 100 * 1024**3  # 100GB
        mocker.patch("psutil.disk_usage", return_value=mock_disk)

        # Mock temperature
        mocker.patch(
            "rpi_usb_cloner.web.system_health.get_cpu_temperature",
            return_value=42.5,
        )

        health = get_system_health()

        assert isinstance(health, SystemHealth)
        assert health.cpu_percent == 25.5
        assert health.memory_percent == 60.0
        assert health.memory_used_mb == 2048
        assert health.memory_total_mb == 4096
        assert health.disk_percent == 45.0
        assert health.disk_used_gb == 50.0
        assert health.disk_total_gb == 100.0
        assert health.temperature_celsius == 42.5

    def test_get_system_health_no_temperature(self, mocker):
        """Test get_system_health when temperature is unavailable."""
        from rpi_usb_cloner.web.system_health import get_system_health

        mocker.patch("psutil.cpu_percent", return_value=10.0)
        mock_memory = Mock()
        mock_memory.percent = 30.0
        mock_memory.used = 1024 * 1024 * 1024
        mock_memory.total = 2 * 1024 * 1024 * 1024
        mocker.patch("psutil.virtual_memory", return_value=mock_memory)

        mock_disk = Mock()
        mock_disk.percent = 20.0
        mock_disk.used = 10 * 1024**3
        mock_disk.total = 50 * 1024**3
        mocker.patch("psutil.disk_usage", return_value=mock_disk)

        mocker.patch(
            "rpi_usb_cloner.web.system_health.get_cpu_temperature",
            return_value=None,
        )

        health = get_system_health()
        assert health.temperature_celsius is None


class TestGetTemperatureStatus:
    """Tests for get_temperature_status function."""

    def test_temperature_status_none(self):
        """Test status for None temperature."""
        from rpi_usb_cloner.web.system_health import get_temperature_status

        assert get_temperature_status(None) == "secondary"

    def test_temperature_status_cool(self):
        """Test status for cool temperature (<60C)."""
        from rpi_usb_cloner.web.system_health import get_temperature_status

        assert get_temperature_status(30.0) == "success"
        assert get_temperature_status(45.0) == "success"
        assert get_temperature_status(59.9) == "success"

    def test_temperature_status_warm(self):
        """Test status for warm temperature (60-75C)."""
        from rpi_usb_cloner.web.system_health import get_temperature_status

        assert get_temperature_status(60.0) == "warning"
        assert get_temperature_status(70.0) == "warning"
        assert get_temperature_status(74.9) == "warning"

    def test_temperature_status_hot(self):
        """Test status for hot temperature (>=75C)."""
        from rpi_usb_cloner.web.system_health import get_temperature_status

        assert get_temperature_status(75.0) == "danger"
        assert get_temperature_status(80.0) == "danger"
        assert get_temperature_status(85.0) == "danger"

    def test_temperature_status_boundary_60(self):
        """Test exact boundary at 60C."""
        from rpi_usb_cloner.web.system_health import get_temperature_status

        assert get_temperature_status(59.99) == "success"
        assert get_temperature_status(60.0) == "warning"

    def test_temperature_status_boundary_75(self):
        """Test exact boundary at 75C."""
        from rpi_usb_cloner.web.system_health import get_temperature_status

        assert get_temperature_status(74.99) == "warning"
        assert get_temperature_status(75.0) == "danger"


class TestGetUsageStatus:
    """Tests for get_usage_status function."""

    def test_usage_status_low(self):
        """Test status for low usage (<70%)."""
        from rpi_usb_cloner.web.system_health import get_usage_status

        assert get_usage_status(0.0) == "success"
        assert get_usage_status(30.0) == "success"
        assert get_usage_status(50.0) == "success"
        assert get_usage_status(69.9) == "success"

    def test_usage_status_moderate(self):
        """Test status for moderate usage (70-85%)."""
        from rpi_usb_cloner.web.system_health import get_usage_status

        assert get_usage_status(70.0) == "warning"
        assert get_usage_status(75.0) == "warning"
        assert get_usage_status(84.9) == "warning"

    def test_usage_status_high(self):
        """Test status for high usage (>=85%)."""
        from rpi_usb_cloner.web.system_health import get_usage_status

        assert get_usage_status(85.0) == "danger"
        assert get_usage_status(90.0) == "danger"
        assert get_usage_status(100.0) == "danger"

    def test_usage_status_boundary_70(self):
        """Test exact boundary at 70%."""
        from rpi_usb_cloner.web.system_health import get_usage_status

        assert get_usage_status(69.99) == "success"
        assert get_usage_status(70.0) == "warning"

    def test_usage_status_boundary_85(self):
        """Test exact boundary at 85%."""
        from rpi_usb_cloner.web.system_health import get_usage_status

        assert get_usage_status(84.99) == "warning"
        assert get_usage_status(85.0) == "danger"
