"""Tests for Bluetooth QR code screen.

These tests cover the QR code display screen functionality.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

pytestmark = [
    pytest.mark.unit,
]


class TestQRCodeGeneration:
    """Test QR code matrix generation."""

    def test_generate_qr_matrix_fallback(self):
        """Test QR matrix generation without qrcode library."""
        from rpi_usb_cloner.ui.screens.qr_code import _generate_qr_matrix

        # Test with qrcode library unavailable (ImportError)
        with patch.dict("sys.modules", {"qrcode": None}):
            matrix = _generate_qr_matrix("test data", version=2)

        # Should return a fallback matrix
        assert isinstance(matrix, list)
        assert len(matrix) > 0
        assert len(matrix[0]) > 0
        # Should be square
        assert len(matrix) == len(matrix[0])

    def test_generate_qr_matrix_with_library(self):
        """Test QR matrix generation with qrcode library available."""
        from rpi_usb_cloner.ui.screens.qr_code import _generate_qr_matrix

        # Mock the qrcode module
        mock_qr = MagicMock()
        mock_modules = [
            [True, False, True],
            [False, True, False],
            [True, False, True],
        ]
        mock_qr.QRCode.return_value.modules = mock_modules

        with patch.dict("sys.modules", {"qrcode": mock_qr}):
            matrix = _generate_qr_matrix("test data", version=2)

        assert matrix == mock_modules


class TestScaleMatrix:
    """Test matrix scaling function."""

    def test_scale_matrix_unchanged(self):
        """Test scaling by 1 returns same matrix."""
        from rpi_usb_cloner.ui.screens.qr_code import _scale_matrix

        matrix = [[True, False], [False, True]]
        result = _scale_matrix(matrix, 1)

        assert result == matrix

    def test_scale_matrix_double(self):
        """Test scaling by 2 doubles size."""
        from rpi_usb_cloner.ui.screens.qr_code import _scale_matrix

        matrix = [[True, False], [False, True]]
        result = _scale_matrix(matrix, 2)

        # Original 2x2 becomes 4x4
        assert len(result) == 4
        assert len(result[0]) == 4


class TestBluetoothQRScreen:
    """Test Bluetooth QR code screen rendering."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock display context."""
        context = MagicMock()
        context.fontdisks = MagicMock()
        context.disp = MagicMock()
        return context

    @pytest.fixture
    def mock_app_context(self):
        """Create a mock app context."""
        context = MagicMock()
        context.current_screen_image = None
        return context

    @patch("rpi_usb_cloner.ui.screens.qr_code.generate_qr_data")
    def test_render_with_error(self, mock_generate_data, mock_context, mock_app_context):
        """Test rendering when Bluetooth is disabled."""
        from rpi_usb_cloner.ui.screens.qr_code import render_bluetooth_qr_screen

        mock_generate_data.return_value = {"error": "Bluetooth not enabled"}

        render_bluetooth_qr_screen(mock_app_context, mock_context)

        # Should display error message
        mock_context.disp.display.assert_called_once()

    @patch("rpi_usb_cloner.ui.screens.qr_code.generate_qr_data")
    @patch("rpi_usb_cloner.ui.screens.qr_code._generate_qr_matrix")
    def test_render_success(
        self, mock_generate_matrix, mock_generate_data, mock_context, mock_app_context
    ):
        """Test successful QR screen rendering."""
        from rpi_usb_cloner.ui.screens.qr_code import render_bluetooth_qr_screen

        mock_generate_data.return_value = {
            "device_name": "RPI-USB-CLONER",
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "pin": "123456",
            "web_url": "http://192.168.50.1:8000",
        }
        # Simple 5x5 QR matrix
        mock_generate_matrix.return_value = [[True] * 25 for _ in range(25)]

        render_bluetooth_qr_screen(mock_app_context, mock_context)

        mock_context.disp.display.assert_called_once()


class TestBluetoothStatusScreen:
    """Test Bluetooth status screen rendering."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock display context."""
        context = MagicMock()
        context.fontdisks = MagicMock()
        context.disp = MagicMock()
        return context

    @pytest.fixture
    def mock_app_context(self):
        """Create a mock app context."""
        context = MagicMock()
        context.current_screen_image = None
        return context

    @patch("rpi_usb_cloner.ui.screens.qr_code.get_bluetooth_status")
    @patch("rpi_usb_cloner.ui.screens.qr_code.get_trusted_bluetooth_devices")
    def test_render_disabled(self, mock_get_trusted, mock_get_status, mock_context, mock_app_context):
        """Test status screen when Bluetooth is disabled."""
        from rpi_usb_cloner.ui.screens.qr_code import render_bluetooth_status_screen

        mock_status = MagicMock()
        mock_status.enabled = False
        mock_status.connected = False
        mock_get_status.return_value = mock_status
        mock_get_trusted.return_value = []

        render_bluetooth_status_screen(mock_app_context, mock_context)

        # Should display error message
        mock_context.disp.display.assert_called_once()

    @patch("rpi_usb_cloner.ui.screens.qr_code.get_bluetooth_status")
    @patch("rpi_usb_cloner.ui.screens.qr_code.get_trusted_bluetooth_devices")
    def test_render_connected(self, mock_get_trusted, mock_get_status, mock_context, mock_app_context):
        """Test status screen when Bluetooth is connected."""
        from rpi_usb_cloner.ui.screens.qr_code import render_bluetooth_status_screen

        mock_status = MagicMock()
        mock_status.enabled = True
        mock_status.connected = True
        mock_status.mac_address = "AA:BB:CC:DD:EE:FF"
        mock_status.pin = "123456"
        mock_status.ip_address = "192.168.50.1"
        mock_status.connected_device = "iPhone (AA:BB:CC:DD:EE:FF)"
        mock_get_status.return_value = mock_status
        mock_get_trusted.return_value = []

        render_bluetooth_status_screen(mock_app_context, mock_context)

        mock_context.disp.display.assert_called_once()

    @patch("rpi_usb_cloner.ui.screens.qr_code.get_bluetooth_status")
    @patch("rpi_usb_cloner.ui.screens.qr_code.get_trusted_bluetooth_devices")
    def test_render_waiting(self, mock_get_trusted, mock_get_status, mock_context, mock_app_context):
        """Test status screen when waiting for connection."""
        from rpi_usb_cloner.ui.screens.qr_code import render_bluetooth_status_screen

        mock_status = MagicMock()
        mock_status.enabled = True
        mock_status.connected = False
        mock_status.mac_address = "AA:BB:CC:DD:EE:FF"
        mock_status.pin = "123456"
        mock_status.ip_address = "192.168.50.1"
        mock_status.connected_device = None
        mock_get_status.return_value = mock_status
        mock_get_trusted.return_value = []

        render_bluetooth_status_screen(mock_app_context, mock_context)

        mock_context.disp.display.assert_called_once()
