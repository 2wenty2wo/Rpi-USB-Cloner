import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306


@dataclass
class DisplayContext:
    disp: ssd1306
    width: int
    height: int
    image: Image.Image
    draw: ImageDraw.ImageDraw
    fonts: Dict[str, ImageFont.ImageFont]
    font_insert: ImageFont.ImageFont
    font_disks: ImageFont.ImageFont
    font_main: ImageFont.ImageFont
    x: int
    top: int
    bottom: int


def init_display(
    splash_path: str = "splash.png",
    font_copy_path: str = "rainyhearts.ttf",
    font_insert_path: str = "slkscr.ttf",
    font_disks_path: str = "slkscr.ttf",
    address: int = 0x3C,
    port: int = 1,
    splash_delay: float = 1.5,
) -> DisplayContext:
    serial = i2c(port=port, address=address)
    disp = ssd1306(serial)
    disp.clear()
    width = disp.width
    height = disp.height
    splash = Image.open(splash_path).convert("1")
    if splash.size != (width, height):
        splash = splash.resize((width, height))
    disp.display(splash)
    time.sleep(splash_delay)
    image = Image.new("1", (width, height))
    draw = ImageDraw.Draw(image)
    font_copy = ImageFont.truetype(font_copy_path, 16)
    font_insert = ImageFont.truetype(font_insert_path, 16)
    font_disks = ImageFont.truetype(font_disks_path, 8)
    font_main = ImageFont.load_default()
    fonts = {
        "title": font_disks,
        "items": font_disks,
        "footer": font_copy,
    }
    x = 12
    padding = -2
    top = padding
    bottom = height - padding
    return DisplayContext(
        disp=disp,
        width=width,
        height=height,
        image=image,
        draw=draw,
        fonts=fonts,
        font_insert=font_insert,
        font_disks=font_disks,
        font_main=font_main,
        x=x,
        top=top,
        bottom=bottom,
    )


def clear_display(context: DisplayContext) -> None:
    context.disp.clear()


def display_image(context: DisplayContext) -> None:
    context.disp.display(context.image)


def render_menu(menu, context: DisplayContext) -> None:
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    current_y = context.top
    if menu.title:
        title_font = menu.title_font or context.fonts["title"]
        title_bbox = draw.textbbox((context.x - 11, current_y), menu.title, font=title_font)
        draw.text((context.x - 11, current_y), menu.title, font=title_font, fill=255)
        title_height = title_bbox[3] - title_bbox[1]
        current_y += title_height + 2
    if menu.content_top is not None:
        current_y = menu.content_top

    items_font = menu.items_font or context.fonts["items"]
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
            draw.rectangle(
                (0, row_top - 1, context.width, row_top + row_height - 1),
                outline=0,
                fill=1,
            )
        for line_index, line in enumerate(lines):
            text_color = 0 if is_selected else 255
            draw.text(
                (context.x - 11, row_top + text_y_offset + line_index * line_height),
                line,
                font=items_font,
                fill=text_color,
            )
        current_y += row_height

    if menu.footer:
        footer_font = context.fonts["footer"]
        footer_y = context.height - 15
        positions = menu.footer_positions
        if positions is None:
            spacing = context.width // (len(menu.footer) + 1)
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


def display_lines(
    context: DisplayContext,
    lines: List[str],
    font: Optional[ImageFont.ImageFont] = None,
) -> None:
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    y = context.top
    selected_font = font or context.font_disks
    for line in lines[:6]:
        draw.text((context.x - 11, y), line, font=selected_font, fill=255)
        y += 10
    display_image(context)


def format_progress_display(
    title,
    device,
    mode,
    bytes_copied,
    total_bytes,
    percent,
    rate,
    eta,
    spinner=None,
):
    lines = []
    if title:
        title_line = title
        if spinner:
            title_line = f"{title} {spinner}"
        lines.append(title_line)
    if device:
        lines.append(device)
    if mode:
        lines.append(f"Mode {mode}")
    if bytes_copied is not None:
        percent_display = ""
        if total_bytes:
            percent_display = f"{(bytes_copied / total_bytes) * 100:.1f}%"
        elif percent is not None:
            percent_display = f"{percent:.1f}%"
        written_line = f"Wrote {human_size(bytes_copied)}"
        if percent_display:
            written_line = f"{written_line} {percent_display}"
        lines.append(written_line)
    elif percent is not None:
        lines.append(f"{percent:.1f}%")
    else:
        lines.append("Working...")
    if rate:
        rate_line = f"{human_size(rate)}/s"
        if eta:
            rate_line = f"{rate_line} ETA {eta}"
        lines.append(rate_line)
    return lines[:6]


def human_size(size_bytes):
    if size_bytes is None:
        return "0B"
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}PB"
