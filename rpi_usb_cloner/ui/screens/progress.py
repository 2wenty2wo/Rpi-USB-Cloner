"""Progress screen rendering functions."""

import time
from typing import Iterable, Optional

from PIL import Image, ImageDraw, ImageFont

from rpi_usb_cloner.ui import display, menus


def render_progress_screen(
    title: str,
    lines: Iterable[str],
    *,
    progress_ratio: Optional[float] = None,
    animate: bool = False,
    title_icon: Optional[str] = None,
    title_icon_font: Optional[ImageFont.ImageFont] = None,
) -> None:
    context = display.get_display_context()
    title_font = context.fonts.get("title", context.fontdisks)
    body_font = context.fontdisks
    content_top = menus.get_standard_content_top(
        title,
        title_font=title_font,
        title_icon=title_icon,
        title_icon_font=title_icon_font,
    )
    wrapped_lines = display._wrap_lines_to_width(
        list(lines),
        body_font,
        context.width - 8,
    )
    line_height = display._get_line_height(body_font)
    line_step = line_height + 2
    text_height = max(line_height, len(wrapped_lines) * line_step - 2)
    bar_height = max(10, line_height + 4)
    bar_width = context.width - 16
    bar_y = int(content_top + (context.height - content_top) * 0.65)
    text_area_height = max(0, bar_y - content_top - 6)
    text_start_y = content_top + max(0, (text_area_height - text_height) // 2)
    text_bottom = text_start_y + text_height
    min_bar_y = int(text_bottom + 6)
    max_bar_y = context.height - bar_height - 4
    bar_y = max(min_bar_y, min(bar_y, max_bar_y))
    bar_x = int((context.width - bar_width) / 2)

    def render_frame(current_ratio: Optional[float], phase: float = 0.0) -> None:
        draw = context.draw
        draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
        if title:
            if title_icon:
                display.draw_title_with_icon(
                    title,
                    title_font=title_font,
                    icon=title_icon,
                    icon_font=title_icon_font,
                    extra_gap=2,
                    left_margin=context.x - 11,
                    draw=draw,
                )
            else:
                draw.text((context.x - 11, context.top), title, font=title_font, fill=255)

        current_y = text_start_y
        for line in wrapped_lines:
            text_width = display._measure_text_width(draw, line, body_font)
            line_x = int((context.width - text_width) / 2)
            draw.text((line_x, current_y), line, font=body_font, fill=255)
            current_y += line_step

        bar_rect = (bar_x, bar_y, bar_x + bar_width, bar_y + bar_height)
        draw.rectangle(bar_rect, outline=255, fill=0)

        inner_left = bar_x + 1
        inner_right = bar_x + bar_width - 1
        inner_width = max(0, inner_right - inner_left)
        inner_top = bar_y + 1
        inner_bottom = bar_y + bar_height - 1
        if inner_width <= 0 or inner_bottom <= inner_top:
            context.disp.display(context.image)
            return

        if current_ratio is None:
            window_width = max(6, int(inner_width * 0.25))
            travel = max(1, inner_width - window_width)
            offset = int(travel * phase)
            fill_left = inner_left + offset
            fill_right = fill_left + window_width
        else:
            clamped = max(0.0, min(1.0, float(current_ratio)))
            fill_right = inner_left + int(inner_width * clamped)
            fill_left = inner_left

        if fill_right > fill_left:
            draw.rectangle(
                (fill_left, inner_top, fill_right, inner_bottom),
                outline=255,
                fill=255,
            )

        # Draw percentage text centered on the progress bar with color inversion
        if current_ratio is not None:
            percent_text = f"{current_ratio * 100:.1f}%"
            percent_font = body_font

            # Calculate text dimensions and center position
            text_bbox = draw.textbbox((0, 0), percent_text, font=percent_font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            # Center the text on the progress bar
            text_x = bar_x + (bar_width - text_width) // 2
            text_y = bar_y + (bar_height - text_height) // 2 - text_bbox[1]

            # Draw text in two parts with different colors for filled/unfilled regions
            # Part 1: Draw white text on the unfilled (right) portion
            if fill_right < text_x + text_width:
                draw.text((text_x, text_y), percent_text, font=percent_font, fill=255)

            # Part 2: Draw black text on the filled (left) portion
            if fill_right > text_x:
                # Create a temporary image to draw the black text
                temp_img = Image.new('1', (context.width, context.height), 0)
                temp_draw = ImageDraw.Draw(temp_img)
                temp_draw.text((text_x, text_y), percent_text, font=percent_font, fill=255)

                # Copy only the pixels where the filled bar overlaps with text
                pixels = context.image.load()
                temp_pixels = temp_img.load()
                text_right = text_x + text_width
                text_bottom = text_y + text_height
                for y in range(max(0, text_y), min(context.height, text_bottom + 1)):
                    for x in range(max(0, text_x), min(context.width, text_right)):
                        if temp_pixels[x, y] and x < fill_right:  # Text pixel in filled region
                            pixels[x, y] = 0  # Draw in black

        context.disp.display(context.image)

    if not animate:
        render_frame(progress_ratio)
        return

    if callable(progress_ratio):
        phase = 0.0
        while True:
            current_ratio = progress_ratio()
            render_frame(current_ratio, phase=phase)
            if current_ratio is not None and current_ratio >= 1:
                return
            phase = (phase + 0.08) % 1.0
            time.sleep(0.08)
    elif progress_ratio is None:
        phase = 0.0
        while True:
            render_frame(None, phase=phase)
            phase = (phase + 0.08) % 1.0
            time.sleep(0.08)
    else:
        render_frame(progress_ratio)
