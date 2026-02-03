from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw

from rpi_usb_cloner.ui import display


@dataclass(frozen=True)
class HeaderLayout:
    content_top: int
    icon_width: int
    icon_height: int


def _measure_text_height(font: display.Font, text: str) -> int:
    try:
        bbox = font.getbbox(text)
    except AttributeError:
        return display._get_line_height(font)
    return max(0, bbox[3] - bbox[1])


def render_header(
    *,
    title: str | None,
    header_lines: Iterable[str] | None = None,
    title_font: display.Font | None = None,
    header_lines_font: display.Font | None = None,
    icon: str | None = None,
    icon_font: display.Font | None = None,
    extra_gap: int = 2,
    left_margin: int | None = None,
    max_width: int | None = None,
    content_top: int | None = None,
    draw: ImageDraw.ImageDraw | None = None,
    image: Image.Image | None = None,
    render: bool = True,
) -> HeaderLayout:
    context = display.get_display_context()
    draw = draw or context.draw
    image = image or context.image
    left_margin = context.x - 11 if left_margin is None else left_margin
    header_font = title_font or context.fonts.get("title", context.fontdisks)

    icon_width = 0
    icon_line_height = 0
    icon_image = None
    is_image_icon = False
    icon_ascent = icon_descent = 0

    if icon:
        if icon.endswith(".png"):
            is_image_icon = True
            try:
                icon_path = (
                    Path(icon)
                    if Path(icon).is_absolute()
                    else display.ASSETS_DIR / icon
                )
                icon_image = Image.open(icon_path).convert("1")
                icon_width = icon_image.width
                icon_ascent = icon_image.height
                icon_descent = 0
            except (OSError, FileNotFoundError):
                is_image_icon = False
                icon_image = None
                icon_width = 0
                icon = None
        else:
            icon_font = icon_font or display._get_lucide_font()
            icon_bbox = icon_font.getbbox(icon)
            icon_width = icon_bbox[2] - icon_bbox[0]
            getmetrics = getattr(icon_font, "getmetrics", None)
            if callable(getmetrics):
                icon_ascent, icon_descent = getmetrics()
            else:
                icon_ascent = max(0, icon_bbox[3] - icon_bbox[1])
                icon_descent = 0

    icon_line_height = icon_ascent + icon_descent

    title_x = left_margin + (
        icon_width + display.TITLE_ICON_PADDING if icon_width else 0
    )
    title_text = ""
    available_width = 0
    title_line_height = 0
    if title:
        available_width = (
            max_width if max_width is not None else max(0, context.width - title_x - 1)
        )
        if render:
            title_text = display._truncate_text(
                draw, title, header_font, available_width
            )
        else:
            title_text = title
        if title_text:
            title_line_height = _measure_text_height(header_font, title_text)

    if not title_text:
        current_y = context.top
        if content_top is not None:
            current_y = max(current_y, content_top)
    else:
        line_height = max(title_line_height, icon_line_height)
        if render:
            title_y = context.top + display.TITLE_TEXT_Y_OFFSET
            draw.text((title_x, title_y), title_text, font=header_font, fill=255)
            if icon:
                if is_image_icon and icon_image:
                    icon_y = 0
                    image.paste(icon_image, (left_margin, icon_y))
                else:
                    icon_y = -1
                    draw.text((left_margin, icon_y), icon, font=icon_font, fill=255)
        current_y = context.top + line_height + display.TITLE_PADDING + extra_gap
        if content_top is not None:
            current_y = max(current_y, content_top)

    if header_lines:
        lines_font = header_lines_font or context.fontdisks
        left_margin = context.x - 11 if left_margin is None else left_margin
        available_width = max(0, context.width - left_margin)
        wrapped_lines = display._wrap_lines_to_width(
            list(header_lines),
            lines_font,
            available_width,
        )
        line_height = display._get_line_height(lines_font)
        line_step = line_height + 2
        available_height = context.height - current_y - 2
        lines_per_page = max(1, available_height // line_step)
        total_pages = max(
            1,
            (len(wrapped_lines) + lines_per_page - 1) // lines_per_page,
        )
        page_lines = wrapped_lines[:lines_per_page]
        if render:
            for line in page_lines:
                draw.text((left_margin, current_y), line, font=lines_font, fill=255)
                current_y += line_step
            if total_pages > 1:
                indicator = f"1/{total_pages}>"
                indicator_bbox = draw.textbbox((0, 0), indicator, font=lines_font)
                indicator_width = indicator_bbox[2] - indicator_bbox[0]
                indicator_height = indicator_bbox[3] - indicator_bbox[1]
                draw.text(
                    (
                        context.width - indicator_width - 2,
                        context.height - indicator_height - 2,
                    ),
                    indicator,
                    font=lines_font,
                    fill=255,
                )
        else:
            current_y += len(page_lines) * line_step

    return HeaderLayout(
        content_top=current_y,
        icon_width=icon_width,
        icon_height=icon_line_height if title_text else 0,
    )
