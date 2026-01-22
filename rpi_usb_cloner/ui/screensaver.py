import random
import time
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps, ImageSequence

from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.ui import display


SCREENSAVER_DIR = Path(__file__).resolve().parent / "assets" / "gifs"
DEFAULT_FRAME_DURATION_MS = 100
INPUT_POLL_INTERVAL = 0.02


def _list_gif_paths(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".gif"
    )


def list_available_gifs(directory: Path = SCREENSAVER_DIR) -> list[Path]:
    return _list_gif_paths(directory)


def _render_placeholder(context: display.DisplayContext, lines: list[str]) -> None:
    with display._display_lock:
        context.draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        y = context.top
        for line in lines:
            context.draw.text((0, y), line, font=context.fontmain, fill=255)
            y += 10
        context.disp.display(context.image)
        display.mark_display_dirty()


def _prepare_frame(frame: Image.Image, size: tuple[int, int]) -> Image.Image:
    if frame.mode not in ("RGB", "L", "1"):
        frame = frame.convert("RGB")
    fitted = ImageOps.fit(
        frame, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
    )
    if fitted.mode != "1":
        fitted = fitted.convert("1")
    return fitted


def _sleep_with_input_check(
    duration_s: float, input_checker: Callable[[], bool]
) -> bool:
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        if input_checker():
            return True
        time.sleep(INPUT_POLL_INTERVAL)
    return False


def _default_input_checker() -> bool:
    return any(gpio.is_pressed(pin) for pin in gpio.PINS)


def _frame_duration_seconds(frame: Image.Image) -> float:
    duration_ms = frame.info.get("duration", DEFAULT_FRAME_DURATION_MS)
    if not isinstance(duration_ms, (int, float)) or duration_ms <= 0:
        duration_ms = DEFAULT_FRAME_DURATION_MS
    return duration_ms / 1000.0


def play_screensaver(
    context: display.DisplayContext,
    *,
    gif_directory: Path = SCREENSAVER_DIR,
    selected_gif: Path | str | None = None,
    screensaver_mode: str = "random",
    input_checker: Callable[[], bool] = _default_input_checker,
    rng: random.Random | None = None,
) -> bool:
    gif_paths = _list_gif_paths(gif_directory)
    chosen_path: Path | None = None
    if screensaver_mode == "selected" and selected_gif:
        candidate = Path(selected_gif)
        if not candidate.is_absolute():
            candidate = gif_directory / candidate
        if candidate.exists():
            chosen_path = candidate
    if chosen_path is None and gif_paths:
        rng = rng or random.Random()
        chosen_path = rng.choice(gif_paths)
    if chosen_path is None:
        _render_placeholder(
            context,
            ["No GIFs found", "Add *.gif to", "ui/assets/gifs"],
        )
        while not input_checker():
            time.sleep(INPUT_POLL_INTERVAL)
        return True
    with Image.open(chosen_path) as image:
        while True:
            for frame in ImageSequence.Iterator(image):
                if input_checker():
                    return True
                prepared = _prepare_frame(frame, (context.width, context.height))
                with display._display_lock:
                    context.image.paste(prepared)
                    context.disp.display(context.image)
                    display.mark_display_dirty()
                if _sleep_with_input_check(
                    _frame_duration_seconds(frame), input_checker
                ):
                    return True
            image.seek(0)
    return False
