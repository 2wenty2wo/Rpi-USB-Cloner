"""Tests for UI display initialization fallbacks."""

from unittest.mock import Mock

from rpi_usb_cloner.ui import display


class FakeSplash:
    """Minimal image-like object for splash screen testing."""

    def __init__(self, size):
        self.size = size
        self.resize_called_with = None

    def convert(self, _mode):
        return self

    def resize(self, size):
        self.resize_called_with = size
        self.size = size
        return self


def test_init_display_falls_back_to_default_fonts(mocker):
    """Display initialization should fall back to default fonts."""
    fake_disp = Mock()
    fake_disp.width = 128
    fake_disp.height = 64
    mocker.patch("rpi_usb_cloner.ui.display.i2c", return_value=Mock())
    mocker.patch("rpi_usb_cloner.ui.display.ssd1306", return_value=fake_disp)
    mocker.patch("rpi_usb_cloner.ui.display.time.sleep")
    splash = FakeSplash((10, 10))
    mocker.patch("rpi_usb_cloner.ui.display.Image.open", return_value=splash)
    mocker.patch("rpi_usb_cloner.ui.display.Image.new", return_value=Mock())
    mocker.patch("rpi_usb_cloner.ui.display.ImageDraw.Draw", return_value=Mock())

    default_font = Mock(name="default_font")
    fontcopy = Mock(name="fontcopy")
    fontinsert = Mock(name="fontinsert")
    mocker.patch(
        "rpi_usb_cloner.ui.display.ImageFont.load_default",
        return_value=default_font,
    )
    mocker.patch(
        "rpi_usb_cloner.ui.display.ImageFont.truetype",
        side_effect=[
            fontcopy,
            fontinsert,
            OSError("missing font"),
            OSError("missing font"),
        ],
    )

    context = display.init_display()

    assert context.fonts["items"] is default_font
    assert context.fonts["items_bold"] is default_font
    assert context.fontcopy is fontcopy
    assert context.fontinsert is fontinsert
    assert splash.resize_called_with == (fake_disp.width, fake_disp.height)
