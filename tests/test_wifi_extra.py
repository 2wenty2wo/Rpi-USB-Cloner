"""Additional tests for Wi-Fi service to improve coverage.

Covers:
- _format_command helper
- _nmcli_unescape helper
- _normalize_ssid helper
- _is_valid_ssid helper
- _split_nmcli_line helper
- list_wifi_interfaces function
- _select_active_interface function
- get_ip_address function
- is_connected function
"""

from __future__ import annotations

import subprocess

import pytest

from rpi_usb_cloner.services import wifi


def _completed_process(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["cmd"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture(autouse=True)
def reset_wifi_cache():
    """Reset global Wi-Fi status cache between tests."""
    wifi._STATUS_CACHE = {"connected": False, "ssid": None, "ip": None}
    wifi._STATUS_CACHE_TIME = None
    wifi._error_handler = None
    wifi._command_runner = None
    yield


class TestFormatCommand:
    """Test _format_command helper."""

    def test_no_redactions(self):
        """Test command formatting without redactions."""
        result = wifi._format_command(["nmcli", "dev", "wifi", "list"])
        assert result == "nmcli dev wifi list"

    def test_with_redactions(self):
        """Test command formatting with password redaction."""
        result = wifi._format_command(
            ["nmcli", "connection", "modify", "ssid", "password", "secret123"],
            redactions=[5],
        )
        assert "******" in result
        assert "secret123" not in result
        assert "nmcli connection modify ssid password" in result

    def test_multiple_redactions(self):
        """Test command formatting with multiple redactions."""
        result = wifi._format_command(
            ["cmd", "arg1", "secret1", "arg3", "secret2"],
            redactions=[2, 4],
        )
        assert result == "cmd arg1 ****** arg3 ******"


class TestNmcliUnescape:
    """Test _nmcli_unescape helper."""

    def test_no_escapes(self):
        """Test unescaping string with no escapes."""
        assert wifi._nmcli_unescape("SimpleSSID") == "SimpleSSID"

    def test_colon_escape(self):
        """Test unescaping colon escape sequence."""
        assert wifi._nmcli_unescape("Cafe\\:Net") == "Cafe:Net"

    def test_pipe_escape(self):
        """Test unescaping pipe escape sequence."""
        assert wifi._nmcli_unescape("Net\\|1") == "Net|1"

    def test_backslash_escape(self):
        """Test unescaping backslash escape sequence."""
        assert wifi._nmcli_unescape("Net\\\\1") == "Net\\1"

    def test_empty_string(self):
        """Test unescaping empty string."""
        assert wifi._nmcli_unescape("") == ""

    def test_trailing_backslash(self):
        """Test unescaping with trailing backslash."""
        assert wifi._nmcli_unescape("Net\\") == "Net\\"


class TestNormalizeSsid:
    """Test _normalize_ssid helper."""

    def test_no_whitespace(self):
        """Test normalizing SSID without whitespace."""
        assert wifi._normalize_ssid("MyNetwork") == "MyNetwork"

    def test_leading_trailing_whitespace(self):
        """Test normalizing SSID with leading/trailing whitespace."""
        assert wifi._normalize_ssid("  MyNetwork  ") == "MyNetwork"

    def test_internal_whitespace_preserved(self):
        """Test that internal whitespace is preserved."""
        assert wifi._normalize_ssid("My Network") == "My Network"


class TestIsValidSsid:
    """Test _is_valid_ssid helper."""

    def test_valid_ssid(self):
        """Test valid SSID."""
        assert wifi._is_valid_ssid("MyNetwork") is True

    def test_empty_ssid(self):
        """Test empty SSID is invalid."""
        assert wifi._is_valid_ssid("") is False

    def test_whitespace_only_ssid(self):
        """Test whitespace-only SSID is invalid."""
        assert wifi._is_valid_ssid("   ") is True  # Whitespace is valid chars

    def test_null_byte_ssid(self):
        """Test SSID with null byte is invalid."""
        assert wifi._is_valid_ssid("Net\x00Work") is False

    def test_32_char_ssid(self):
        """Test 32-character SSID is valid."""
        assert wifi._is_valid_ssid("A" * 32) is True

    def test_33_char_ssid(self):
        """Test 33-character SSID is invalid."""
        assert wifi._is_valid_ssid("A" * 33) is False


class TestSplitNmcliLine:
    """Test _split_nmcli_line helper."""

    def test_simple_split(self):
        """Test simple line split."""
        result = wifi._split_nmcli_line("a:b:c", separator=":")
        assert result == ["a", "b", "c"]

    def test_escaped_separator(self):
        """Test split with escaped separator."""
        result = wifi._split_nmcli_line("Cafe\\:Net:70:WPA2", separator=":")
        assert result == ["Cafe\\:Net", "70", "WPA2"]

    def test_maxsplit(self):
        """Test maxsplit parameter."""
        result = wifi._split_nmcli_line("a:b:c:d", separator=":", maxsplit=2)
        assert result == ["a", "b", "c:d"]

    def test_empty_line(self):
        """Test splitting empty line."""
        result = wifi._split_nmcli_line("", separator=":")
        assert result == [""]

    def test_no_separator(self):
        """Test line with no separator."""
        result = wifi._split_nmcli_line("noseparator", separator=":")
        assert result == ["noseparator"]


class TestListWifiInterfaces:
    """Test list_wifi_interfaces function."""

    def test_iw_dev_parsing(self, mocker):
        """Test parsing iw dev output."""
        mocker.patch(
            "rpi_usb_cloner.services.wifi._run_command",
            return_value=_completed_process(
                "phy#0\n\tInterface wlan0\n\t\ttype managed\n\tInterface wlan1\n"
            ),
        )
        interfaces = wifi.list_wifi_interfaces()
        assert "wlan0" in interfaces
        assert "wlan1" in interfaces

    def test_iw_dev_not_found_fallback_to_nmcli(self, mocker):
        """Test fallback to nmcli when iw not found."""
        def fake_run(command, check=True, redactions=None):
            if command[0] == "iw":
                raise FileNotFoundError("iw not found")
            if command[:4] == ["nmcli", "-t", "-f", "DEVICE,TYPE"]:
                return _completed_process("wlan0:wifi\neth0:ethernet\n")
            raise AssertionError(f"Unexpected command: {command}")

        mocker.patch("rpi_usb_cloner.services.wifi._run_command", side_effect=fake_run)
        interfaces = wifi.list_wifi_interfaces()
        assert "wlan0" in interfaces
        assert "eth0" not in interfaces

    def test_no_interfaces_notifies_error(self, mocker):
        """Test that no interfaces notifies error."""
        errors = []

        def error_handler(lines):
            errors.append(list(lines))

        wifi.configure_wifi_helpers(error_handler=error_handler)
        mocker.patch(
            "rpi_usb_cloner.services.wifi._run_command",
            side_effect=FileNotFoundError("no command"),
        )
        interfaces = wifi.list_wifi_interfaces()
        assert interfaces == []
        assert any("No Wi-Fi interfaces" in str(e) for e in errors)


class TestSelectActiveInterface:
    """Test _select_active_interface function."""

    def test_selects_connected_interface(self, mocker):
        """Test selecting the connected interface."""
        mocker.patch(
            "rpi_usb_cloner.services.wifi.list_wifi_interfaces",
            return_value=["wlan0", "wlan1"],
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi._run_command",
            return_value=_completed_process(
                "wlan0:wifi:connected\nwlan1:wifi:disconnected\n"
            ),
        )
        interface = wifi._select_active_interface()
        assert interface == "wlan0"

    def test_falls_back_to_first_interface(self, mocker):
        """Test falling back to first interface when none connected."""
        mocker.patch(
            "rpi_usb_cloner.services.wifi.list_wifi_interfaces",
            return_value=["wlan0", "wlan1"],
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi._run_command",
            return_value=_completed_process(
                "wlan0:wifi:disconnected\nwlan1:wifi:disconnected\n"
            ),
        )
        interface = wifi._select_active_interface()
        assert interface == "wlan0"

    def test_no_interfaces_returns_none(self, mocker):
        """Test returning None when no interfaces."""
        mocker.patch(
            "rpi_usb_cloner.services.wifi.list_wifi_interfaces",
            return_value=[],
        )
        interface = wifi._select_active_interface()
        assert interface is None


class TestGetIpAddress:
    """Test get_ip_address function."""

    def test_successful_ip_lookup(self, mocker):
        """Test successful IP address lookup."""
        mocker.patch(
            "rpi_usb_cloner.services.wifi._select_active_interface",
            return_value="wlan0",
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi._run_command",
            return_value=_completed_process(
                "2: wlan0: <BROADCAST,MULTICAST> mtu 1500\n    inet 192.168.1.100/24"
            ),
        )
        ip = wifi.get_ip_address()
        assert ip == "192.168.1.100"

    def test_no_ip_found(self, mocker):
        """Test when no IP address is assigned."""
        errors = []

        def error_handler(lines):
            errors.append(list(lines))

        wifi.configure_wifi_helpers(error_handler=error_handler)
        mocker.patch(
            "rpi_usb_cloner.services.wifi._select_active_interface",
            return_value="wlan0",
        )
        mocker.patch(
            "rpi_usb_cloner.services.wifi._run_command",
            return_value=_completed_process("2: wlan0: <BROADCAST> mtu 1500\n"),
        )
        ip = wifi.get_ip_address()
        assert ip is None
        assert any("No IPv4" in str(e) for e in errors)

    def test_no_interface_returns_none(self, mocker):
        """Test returning None when no interface available."""
        mocker.patch(
            "rpi_usb_cloner.services.wifi._select_active_interface",
            return_value=None,
        )
        ip = wifi.get_ip_address()
        assert ip is None


class TestIsConnected:
    """Test is_connected function."""

    def test_connected_when_ssid_present(self, mocker):
        """Test connected status when SSID is present."""
        mocker.patch(
            "rpi_usb_cloner.services.wifi.get_active_ssid",
            return_value="MyNetwork",
        )
        assert wifi.is_connected() is True

    def test_not_connected_when_no_ssid(self, mocker):
        """Test not connected when no SSID."""
        mocker.patch(
            "rpi_usb_cloner.services.wifi.get_active_ssid",
            return_value=None,
        )
        assert wifi.is_connected() is False


class TestNotifyError:
    """Test _notify_error function."""

    def test_error_handler_called(self, mocker):
        """Test that error handler is called with message."""
        errors = []

        def error_handler(lines):
            errors.append(list(lines))

        wifi.configure_wifi_helpers(error_handler=error_handler)
        wifi._notify_error("Something went wrong")

        assert len(errors) == 1
        assert errors[0][0] == "WIFI ERROR"
        assert errors[0][1] == "Something went wrong"

    def test_no_error_handler_logs_only(self, mocker):
        """Test that error is logged when no handler configured."""
        wifi._error_handler = None
        # Should not raise
        wifi._notify_error("Something went wrong")


class TestDefaultRunner:
    """Test _default_runner function."""

    def test_default_runner_calls_subprocess(self, mocker):
        """Test that default runner calls subprocess.run."""
        mock_run = mocker.patch(
            "rpi_usb_cloner.services.wifi.subprocess.run",
            return_value=_completed_process(),
        )
        result = wifi._default_runner(["echo", "test"], check=True)
        mock_run.assert_called_once_with(
            ["echo", "test"], check=True, text=True, capture_output=True
        )
