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
    assert networks[0].secured is True
    assert networks[0].in_use is True
    assert networks[1].secured is False


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
