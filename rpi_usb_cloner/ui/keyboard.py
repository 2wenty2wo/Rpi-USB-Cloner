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
    is_pressed,
)
from rpi_usb_cloner.ui import display, menus
from rpi_usb_cloner.ui.constants import (
    BUTTON_POLL_DELAY,
    INITIAL_REPEAT_DELAY,
    REPEAT_INTERVAL,
)
from rpi_usb_cloner.ui.icons import LOWERCASE_ICON, SYMBOLS_ICON, UPPERCASE_ICON


KEY_SPACE = "SPACE"
KEY_BACKSPACE = "BACK"
KEY_CONFIRM = "OK"
KEY_CANCEL = "CANCEL"
KEY_SHIFT = "SHIFT"
PASSWORD_ICON_GLYPH = ""


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
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "0",
        KEY_SPACE,
    ],
    lower=[
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "i",
        "j",
        "k",
        "l",
        "m",
        "n",
        "o",
        "p",
        "q",
        "r",
        "s",
        "t",
        "u",
        "v",
        "w",
        "x",
        "y",
        "z",
        KEY_SPACE,
    ],
    upper=[
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",
        "K",
        "L",
        "M",
        "N",
        "O",
        "P",
        "Q",
        "R",
        "S",
        "T",
        "U",
        "V",
        "W",
        "X",
        "Y",
        "Z",
        KEY_SPACE,
    ],
    symbols=[
        ".",
        ",",
        "?",
        "!",
        "@",
        "#",
        "$",
        "%",
        "^",
        "&",
        "*",
        "(",
        ")",
        ":",
        ";",
        "'",
        '"',
        "-",
        "_",
        "+",
        "=",
        "[",
        "]",
        "{",
        "}",
        "\\",
        "|",
        "<",
        ">",
        "/",
        "`",
        "~",
        KEY_SPACE,
    ],
)

_keyboard_fonts: Optional[tuple[display.Font, display.Font, display.Font]] = None


def _get_keyboard_fonts() -> tuple[display.Font, display.Font, display.Font]:
    global _keyboard_fonts
    if _keyboard_fonts is not None:
        return _keyboard_fonts
    context = display.get_display_context()
    input_font: display.Font
    try:
        input_font = ImageFont.truetype(
            str(display.ASSETS_DIR / "fonts" / "dogicapixel.ttf"), 8
        )
    except OSError:
        input_font = context.fontdisks
    key_font: display.Font
    try:
        key_font = ImageFont.truetype(
            str(display.ASSETS_DIR / "fonts" / "dogicapixel.ttf"), 8
        )
    except OSError:
        key_font = input_font
    icon_font: display.Font
    try:
        icon_font = ImageFont.truetype(
            str(display.ASSETS_DIR / "fonts" / "lucide.ttf"),
            16,
        )
    except OSError:
        icon_font = key_font
    _keyboard_fonts = (input_font, key_font, icon_font)
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
    selected_col: int,
    selected_band: str,
    mode_index: int,
    title_icon: Optional[str] = None,
    title_icon_font: Optional[display.Font] = None,
) -> None:
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    keys = layout.get_keys(layout_mode)
    current_y = context.top
    title_font = context.fonts.get("title", context.fontdisks)
    padding = 2
    input_font, key_font, icon_font = _get_keyboard_fonts()
    resolved_title_icon = title_icon if masked else None
    if masked and resolved_title_icon is None:
        resolved_title_icon = PASSWORD_ICON_GLYPH
    resolved_title_icon_font: Optional[display.Font] = title_icon_font
    if resolved_title_icon and resolved_title_icon_font is None:
        resolved_title_icon_font = icon_font
    if title:
        display.set_animated_icon(resolved_title_icon)
        layout_info = display.draw_title_with_icon(
            title,
            title_font=title_font,
            icon=resolved_title_icon,
            icon_font=resolved_title_icon_font,
            extra_gap=0,
            left_margin=context.x - 11,
            draw=draw,
        )
        current_y = layout_info.content_top
    display_value = "*" * len(value) if masked else value
    input_left = context.x - 11
    input_right = context.width - padding
    input_top = current_y
    input_height = _get_line_height(input_font) + 6
    draw.rectangle(
        (input_left, input_top, input_right, input_top + input_height),
        outline=1,
        fill=1,
    )
    available_width = max(0, input_right - input_left - 4)
    display_value = _truncate_text(draw, display_value, input_font, available_width)
    text_bbox = draw.textbbox((0, 0), display_value, font=input_font)
    text_height = text_bbox[3] - text_bbox[1]
    text_y = input_top + max(0, (input_height - text_height) // 2)
    draw.text((input_left + 2, text_y), display_value, font=input_font, fill=0)
    current_y += input_height + 2

    line_height = _get_line_height(key_font)
    row_height = line_height + 6
    strip_top = current_y
    strip_height = row_height
    strip_left = context.x - 11
    strip_right = context.width - padding
    strip_width = max(0, strip_right - strip_left)

    key_padding = 6
    key_metrics = []
    for key in keys:
        label = key
        if key == KEY_SPACE:
            label = "SPACE"
        elif key == KEY_BACKSPACE:
            label = "BACK"
        elif key == KEY_CONFIRM:
            label = "OK"
        elif key == KEY_CANCEL:
            label = "CANCEL"
        elif key == KEY_SHIFT:
            label = (
                "SYM"
                if layout_mode == "upper"
                else "ABC" if layout_mode == "symbols" else "SHF"
            )
        text_bbox = draw.textbbox((0, 0), label, font=key_font)
        text_width = text_bbox[2] - text_bbox[0]
        key_metrics.append((label, text_width))

    key_positions = []
    cursor_x = 0
    for label, text_width in key_metrics:
        key_width = text_width + key_padding
        key_positions.append((cursor_x, key_width, label))
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

    for col_index, (key_left, key_width, label) in enumerate(key_positions):
        cell_left = strip_left + key_left - offset_x
        cell_right = cell_left + key_width - 1
        is_selected = selected_band == "chars" and col_index == selected_col
        if cell_right < strip_left or cell_left > strip_right:
            continue
        if is_selected:
            draw.rectangle(
                (cell_left, strip_top, cell_right, strip_top + strip_height),
                outline=0,
                fill=1,
            )
        text_bbox = draw.textbbox((0, 0), label, font=key_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = cell_left + max(0, (key_width - text_width) // 2)
        text_y = strip_top + max(0, (strip_height - text_height) // 2)
        draw.text(
            (text_x, text_y),
            label,
            font=key_font,
            fill=0 if is_selected else 255,
        )

    current_y += strip_height + 2

    mode_selectors = [
        ("upper", UPPERCASE_ICON, icon_font),
        ("lower", LOWERCASE_ICON, icon_font),
        ("numbers", "\ue0ef", icon_font),
        ("symbols", SYMBOLS_ICON, icon_font),
    ]
    mode_actions = [
        ("back", "\ue0ae", icon_font),
        ("ok", "\ue06c", icon_font),
    ]
    mode_items = mode_selectors + mode_actions
    inter_group_gap = 8
    mode_positions: list[tuple[int, int, str, display.Font, str]] = []
    for attempt_padding, attempt_gap in ((key_padding, 4), (2, 2), (0, 1)):
        mode_positions.clear()
        cursor_x = 0
        for item_index, (mode_key, label, font) in enumerate(mode_items):
            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            item_width = text_width + attempt_padding
            mode_positions.append((cursor_x, item_width, label, font, mode_key))
            cursor_x += item_width + attempt_gap
            if item_index == len(mode_selectors) - 1:
                cursor_x += inter_group_gap
        total_mode_width = cursor_x - attempt_gap if mode_positions else 0
        if total_mode_width <= strip_width:
            break
    mode_left = strip_left
    mode_top = current_y
    mode_height = row_height
    mode_offset = (
        max(0, (strip_width - total_mode_width) // 2)
        if total_mode_width <= strip_width
        else 0
    )
    for item_index, (item_left, item_width, label, font, mode_key) in enumerate(
        mode_positions
    ):
        cell_left = mode_left + mode_offset + item_left
        cell_right = cell_left + item_width - 1
        is_active = layout_mode == mode_key
        is_selected = selected_band == "modes" and item_index == mode_index
        text_fill = 255
        if is_active:
            draw.rectangle(
                (cell_left, mode_top, cell_right, mode_top + mode_height),
                outline=1,
                fill=0,
            )
        if is_selected:
            draw.rectangle(
                (cell_left, mode_top, cell_right, mode_top + mode_height),
                outline=1,
                fill=1,
            )
            text_fill = 0
        text_bbox = draw.textbbox((0, 0), label, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = cell_left + max(0, (item_width - text_width) // 2) - text_bbox[0]
        text_y = mode_top + max(0, (mode_height - text_height) // 2)
        draw.text((text_x, text_y), label, font=font, fill=text_fill)
    context.disp.display(context.image)


def prompt_text(
    title: str,
    *,
    initial: str = "",
    masked: bool = False,
    layout: KeyboardLayout = DEFAULT_LAYOUT,
    title_icon: Optional[str] = None,
    title_icon_font: Optional[display.Font] = None,
) -> Optional[str]:
    value = initial
    selected_col = 0
    selected_band = "chars"
    layout_mode = "lower"
    mode_items = ["upper", "lower", "numbers", "symbols", "back", "ok"]
    mode_index = mode_items.index(layout_mode)
    menus.wait_for_buttons_release([PIN_U, PIN_D, PIN_L, PIN_R, PIN_A, PIN_B, PIN_C])
    prev_states = {
        "U": is_pressed(PIN_U),
        "D": is_pressed(PIN_D),
        "L": is_pressed(PIN_L),
        "R": is_pressed(PIN_R),
        "A": is_pressed(PIN_A),
        "B": is_pressed(PIN_B),
        "C": is_pressed(PIN_C),
    }
    last_press_time = dict.fromkeys(prev_states, 0.0)
    last_repeat_time = dict.fromkeys(prev_states, 0.0)
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
            title_icon,
            title_icon_font,
        )
        now = time.monotonic()
        current_u = is_pressed(PIN_U)
        if not prev_states["U"] and current_u:
            if selected_band == "modes":
                selected_band = "chars"
            last_press_time["U"] = now
            last_repeat_time["U"] = now
        elif (
            current_u
            and now - last_press_time["U"] >= INITIAL_REPEAT_DELAY
            and now - last_repeat_time["U"] >= REPEAT_INTERVAL
            and selected_band == "modes"
        ):
            selected_band = "chars"
            last_repeat_time["U"] = now
        current_d = is_pressed(PIN_D)
        if not prev_states["D"] and current_d:
            if selected_band == "chars":
                selected_band = "modes"
                mode_index = mode_items.index(layout_mode)
            last_press_time["D"] = now
            last_repeat_time["D"] = now
        elif (
            current_d
            and now - last_press_time["D"] >= INITIAL_REPEAT_DELAY
            and now - last_repeat_time["D"] >= REPEAT_INTERVAL
            and selected_band == "chars"
        ):
            selected_band = "modes"
            mode_index = mode_items.index(layout_mode)
            last_repeat_time["D"] = now
        current_l = is_pressed(PIN_L)
        if not prev_states["L"] and current_l:
            if selected_band == "modes":
                mode_index = max(0, mode_index - 1)
            else:
                selected_col = max(0, selected_col - 1)
            last_press_time["L"] = now
            last_repeat_time["L"] = now
        elif current_l and now - last_press_time["L"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["L"] >= REPEAT_INTERVAL:
                if selected_band == "modes":
                    mode_index = max(0, mode_index - 1)
                else:
                    selected_col = max(0, selected_col - 1)
                last_repeat_time["L"] = now
        current_r = is_pressed(PIN_R)
        if not prev_states["R"] and current_r:
            if selected_band == "modes":
                mode_index = min(len(mode_items) - 1, mode_index + 1)
            else:
                selected_col = min(len(keys) - 1, selected_col + 1)
            last_press_time["R"] = now
            last_repeat_time["R"] = now
        elif current_r and now - last_press_time["R"] >= INITIAL_REPEAT_DELAY:
            if now - last_repeat_time["R"] >= REPEAT_INTERVAL:
                if selected_band == "modes":
                    mode_index = min(len(mode_items) - 1, mode_index + 1)
                else:
                    selected_col = min(len(keys) - 1, selected_col + 1)
                last_repeat_time["R"] = now
        current_a = is_pressed(PIN_A)
        if not prev_states["A"] and current_a:
            return None
        current_b = is_pressed(PIN_B)
        if not prev_states["B"] and current_b:
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
                    layout_mode = (
                        "upper"
                        if layout_mode == "lower"
                        else "symbols" if layout_mode == "upper" else "lower"
                    )
                    keys = layout.get_keys(layout_mode)
                    selected_col = min(selected_col, len(keys) - 1)
                else:
                    value += key
        current_c = is_pressed(PIN_C)
        if not prev_states["C"] and current_c:
            return value
        prev_states["U"] = current_u
        prev_states["D"] = current_d
        prev_states["L"] = current_l
        prev_states["R"] = current_r
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        prev_states["C"] = current_c
        time.sleep(BUTTON_POLL_DELAY)
