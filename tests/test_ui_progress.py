"""Tests for UI progress screen rendering logic."""

from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image, ImageDraw, ImageFont

from rpi_usb_cloner.storage.clone.progress import format_eta
from rpi_usb_cloner.ui.screens import progress as progress_screen


def _build_display_context(width: int = 128, height: int = 64) -> SimpleNamespace:
    image = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    return SimpleNamespace(
        disp=Mock(),
        draw=draw,
        image=image,
        fonts={"title": font, "items": font, "footer": font},
        width=width,
        height=height,
        x=0,
        top=0,
        bottom=height - 1,
        fontcopy=font,
        fontinsert=font,
        fontdisks=font,
        fontmain=font,
    )


def test_progress_percent_text_for_normal_ratio(mocker):
    """Percent text should reflect the progress ratio."""
    context = _build_display_context()
    mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=context)
    text_calls = []
    original_text = context.draw.text

    def spy_text(position, text, *args, **kwargs):
        text_calls.append(text)
        return original_text(position, text, *args, **kwargs)

    mocker.patch.object(context.draw, "text", side_effect=spy_text)
    progress_screen.render_progress_screen(
        "COPYING", ["Working..."], progress_ratio=0.5
    )
    assert "50.0%" in text_calls


def test_progress_percent_text_for_zero_ratio(mocker):
    """Zero progress should render 0.0%."""
    context = _build_display_context()
    mocker.patch("rpi_usb_cloner.ui.display.get_display_context", return_value=context)
    text_calls = []
    original_text = context.draw.text

    def spy_text(position, text, *args, **kwargs):
        text_calls.append(text)
        return original_text(position, text, *args, **kwargs)

    mocker.patch.object(context.draw, "text", side_effect=spy_text)
    progress_screen.render_progress_screen(
        "COPYING", ["Working..."], progress_ratio=0.0
    )
    assert "0.0%" in text_calls


def test_eta_formatting_edge_cases():
    """ETA formatting should handle edge cases gracefully."""
    assert format_eta(0) == "00:00"
    assert format_eta(59) == "00:59"
    assert format_eta(3600) == "1:00:00"
    assert format_eta(-1) is None
