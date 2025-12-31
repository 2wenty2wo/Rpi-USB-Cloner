import time
from dataclasses import dataclass
from typing import List, Optional

from PIL import ImageFont

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
    rows: List[List[str]]
    uppercase_rows: Optional[List[List[str]]] = None
    symbols_rows: Optional[List[List[str]]] = None

    def get_rows(self, mode: str) -> List[List[str]]:
        if mode == "upper" and self.uppercase_rows:
            return self.uppercase_rows
        if mode == "symbols" and self.symbols_rows:
            return self.symbols_rows
        return self.rows


DEFAULT_LAYOUT = KeyboardLayout(
    rows=[
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
        ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
        ["a", "s", "d", "f", "g", "h", "j", "k", "l", "-"],
        [KEY_SHIFT, "z", "x", "c", "v", "b", "n", "m", ".", "@"],
        [KEY_SPACE, KEY_BACKSPACE, KEY_CONFIRM, KEY_CANCEL],
    ],
    uppercase_rows=[
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
        ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
        ["A", "S", "D", "F", "G", "H", "J", "K", "L", "-"],
        [KEY_SHIFT, "Z", "X", "C", "V", "B", "N", "M", ".", "@"],
        [KEY_SPACE, KEY_BACKSPACE, KEY_CONFIRM, KEY_CANCEL],
    ],
    symbols_rows=[
        ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"],
        ["-", "_", "+", "=", "[", "]", "{", "}", "\\", "|"],
        [";", ":", "'", "\"", "<", ">", ",", ".", "?", "/"],
        [KEY_SHIFT, "`", "~", "^", "*", "(", ")", "<", ">", "?"],
        [KEY_SPACE, KEY_BACKSPACE, KEY_CONFIRM, KEY_CANCEL],
    ]
)

_keyboard_fonts: Optional[tuple[ImageFont.ImageFont, ImageFont.ImageFont]] = None


def _get_keyboard_fonts() -> tuple[ImageFont.ImageFont, ImageFont.ImageFont]:
    global _keyboard_fonts
    if _keyboard_fonts is not None:
        return _keyboard_fonts
    context = display.get_display_context()
    try:
        input_font = ImageFont.truetype(display.ASSETS_DIR / "dogicapixel.ttf", 8)
    except OSError:
        input_font = context.fontdisks
    try:
        key_font = ImageFont.truetype(display.ASSETS_DIR / "dogicapixelbold.ttf", 8)
    except OSError:
        key_font = context.fontdisks
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


def _render_keyboard(
    title: str,
    value: str,
    masked: bool,
    layout: KeyboardLayout,
    layout_mode: str,
    selected_row: int,
    selected_col: int,
) -> None:
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    rows = layout.get_rows(layout_mode)
    current_y = context.top
    title_font = context.fonts.get("title", context.fontdisks)
    if title:
        draw.text((context.x - 11, current_y), title, font=title_font, fill=255)
        current_y += _get_line_height(title_font) + display.TITLE_PADDING

    input_font, key_font = _get_keyboard_fonts()
    display_value = "*" * len(value) if masked else value
    available_width = context.width - (context.x - 11)
    display_value = _truncate_text(draw, display_value, input_font, available_width)
    draw.text((context.x - 11, current_y), display_value, font=input_font, fill=255)
    current_y += _get_line_height(input_font) + 2

    line_height = _get_line_height(key_font)
    row_height = line_height + 4
    available_height = context.height - current_y
    visible_rows = max(1, available_height // row_height)
    total_rows = len(rows)
    row_offset = min(max(selected_row - visible_rows + 1, 0), max(0, total_rows - visible_rows))

    for row_index in range(row_offset, min(total_rows, row_offset + visible_rows)):
        row = rows[row_index]
        cell_width = max(1, context.width // len(row))
        row_top = current_y + (row_index - row_offset) * row_height
        for col_index, key in enumerate(row):
            cell_left = col_index * cell_width
            cell_right = cell_left + cell_width - 1
            is_selected = row_index == selected_row and col_index == selected_col
            if is_selected:
                draw.rectangle((cell_left, row_top, cell_right, row_top + row_height - 1), outline=0, fill=1)
            label = key
            if key == KEY_SPACE:
                label = "SPC"
            elif key == KEY_BACKSPACE:
                label = "BS"
            elif key == KEY_CONFIRM:
                label = "OK"
            elif key == KEY_CANCEL:
                label = "CAN"
            elif key == KEY_SHIFT:
                label = "SYM" if layout_mode == "upper" else "ABC" if layout_mode == "symbols" else "SHF"
            text_bbox = draw.textbbox((0, 0), label, font=key_font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            text_x = cell_left + max(0, (cell_width - text_width) // 2)
            text_y = row_top + max(0, (row_height - text_height) // 2)
            draw.text(
                (text_x, text_y),
                label,
                font=key_font,
                fill=0 if is_selected else 255,
            )
    context.disp.display(context.image)


def prompt_text(
    title: str,
    *,
    initial: str = "",
    masked: bool = False,
    layout: KeyboardLayout = DEFAULT_LAYOUT,
) -> Optional[str]:
    value = initial
    selected_row = 0
    selected_col = 0
    layout_mode = "lower"
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
        rows = layout.get_rows(layout_mode)
        _render_keyboard(title, value, masked, layout, layout_mode, selected_row, selected_col)
        now = time.monotonic()
        current_u = read_button(PIN_U)
        if prev_states["U"] and not current_u:
            selected_row = max(0, selected_row - 1)
            selected_col = min(selected_col, len(rows[selected_row]) - 1)
            last_press_time["U"] = now
            last_repeat_time["U"] = now
        elif not current_u and now - last_press_time["U"] >= menus.INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["U"] >= menus.REPEAT_INTERVAL:
                selected_row = max(0, selected_row - 1)
                selected_col = min(selected_col, len(rows[selected_row]) - 1)
                last_repeat_time["U"] = now
        current_d = read_button(PIN_D)
        if prev_states["D"] and not current_d:
            selected_row = min(len(rows) - 1, selected_row + 1)
            selected_col = min(selected_col, len(rows[selected_row]) - 1)
            last_press_time["D"] = now
            last_repeat_time["D"] = now
        elif not current_d and now - last_press_time["D"] >= menus.INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["D"] >= menus.REPEAT_INTERVAL:
                selected_row = min(len(rows) - 1, selected_row + 1)
                selected_col = min(selected_col, len(rows[selected_row]) - 1)
                last_repeat_time["D"] = now
        current_l = read_button(PIN_L)
        if prev_states["L"] and not current_l:
            selected_col = max(0, selected_col - 1)
            last_press_time["L"] = now
            last_repeat_time["L"] = now
        elif not current_l and now - last_press_time["L"] >= menus.INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["L"] >= menus.REPEAT_INTERVAL:
                selected_col = max(0, selected_col - 1)
                last_repeat_time["L"] = now
        current_r = read_button(PIN_R)
        if prev_states["R"] and not current_r:
            selected_col = min(len(rows[selected_row]) - 1, selected_col + 1)
            last_press_time["R"] = now
            last_repeat_time["R"] = now
        elif not current_r and now - last_press_time["R"] >= menus.INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["R"] >= menus.REPEAT_INTERVAL:
                selected_col = min(len(rows[selected_row]) - 1, selected_col + 1)
                last_repeat_time["R"] = now
        current_a = read_button(PIN_A)
        if prev_states["A"] and not current_a:
            return None
        current_b = read_button(PIN_B)
        if prev_states["B"] and not current_b:
            key = rows[selected_row][selected_col]
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
                rows = layout.get_rows(layout_mode)
                selected_row = min(selected_row, len(rows) - 1)
                selected_col = min(selected_col, len(rows[selected_row]) - 1)
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
