import time
from dataclasses import dataclass
from io import BytesIO
from typing import Dict, List, Optional

import cairosvg
from PIL import Image, ImageFont

from rpi_usb_cloner.hardware.gpio import (
    PIN_A,
    PIN_B,
    PIN_C,
    PIN_D,
    PIN_L,
    PIN_R,
    PIN_U,
    read_button,
)
from rpi_usb_cloner.ui import display, menus

KEY_SPACE = "SPACE"
KEY_BACKSPACE = "BACK"
KEY_CONFIRM = "OK"
KEY_CANCEL = "CANCEL"
KEY_SHIFT = "SHIFT"


@dataclass(frozen=True)
class KeyboardLayout:
    lower: List[str]
    upper: List[str]
    numbers: List[str]
    symbols: List[str]

    def get_keys(self, mode: str) -> List[str]:
        if mode == "upper":
            return self.upper
        if mode == "symbols":
            return self.symbols
        if mode == "numbers":
            return self.numbers
        return self.lower


DEFAULT_LAYOUT = KeyboardLayout(
    numbers=[
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
        KEY_SPACE,
    ],
    lower=[
        "a", "b", "c", "d", "e", "f", "g", "h", "i", "j",
        "k", "l", "m", "n", "o", "p", "q", "r", "s", "t",
        "u", "v", "w", "x", "y", "z",
        KEY_SPACE,
    ],
    upper=[
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
        "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
        "U", "V", "W", "X", "Y", "Z",
        KEY_SPACE,
    ],
    symbols=[
        "!", "@", "#", "$", "%", "^", "&", "*", "(", ")",
        "-", "_", "+", "=", "[", "]", "{", "}", "\\", "|",
        ";", ":", "'", "\"", "<", ">", ",", ".", "?", "/",
        "`", "~",
        KEY_SPACE,
    ],
)

_keyboard_fonts: Optional[tuple[ImageFont.ImageFont, ImageFont.ImageFont]] = None
_backspace_icon_cache: Dict[int, Image.Image] = {}


def _get_keyboard_fonts() -> tuple[ImageFont.ImageFont, ImageFont.ImageFont]:
    global _keyboard_fonts
    if _keyboard_fonts is not None:
        return _keyboard_fonts
    context = display.get_display_context()
    try:
        input_font = ImageFont.truetype(display.ASSETS_DIR / "fonts" / "dogicapixel.ttf", 8)
    except OSError:
        input_font = context.fontdisks
    try:
        key_font = ImageFont.truetype(display.ASSETS_DIR / "fonts" / "dogicapixel.ttf", 8)
    except OSError:
        key_font = input_font
    _keyboard_fonts = (input_font, key_font)
    return _keyboard_fonts


def _get_line_height(font, min_height=8):
    line_height = min_height
    try:
        bbox = font.getbbox("Ag")
        line_height = max(bbox[3] - bbox[1], line_height)
    except AttributeError:
        if hasattr(font, "getmetrics"):
            ascent, descent = font.getmetrics()
            line_height = max(ascent + descent, line_height)
    return line_height


def _truncate_text(draw, text: str, font, max_width: int) -> str:
    bbox = draw.textbbox((0, 0), text, font=font)
    if bbox[2] - bbox[0] <= max_width:
        return text
    ellipsis = "…"
    truncated = text
    while truncated:
        candidate = f"{truncated}{ellipsis}" if truncated != text else truncated
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return candidate
        truncated = truncated[:-1]
    return ""


def _get_backspace_mask(size: int) -> Image.Image:
    if size in _backspace_icon_cache:
        return _backspace_icon_cache[size]
    svg_path = display.ASSETS_DIR / "svg" / "backspace.svg"
    png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=size, output_height=size)
    image = Image.open(BytesIO(png_bytes)).convert("RGBA")
    mask = image.split()[3]
    _backspace_icon_cache[size] = mask
    return mask


def _render_keyboard(
    title: str,
    value: str,
    masked: bool,
    layout: KeyboardLayout,
    layout_mode: str,
    selected_col: int,
    selected_band: str,
    mode_index: int,
) -> None:
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    keys = layout.get_keys(layout_mode)
    current_y = context.top
    title_font = context.fonts.get("title", context.fontdisks)
    padding = 4
    if title:
        draw.text((context.x - 11, current_y), title, font=title_font, fill=255)
        current_y += _get_line_height(title_font) + display.TITLE_PADDING

    input_font, key_font = _get_keyboard_fonts()
    display_value = "*" * len(value) if masked else value
    input_left = context.x - 11
    input_right = context.width - padding
    input_top = current_y
    input_height = _get_line_height(input_font) + 6
    draw.rectangle((input_left, input_top, input_right, input_top + input_height), outline=1, fill=1)
    available_width = max(0, input_right - input_left - 4)
    display_value = _truncate_text(draw, display_value, input_font, available_width)
    draw.text((input_left + 2, input_top + 2), display_value, font=input_font, fill=0)
    current_y += input_height + padding

    line_height = _get_line_height(key_font)
    row_height = line_height + 6
    strip_top = current_y
    strip_height = row_height
    strip_left = context.x - 11
    strip_right = context.width - padding
    strip_width = max(0, strip_right - strip_left)

    key_padding = 6
    key_metrics = []
    icon_size = max(6, row_height - 6)
    for key in keys:
        label = key
        is_icon = False
        if key == KEY_SPACE:
            label = "SPACE"
        elif key == KEY_BACKSPACE:
            label = ""
            is_icon = True
        elif key == KEY_CONFIRM:
            label = "OK"
        elif key == KEY_CANCEL:
            label = "CANCEL"
        elif key == KEY_SHIFT:
            label = "SYM" if layout_mode == "upper" else "ABC" if layout_mode == "symbols" else "SHF"
        if is_icon:
            content_width = icon_size
            content_height = icon_size
        else:
            text_bbox = draw.textbbox((0, 0), label, font=key_font)
            content_width = text_bbox[2] - text_bbox[0]
            content_height = text_bbox[3] - text_bbox[1]
        key_metrics.append((label, content_width, content_height, is_icon))

    key_positions = []
    cursor_x = 0
    for label, content_width, content_height, is_icon in key_metrics:
        key_width = content_width + key_padding
        key_positions.append((cursor_x, key_width, label, content_width, content_height, is_icon))
        cursor_x += key_width
    total_width = cursor_x
    offset_x = 0
    if total_width > strip_width and key_positions:
        selected_left, selected_width, _ = key_positions[selected_col]
        selected_right = selected_left + selected_width
        if selected_right - offset_x > strip_width:
            offset_x = selected_right - strip_width
        if selected_left - offset_x < 0:
            offset_x = selected_left
        offset_x = max(0, min(offset_x, total_width - strip_width))

    for col_index, (key_left, key_width, label, content_width, content_height, is_icon) in enumerate(key_positions):
        cell_left = strip_left + key_left - offset_x
        cell_right = cell_left + key_width - 1
        is_selected = selected_band == "chars" and col_index == selected_col
        if cell_right < strip_left or cell_left > strip_right:
            continue
        if is_selected:
            draw.rectangle((cell_left, strip_top, cell_right, strip_top + strip_height), outline=0, fill=1)
        if is_icon:
            mask = _get_backspace_mask(icon_size)
            icon_left = cell_left + max(0, (key_width - icon_size) // 2)
            icon_top = strip_top + max(0, (strip_height - icon_size) // 2)
            fill_color = 0 if is_selected else 255
            icon_image = Image.new("1", (icon_size, icon_size), color=fill_color)
            context.image.paste(icon_image, (icon_left, icon_top), mask)
        else:
            text_x = cell_left + max(0, (key_width - content_width) // 2)
            text_y = strip_top + max(0, (strip_height - content_height) // 2)
            draw.text(
                (text_x, text_y),
                label,
                font=key_font,
                fill=0 if is_selected else 255,
            )

    current_y += strip_height + padding

    mode_items = [
        ("upper", "A"),
        ("lower", "a"),
        ("numbers", "123"),
        ("symbols", "!@#"),
        ("back", "✕"),
        ("ok", "✓"),
    ]
    mode_positions = []
    for attempt_padding, attempt_gap in ((key_padding, 4), (2, 2), (0, 1)):
        mode_positions.clear()
        cursor_x = 0
        for _, label in mode_items:
            text_bbox = draw.textbbox((0, 0), label, font=key_font)
            text_width = text_bbox[2] - text_bbox[0]
            item_width = text_width + attempt_padding
            mode_positions.append((cursor_x, item_width, label))
            cursor_x += item_width + attempt_gap
        total_mode_width = cursor_x - attempt_gap if mode_positions else 0
        if total_mode_width <= strip_width:
            mode_padding = attempt_padding
            mode_gap = attempt_gap
            break
    mode_left = strip_left
    mode_top = current_y
    mode_height = row_height
    mode_offset = max(0, (strip_width - total_mode_width) // 2) if total_mode_width <= strip_width else 0
    for item_index, (item_left, item_width, label) in enumerate(mode_positions):
        cell_left = mode_left + mode_offset + item_left
        cell_right = cell_left + item_width - 1
        mode_key, _ = mode_items[item_index]
        is_active = layout_mode == mode_key
        is_selected = selected_band == "modes" and item_index == mode_index
        if is_selected or (is_active and selected_band != "modes"):
            draw.rectangle((cell_left, mode_top, cell_right, mode_top + mode_height), outline=1, fill=1)
            text_fill = 0
        else:
            if is_active:
                draw.rectangle((cell_left, mode_top, cell_right, mode_top + mode_height), outline=1, fill=0)
            text_fill = 255
        text_bbox = draw.textbbox((0, 0), label, font=key_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = cell_left + max(0, (item_width - text_width) // 2)
        text_y = mode_top + max(0, (mode_height - text_height) // 2)
        draw.text((text_x, text_y), label, font=key_font, fill=text_fill)
    context.disp.display(context.image)


def prompt_text(
    title: str,
    *,
    initial: str = "",
    masked: bool = False,
    layout: KeyboardLayout = DEFAULT_LAYOUT,
) -> Optional[str]:
    value = initial
    selected_col = 0
    selected_band = "chars"
    layout_mode = "lower"
    mode_items = ["upper", "lower", "numbers", "symbols", "back", "ok"]
    mode_index = mode_items.index(layout_mode)
    menus.wait_for_buttons_release([PIN_U, PIN_D, PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
    prev_states = {
        "U": read_button(PIN_U),
        "D": read_button(PIN_D),
        "L": read_button(PIN_L),
        "R": read_button(PIN_R),
        "A": read_button(PIN_A),
        "B": read_button(PIN_B),
        "C": read_button(PIN_C),
    }
    last_press_time = {key: 0.0 for key in prev_states}
    last_repeat_time = {key: 0.0 for key in prev_states}
    while True:
        keys = layout.get_keys(layout_mode)
        _render_keyboard(
            title,
            value,
            masked,
            layout,
            layout_mode,
            selected_col,
            selected_band,
            mode_index,
        )
        now = time.monotonic()
        current_u = read_button(PIN_U)
        if prev_states["U"] and not current_u:
            if selected_band == "modes":
                selected_band = "chars"
            last_press_time["U"] = now
            last_repeat_time["U"] = now
        elif not current_u and now - last_press_time["U"] >= menus.INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["U"] >= menus.REPEAT_INTERVAL:
                if selected_band == "modes":
                    selected_band = "chars"
                    last_repeat_time["U"] = now
        current_d = read_button(PIN_D)
        if prev_states["D"] and not current_d:
            if selected_band == "chars":
                selected_band = "modes"
                mode_index = mode_items.index(layout_mode)
            last_press_time["D"] = now
            last_repeat_time["D"] = now
        elif not current_d and now - last_press_time["D"] >= menus.INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["D"] >= menus.REPEAT_INTERVAL:
                if selected_band == "chars":
                    selected_band = "modes"
                    mode_index = mode_items.index(layout_mode)
                    last_repeat_time["D"] = now
        current_l = read_button(PIN_L)
        if prev_states["L"] and not current_l:
            if selected_band == "modes":
                mode_index = max(0, mode_index - 1)
            else:
                selected_col = max(0, selected_col - 1)
            last_press_time["L"] = now
            last_repeat_time["L"] = now
        elif not current_l and now - last_press_time["L"] >= menus.INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["L"] >= menus.REPEAT_INTERVAL:
                if selected_band == "modes":
                    mode_index = max(0, mode_index - 1)
                else:
                    selected_col = max(0, selected_col - 1)
                last_repeat_time["L"] = now
        current_r = read_button(PIN_R)
        if prev_states["R"] and not current_r:
            if selected_band == "modes":
                mode_index = min(len(mode_items) - 1, mode_index + 1)
            else:
                selected_col = min(len(keys) - 1, selected_col + 1)
            last_press_time["R"] = now
            last_repeat_time["R"] = now
        elif not current_r and now - last_press_time["R"] >= menus.INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["R"] >= menus.REPEAT_INTERVAL:
                if selected_band == "modes":
                    mode_index = min(len(mode_items) - 1, mode_index + 1)
                else:
                    selected_col = min(len(keys) - 1, selected_col + 1)
                last_repeat_time["R"] = now
        current_a = read_button(PIN_A)
        if prev_states["A"] and not current_a:
            return None
        current_b = read_button(PIN_B)
        if prev_states["B"] and not current_b:
            if selected_band == "modes":
                selected_mode = mode_items[mode_index]
                if selected_mode == "ok":
                    return value
                if selected_mode == "back":
                    value = value[:-1]
                else:
                    layout_mode = selected_mode
                    keys = layout.get_keys(layout_mode)
                    selected_col = min(selected_col, len(keys) - 1)
            else:
                key = keys[selected_col]
                if key == KEY_BACKSPACE:
                    value = value[:-1]
                elif key == KEY_SPACE:
                    value += " "
                elif key == KEY_CONFIRM:
                    return value
                elif key == KEY_CANCEL:
                    return None
                elif key == KEY_SHIFT:
                    layout_mode = "upper" if layout_mode == "lower" else "symbols" if layout_mode == "upper" else "lower"
                    keys = layout.get_keys(layout_mode)
                    selected_col = min(selected_col, len(keys) - 1)
                else:
                    value += key
        current_c = read_button(PIN_C)
        if prev_states["C"] and not current_c:
            return value
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        prev_states["C"] = current_c
        time.sleep(menus.BUTTON_POLL_DELAY)
