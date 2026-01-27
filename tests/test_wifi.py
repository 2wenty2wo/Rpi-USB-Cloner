"""Tests for Wi-Fi service helpers."""

from __future__ import annotations

import subprocess

import pytest

from rpi_usb_cloner.services import wifi


def _completed_process(
    stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["cmd"], returncode=0, stdout=stdout, stderr=stderr
    )


@pytest.fixture(autouse=True)
def reset_wifi_cache():
    """Reset global Wi-Fi status cache between tests."""
    wifi._STATUS_CACHE = {"connected": False, "ssid": None, "ip": None}
    wifi._STATUS_CACHE_TIME = None
    wifi._error_handler = None
    wifi._command_runner = None
    yield


def test_list_networks_parses_nmcli_output(mocker):
    """Test nmcli parsing handles escaped SSIDs and security flags."""
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )

    def fake_run(command, check=True, redactions=None):
        if command[:2] == ["rfkill", "unblock"]:
            return _completed_process()
        if command[:3] == ["ip", "link", "set"]:
            return _completed_process()
        if command[:4] == ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE"]:
            return _completed_process("Cafe\\:Net:70:WPA2:*\nOpenNet:55:--:\n")
        raise AssertionError(f"Unexpected command: {command}")

    mocker.patch("rpi_usb_cloner.services.wifi._run_command", side_effect=fake_run)

    networks = wifi.list_networks()

    assert [network.ssid for network in networks] == ["Cafe:Net", "OpenNet"]
    assert [network.signal for network in networks] == [70, 55]
    assert networks[0].secured is True
    assert networks[0].in_use is True
    assert networks[1].secured is False


def test_list_networks_marks_open_vs_secured(mocker):
    """Test nmcli parsing distinguishes open from secured networks."""
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )

    def fake_run(command, check=True, redactions=None):
        if command[:2] == ["rfkill", "unblock"]:
            return _completed_process()
        if command[:3] == ["ip", "link", "set"]:
            return _completed_process()
        if command[:4] == ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE"]:
            return _completed_process(
                "SecuredNet:65:WPA2:*\n" "OpenNet:55:--:\n" "Hidden:::\n"
            )
        raise AssertionError(f"Unexpected command: {command}")

    mocker.patch("rpi_usb_cloner.services.wifi._run_command", side_effect=fake_run)

    networks = wifi.list_networks()

    assert [network.ssid for network in networks] == [
        "SecuredNet",
        "OpenNet",
        "Hidden",
    ]
    assert networks[0].secured is True
    assert networks[1].secured is False
    assert networks[2].secured is False


def test_list_networks_falls_back_to_iw_scan(mocker):
    """Test list_networks uses iw scan fallback when nmcli fails."""
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )

    def fake_run(command, check=True, redactions=None):
        if command[:2] == ["rfkill", "unblock"]:
            return _completed_process()
        if command[:3] == ["ip", "link", "set"]:
            return _completed_process()
        if command[:4] == ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE"]:
            raise subprocess.CalledProcessError(1, command, stderr="nmcli boom")
        if command[:2] == ["iwlist", "wlan0"]:
            return _completed_process(
                "Cell 01 - Address: AA:BB:CC:DD:EE:FF\n"
                '          ESSID:"FallbackNet"\n'
                "          Quality=70/70  Signal level=-40 dBm\n"
                "          Encryption key:on\n"
            )
        raise AssertionError(f"Unexpected command: {command}")

    mocker.patch("rpi_usb_cloner.services.wifi._run_command", side_effect=fake_run)
    mocker.patch(
        "rpi_usb_cloner.services.wifi.subprocess.run",
        return_value=_completed_process(""),
    )

    networks = wifi.list_networks()

    assert [network.ssid for network in networks] == ["FallbackNet"]
    assert networks[0].secured is True
    assert networks[0].signal == 100


def test_list_networks_iw_scan_parses_negative_signal(mocker):
    """Test iw scan parsing normalizes negative signal values."""
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )

    def fake_run(command, check=True, redactions=None):
        if command[:2] == ["rfkill", "unblock"]:
            return _completed_process()
        if command[:3] == ["ip", "link", "set"]:
            return _completed_process()
        if command[:4] == ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE"]:
            raise subprocess.CalledProcessError(1, command, stderr="nmcli boom")
        raise AssertionError(f"Unexpected command: {command}")

    mocker.patch("rpi_usb_cloner.services.wifi._run_command", side_effect=fake_run)
    mocker.patch(
        "rpi_usb_cloner.services.wifi.subprocess.run",
        return_value=_completed_process(
            "BSS 01:00:00:00:00:00(on wlan0)\n"
            "\tSSID:SignalNet\n"
            "\tsignal: -80.00 dBm\n"
            "\tRSN:\n"
        ),
    )

    networks = wifi.list_networks()

    assert [network.ssid for network in networks] == ["SignalNet"]
    assert networks[0].signal == 40
    assert networks[0].secured is True


def test_list_networks_iwlist_quality_parsing(mocker):
    """Test iwlist quality parsing returns computed signal percentage."""
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )

    def fake_run(command, check=True, redactions=None):
        if command[:2] == ["rfkill", "unblock"]:
            return _completed_process()
        if command[:3] == ["ip", "link", "set"]:
            return _completed_process()
        if command[:4] == ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE"]:
            raise subprocess.CalledProcessError(1, command, stderr="nmcli boom")
        if command[:2] == ["iwlist", "wlan0"]:
            return _completed_process(
                "Cell 01 - Address: AA:BB:CC:DD:EE:FF\n"
                '          ESSID:"QualityNet"\n'
                "          Quality=35/70\n"
            )
        raise AssertionError(f"Unexpected command: {command}")

    mocker.patch("rpi_usb_cloner.services.wifi._run_command", side_effect=fake_run)
    mocker.patch(
        "rpi_usb_cloner.services.wifi.subprocess.run",
        return_value=_completed_process(""),
    )

    networks = wifi.list_networks()

    assert [network.ssid for network in networks] == ["QualityNet"]
    assert networks[0].signal == 50
    assert networks[0].secured is False


def test_connect_rejects_invalid_ssid(mocker):
    """Test connect rejects blank or whitespace SSIDs."""
    errors: list[list[str]] = []

    def error_handler(lines):
        errors.append(list(lines))

    wifi.configure_wifi_helpers(error_handler=error_handler)
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )

    assert wifi.connect("   ") is False
    assert errors
    assert "SSID is required" in errors[0][1]


def test_connect_rejects_invalid_ssid_length_and_chars(mocker):
    """Test connect rejects SSIDs with invalid length or characters."""
    errors: list[list[str]] = []

    def error_handler(lines):
        errors.append(list(lines))

    wifi.configure_wifi_helpers(error_handler=error_handler)
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )
    run_mock = mocker.patch("rpi_usb_cloner.services.wifi._run_command")

    assert wifi.connect("A" * 33) is False
    assert wifi.connect("Bad\x00Name") is False
    assert len(errors) == 2
    run_mock.assert_not_called()


def test_connect_handles_subprocess_failure(mocker):
    """Test connect handles subprocess failures and reports errors."""
    errors: list[list[str]] = []

    def error_handler(lines):
        errors.append(list(lines))

    wifi.configure_wifi_helpers(error_handler=error_handler)
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )
    mocker.patch("rpi_usb_cloner.services.wifi.get_active_ssid", return_value=None)

    def failing_run(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["nmcli"], stderr="boom")

    mocker.patch("rpi_usb_cloner.services.wifi._run_command", side_effect=failing_run)

    assert wifi.connect("MyWifi") is False
    assert errors
    assert "Wi-Fi connect failed" in errors[0][1]


def test_connect_open_network_runs_nmcli(mocker):
    """Test connect uses open-network command when password omitted."""
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )
    mocker.patch("rpi_usb_cloner.services.wifi.get_active_ssid", return_value=None)
    run_mock = mocker.patch(
        "rpi_usb_cloner.services.wifi._run_command", return_value=_completed_process()
    )

    assert wifi.connect("OpenNet") is True

    run_mock.assert_called_once_with(
        ["nmcli", "dev", "wifi", "connect", "OpenNet", "ifname", "wlan0"]
    )


def test_connect_secure_network_updates_connection(mocker):
    """Test connect updates secured network configuration."""
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )
    mocker.patch("rpi_usb_cloner.services.wifi.get_active_ssid", return_value=None)

    def fake_run(command, check=True, redactions=None):
        if command[:4] == ["nmcli", "-t", "-f", "NAME"]:
            return _completed_process("SecureNet\n")
        return _completed_process()

    run_mock = mocker.patch(
        "rpi_usb_cloner.services.wifi._run_command", side_effect=fake_run
    )

    assert wifi.connect("SecureNet", password="secret") is True

    assert run_mock.call_args_list[1][0][0][:3] == ["nmcli", "connection", "modify"]
    assert run_mock.call_args_list[-1][0][0] == [
        "nmcli",
        "connection",
        "up",
        "SecureNet",
    ]


def test_connect_returns_true_when_already_connected(mocker):
    """Test connect short-circuits when already connected."""
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )
    mocker.patch("rpi_usb_cloner.services.wifi.get_active_ssid", return_value="Cafe")
    run_mock = mocker.patch("rpi_usb_cloner.services.wifi._run_command")

    assert wifi.connect("Cafe") is True

    run_mock.assert_not_called()


def test_disconnect_success(mocker):
    """Test disconnect returns True on success."""
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )
    run_mock = mocker.patch(
        "rpi_usb_cloner.services.wifi._run_command", return_value=_completed_process()
    )

    assert wifi.disconnect() is True
    run_mock.assert_called_once_with(["nmcli", "dev", "disconnect", "wlan0"])


def test_disconnect_failure_notifies_error(mocker):
    """Test disconnect returns False and notifies error on failure."""
    errors: list[list[str]] = []

    def error_handler(lines):
        errors.append(list(lines))

    wifi.configure_wifi_helpers(error_handler=error_handler)
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )

    def failing_run(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["nmcli"], stderr="boom")

    mocker.patch("rpi_usb_cloner.services.wifi._run_command", side_effect=failing_run)

    assert wifi.disconnect() is False
    assert errors
    assert "Wi-Fi disconnect failed" in errors[0][1]


def test_list_networks_handles_iw_timeout(mocker):
    """Test iw scan timeout notifies error and returns empty list."""
    errors: list[list[str]] = []

    def error_handler(lines):
        errors.append(list(lines))

    wifi.configure_wifi_helpers(error_handler=error_handler)
    mocker.patch(
        "rpi_usb_cloner.services.wifi._select_active_interface", return_value="wlan0"
    )

    def fake_run(command, check=True, redactions=None):
        if command[:2] == ["rfkill", "unblock"]:
            return _completed_process()
        if command[:3] == ["ip", "link", "set"]:
            return _completed_process()
        if command[:4] == ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE"]:
            raise subprocess.CalledProcessError(1, command, stderr="nmcli boom")
        raise AssertionError(f"Unexpected command: {command}")

    mocker.patch("rpi_usb_cloner.services.wifi._run_command", side_effect=fake_run)
    mocker.patch(
        "rpi_usb_cloner.services.wifi.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["iw"], timeout=10),
    )

    assert wifi.list_networks() == []
    assert errors


def test_get_status_cached_parses_nmcli_output(mocker):
    """Test nmcli status parsing returns connected status details."""
    mocker.patch(
        "rpi_usb_cloner.services.wifi._split_nmcli_line",
        side_effect=wifi._split_nmcli_line,
    )
    mocker.patch(
        "rpi_usb_cloner.services.wifi.get_ip_address", return_value="192.168.1.10"
    )
    mocker.patch("rpi_usb_cloner.services.wifi.get_active_ssid", return_value="HomeNet")

    def fake_run(command, check=True, redactions=None):
        if command[:4] == ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION"]:
            return _completed_process("wlan0:wifi:connected:HomeNet\n")
        if command[:4] == ["nmcli", "-g", "IP4.ADDRESS", "device"]:
            return _completed_process("192.168.1.10/24")
        raise AssertionError(f"Unexpected command: {command}")

    mocker.patch("rpi_usb_cloner.services.wifi._run_command", side_effect=fake_run)

    status = wifi.get_status_cached(ttl_s=0.0)

    assert status["connected"] is True
    assert status["ssid"] == "HomeNet"
    assert status["ip"] == "192.168.1.10"


def test_get_active_ssid_falls_back_to_iw_on_nmcli_error(mocker):
    """Test active SSID falls back to iw output when nmcli fails."""
    def fake_run(command, check=True, redactions=None):
        if command[:4] == ["nmcli", "-t", "-f", "ACTIVE,SSID,DEVICE"]:
            raise subprocess.CalledProcessError(1, command, stderr="nmcli boom")
        if command[:2] == ["iw", "dev"]:
            return _completed_process(
                "phy#0\n"
                "\tInterface wlan0\n"
                "\t\ttype managed\n"
                "\t\tssid BackupNet\n"
            )
        raise AssertionError(f"Unexpected command: {command}")

    mocker.patch("rpi_usb_cloner.services.wifi._run_command", side_effect=fake_run)

    assert wifi.get_active_ssid(interface="wlan0") == "BackupNet"
