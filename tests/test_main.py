"""Tests for main application module."""

from rpi_usb_cloner import main


# ==============================================================================
# Helper Function Tests
# ==============================================================================


class TestMainHelpers:
    """Test helper functions in main.py."""

    def test_get_device_name_from_dict(self):
        """Test extracting name from device dict."""
        device = {"name": "sda", "size": 100}
        assert main.get_device_name_from_dict(device) == "sda"
        assert main.get_device_name_from_dict({}) == ""

    def test_get_size_from_dict(self):
        """Test extracting size from device dict."""
        device = {"name": "sda", "size": 123456}
        assert main.get_size_from_dict(device) == 123456
        assert main.get_size_from_dict({}) == 0

    def test_get_vendor_from_dict(self):
        """Test extracting vendor from device dict."""
        device = {"vendor": "SanDisk", "model": "Cruzer"}
        assert main.get_vendor_from_dict(device) == "SanDisk"
        assert main.get_vendor_from_dict({}) == ""

    def test_get_model_from_dict(self):
        """Test extracting model from device dict."""
        device = {"vendor": "SanDisk", "model": "Cruzer"}
        assert main.get_model_from_dict(device) == "Cruzer"
        assert main.get_model_from_dict({}) == ""
