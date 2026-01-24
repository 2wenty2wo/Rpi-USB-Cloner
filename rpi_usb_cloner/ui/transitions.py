from __future__ import annotations

import time
from typing import Optional

from PIL import Image

from rpi_usb_cloner.ui import display


def render_slide_transition(
    from_image: Image.Image,
    to_image: Image.Image,
    direction: str,
    frame_count: int,
    dirty_region: Optional[tuple[int, int, int, int]] = None,
    frame_delay: float = 0.04,
) -> None:
    """Render a horizontal slide transition between two images.

    Args:
        from_image: Starting frame (current screen).
        to_image: Ending frame (next screen).
        direction: "forward" (new screen slides in from right) or "back".
        frame_count: Number of frames to render.
        dirty_region: Optional bounding box (left, top, right, bottom) to update.
        frame_delay: Delay between frames in seconds.
    """
    context = display.get_display_context()
    width, height = context.width, context.height
    from_frame = from_image.convert("1")
    to_frame = to_image.convert("1")
    if from_frame.size != (width, height) or to_frame.size != (width, height):
        raise ValueError("Transition images must match display dimensions.")
    if frame_count <= 0:
        frame_count = 1
    if dirty_region is None:
        dirty_region = (0, 0, width, height)
    left, top, right, bottom = dirty_region
    dirty_width = max(0, right - left)
    dirty_height = max(0, bottom - top)
    direction = direction.lower()
    if direction not in {"forward", "back"}:
        direction = "forward"

    for index in range(1, frame_count + 1):
        shift = int(round(width * index / frame_count))
        if direction == "back":
            from_offset = shift
            to_offset = -width + shift
        else:
            from_offset = -shift
            to_offset = width - shift

        region = Image.new("1", (dirty_width, dirty_height), 0)
        region.paste(from_frame, (from_offset - left, -top))
        region.paste(to_frame, (to_offset - left, -top))
        with display._display_lock:
            context.image.paste(region, (left, top))
            context.disp.display(context.image)
            display.mark_display_dirty()
        if frame_delay > 0:
            time.sleep(frame_delay)
