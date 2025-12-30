from dataclasses import dataclass
from typing import List, Optional

from PIL import ImageFont


@dataclass
class MenuItem:
    lines: List[str]


@dataclass
class Menu:
    items: List[MenuItem]
    selected_index: int = 0
    title: Optional[str] = None
    title_font: Optional[ImageFont.ImageFont] = None
    footer: Optional[List[str]] = None
    footer_selected_index: Optional[int] = None
    footer_positions: Optional[List[int]] = None
    content_top: Optional[int] = None
    items_font: Optional[ImageFont.ImageFont] = None


def render_menu(menu, draw, width, height, fonts, *, x, top):
    draw.rectangle((0, 0, width, height), outline=0, fill=0)
    current_y = top
    if menu.title:
        title_font = menu.title_font or fonts["title"]
        title_bbox = draw.textbbox((x - 11, current_y), menu.title, font=title_font)
        draw.text((x - 11, current_y), menu.title, font=title_font, fill=255)
        title_height = title_bbox[3] - title_bbox[1]
        current_y += title_height + 2
    if menu.content_top is not None:
        current_y = menu.content_top

    items_font = menu.items_font or fonts["items"]
    line_height = 8
    try:
        bbox = items_font.getbbox("Ag")
        line_height = max(bbox[3] - bbox[1], line_height)
    except AttributeError:
        if hasattr(items_font, "getmetrics"):
            ascent, descent = items_font.getmetrics()
            line_height = max(ascent + descent, line_height)

    for item_index, item in enumerate(menu.items):
        lines = item.lines
        row_height = max(len(lines), 1) * line_height + 4
        row_top = current_y
        text_y_offset = (row_height - len(lines) * line_height) // 2
        is_selected = item_index == menu.selected_index
        if is_selected:
            draw.rectangle((0, row_top - 1, width, row_top + row_height - 1), outline=0, fill=1)
        for line_index, line in enumerate(lines):
            text_color = 0 if is_selected else 255
            draw.text(
                (x - 11, row_top + text_y_offset + line_index * line_height),
                line,
                font=items_font,
                fill=text_color,
            )
        current_y += row_height

    if menu.footer:
        footer_font = fonts["footer"]
        footer_y = height - 15
        positions = menu.footer_positions
        if positions is None:
            spacing = width // (len(menu.footer) + 1)
            positions = [(spacing * (index + 1)) - 10 for index in range(len(menu.footer))]
        for footer_index, label in enumerate(menu.footer):
            x_pos = positions[footer_index]
            text_bbox = draw.textbbox((x_pos, footer_y), label, font=footer_font)
            if menu.footer_selected_index is not None and footer_index == menu.footer_selected_index:
                draw.rectangle(
                    (text_bbox[0] - 3, text_bbox[1] - 2, text_bbox[2] + 3, text_bbox[3] + 2),
                    outline=0,
                    fill=1,
                )
                draw.text((x_pos, footer_y), label, font=footer_font, fill=0)
            else:
                draw.text((x_pos, footer_y), label, font=footer_font, fill=255)
