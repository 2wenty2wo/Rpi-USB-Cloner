"""Confirmation screen rendering functions."""

import time
from typing import Iterable, Optional

from PIL import ImageFont

from rpi_usb_cloner.app import state as app_state
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.ui import display
from rpi_usb_cloner.ui import menus
from rpi_usb_cloner.ui.constants import BUTTON_POLL_DELAY


def render_confirmation_screen(
    title: str,
    prompt_lines: Iterable[str],
    *,
    selected_index: int = 0,
    title_icon: Optional[str] = None,
    title_icon_font: Optional[ImageFont.ImageFont] = None,
) -> None:
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    title_font = context.fonts.get("title", context.fontdisks)
    prompt_font = context.fontdisks
    button_font = context.fontcopy
    confirmation_font_path = display.ASSETS_DIR / "fonts" / "Born2bSportyFS.otf"
    try:
        button_font = ImageFont.truetype(confirmation_font_path, 14)
    except OSError:
        button_font = context.fontcopy
    layout = display.draw_title_with_icon(
        title,
        title_font=title_font,
        icon=title_icon,
        icon_font=title_icon_font,
        extra_gap=2,
        left_margin=context.x - 11,
    )
    content_top = layout.content_top
    if isinstance(prompt_lines, str):
        line_list = [prompt_lines]
    else:
        line_list = list(prompt_lines)
    wrapped_prompt_lines = display._wrap_lines_to_width(
        line_list,
        prompt_font,
        context.width - 8,
    )
    prompt_line_height = display._get_line_height(prompt_font)
    prompt_line_step = prompt_line_height + 2
    button_labels = ("NO", "YES")
    max_label_width = 0
    max_text_height = 0
    for button_label in button_labels:
        label_width = display._measure_text_width(draw, button_label, button_font)
        max_label_width = max(max_label_width, label_width)
        text_bbox = draw.textbbox((0, 0), button_label, font=button_font)
        text_height = text_bbox[3] - text_bbox[1]
        max_text_height = max(max_text_height, text_height)
    button_height = max(10, max_text_height + 4)
    max_button_y = context.height - button_height - 4
    max_prompt_height = max(0, max_button_y - content_top - 6)
    max_prompt_lines = max(1, int((max_prompt_height + 2) / prompt_line_step))
    if wrapped_prompt_lines:
        if len(wrapped_prompt_lines) > max_prompt_lines:
            wrapped_prompt_lines = wrapped_prompt_lines[:max_prompt_lines]
            last_line = f"{wrapped_prompt_lines[-1]}…"
            wrapped_prompt_lines[-1] = display._truncate_text(
                draw,
                last_line,
                prompt_font,
                context.width - 8,
            )
    else:
        wrapped_prompt_lines = [""]
    prompt_height = max(
        prompt_line_height,
        len(wrapped_prompt_lines) * prompt_line_step - 2,
    )
    button_width = max(
        36,
        max_label_width + 16,
    )
    button_gap = 18
    block_width = button_width * 2 + button_gap
    available_width = context.width - 4
    min_button_gap = 2
    if block_width > available_width:
        max_gap = max(min_button_gap, available_width - button_width * 2)
        button_gap = min(button_gap, max_gap)
        block_width = button_width * 2 + button_gap
        if block_width > available_width:
            max_button_width = max(1, int((available_width - button_gap) / 2))
            button_width = min(button_width, max_button_width)
            block_width = button_width * 2 + button_gap
    button_y = int(content_top + (context.height - content_top) * 0.55)
    prompt_area_height = max(0, button_y - content_top - 6)
    prompt_start_y = content_top + max(0, (prompt_area_height - prompt_height) // 2)
    prompt_bottom = prompt_start_y + prompt_height
    min_button_y = int(prompt_bottom + 4)
    button_y = max(min_button_y, min(button_y, max_button_y))
    left_x = int((context.width - block_width) / 2)
    right_x = left_x + button_width + button_gap

    current_y = prompt_start_y
    for line in wrapped_prompt_lines:
        text_width = display._measure_text_width(draw, line, prompt_font)
        line_x = int((context.width - text_width) / 2)
        draw.text((line_x, current_y), line, font=prompt_font, fill=255)
        current_y += prompt_line_step

    buttons = [("NO", left_x), ("YES", right_x)]
    for index, (label, x_pos) in enumerate(buttons):
        is_selected = index == selected_index
        rect = (x_pos, button_y, x_pos + button_width, button_y + button_height)
        if is_selected:
            draw.rectangle(rect, outline=255, fill=255)
        else:
            draw.rectangle(rect, outline=255, fill=0)
        text_width = display._measure_text_width(draw, label, button_font)
        text_bbox = draw.textbbox((0, 0), label, font=button_font)
        text_height = text_bbox[3] - text_bbox[1]
        content_x = int(x_pos + (button_width - text_width) / 2)
        text_y = button_y + (button_height - text_height) // 2 - text_bbox[1]
        fill = 0 if is_selected else 255
        draw.text((content_x, text_y), label, font=button_font, fill=fill)
    context.disp.display(context.image)
    display.mark_display_dirty()


def render_confirmation(
    app_ctx,
    title: str,
    message: str,
    default: bool = False,
) -> bool:
    _ = app_ctx
    prompt_lines = message.splitlines() if message else [""]
    confirm_selection = app_state.CONFIRM_YES if default else app_state.CONFIRM_NO
    render_confirmation_screen(
        title,
        prompt_lines,
        selected_index=confirm_selection,
    )
    menus.wait_for_buttons_release([gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B])
    prev_states = {
        "L": gpio.is_pressed(gpio.PIN_L),
        "R": gpio.is_pressed(gpio.PIN_R),
        "A": gpio.is_pressed(gpio.PIN_A),
        "B": gpio.is_pressed(gpio.PIN_B),
    }
    while True:
        action_taken = False
        current_r = gpio.is_pressed(gpio.PIN_R)
        if prev_states["R"] and not current_r:
            if confirm_selection == app_state.CONFIRM_NO:
                confirm_selection = app_state.CONFIRM_YES
                action_taken = True
        current_l = gpio.is_pressed(gpio.PIN_L)
        if prev_states["L"] and not current_l:
            if confirm_selection == app_state.CONFIRM_YES:
                confirm_selection = app_state.CONFIRM_NO
                action_taken = True
        current_a = gpio.is_pressed(gpio.PIN_A)
        if prev_states["A"] and not current_a:
            return False
        current_b = gpio.is_pressed(gpio.PIN_B)
        if prev_states["B"] and not current_b:
            return confirm_selection == app_state.CONFIRM_YES
        prev_states["R"] = current_r
        prev_states["L"] = current_l
        prev_states["A"] = current_a
        prev_states["B"] = current_b
        if action_taken:
            render_confirmation_screen(
                title,
                prompt_lines,
                selected_index=confirm_selection,
            )
        time.sleep(BUTTON_POLL_DELAY)


def render_update_buttons_screen(
    title: str,
    prompt_lines: Iterable[str],
    *,
    selected_index: int = 0,
    title_icon: Optional[str] = None,
    title_icon_font: Optional[ImageFont.ImageFont] = None,
) -> int:
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    title_font = context.fonts.get("title", context.fontdisks)
    prompt_font = context.fontdisks
    button_font = context.fontcopy
    confirmation_font_path = display.ASSETS_DIR / "fonts" / "Born2bSportyFS.otf"
    try:
        button_font = ImageFont.truetype(confirmation_font_path, 14)
    except OSError:
        button_font = context.fontcopy
    layout = display.draw_title_with_icon(
        title,
        title_font=title_font,
        icon=title_icon,
        icon_font=title_icon_font,
        extra_gap=2,
        left_margin=context.x - 11,
    )
    content_top = layout.content_top
    if isinstance(prompt_lines, str):
        line_list = [prompt_lines]
    else:
        line_list = list(prompt_lines)
    wrapped_prompt_lines = display._wrap_lines_to_width(
        line_list,
        prompt_font,
        context.width - 8,
    )
    prompt_line_height = display._get_line_height(prompt_font)
    prompt_line_step = prompt_line_height + 2
    button_labels = ("CHECK", "UPDATE")
    max_label_width = 0
    max_text_height = 0
    for button_label in button_labels:
        label_width = display._measure_text_width(draw, button_label, button_font)
        max_label_width = max(max_label_width, label_width)
        text_bbox = draw.textbbox((0, 0), button_label, font=button_font)
        text_height = text_bbox[3] - text_bbox[1]
        max_text_height = max(max_text_height, text_height)
    button_height = max(10, max_text_height + 4)
    max_button_y = context.height - button_height - 4
    max_prompt_height = max(0, max_button_y - content_top - 6)
    max_prompt_lines = max(1, int((max_prompt_height + 2) / prompt_line_step))
    if wrapped_prompt_lines:
        if len(wrapped_prompt_lines) > max_prompt_lines:
            wrapped_prompt_lines = wrapped_prompt_lines[:max_prompt_lines]
            last_line = f"{wrapped_prompt_lines[-1]}…"
            wrapped_prompt_lines[-1] = display._truncate_text(
                draw,
                last_line,
                prompt_font,
                context.width - 8,
            )
    else:
        wrapped_prompt_lines = [""]
    prompt_height = max(
        prompt_line_height,
        len(wrapped_prompt_lines) * prompt_line_step - 2,
    )
    button_width = max(
        36,
        max_label_width + 16,
    )
    button_gap = 18
    block_width = button_width * 2 + button_gap
    available_width = context.width - 4
    min_button_gap = 2
    if block_width > available_width:
        max_gap = max(min_button_gap, available_width - button_width * 2)
        button_gap = min(button_gap, max_gap)
        block_width = button_width * 2 + button_gap
        if block_width > available_width:
            max_button_width = max(1, int((available_width - button_gap) / 2))
            button_width = min(button_width, max_button_width)
            block_width = button_width * 2 + button_gap
    button_y = int(content_top + (context.height - content_top) * 0.65)
    prompt_area_height = max(0, button_y - content_top - 6)
    prompt_start_y = content_top + max(0, (prompt_area_height - prompt_height) // 2)
    prompt_bottom = prompt_start_y + prompt_height
    min_button_y = int(prompt_bottom + 2)
    button_y = max(min_button_y, min(button_y, max_button_y))
    left_x = int((context.width - block_width) / 2)
    right_x = left_x + button_width + button_gap

    current_y = prompt_start_y
    for line in wrapped_prompt_lines:
        text_width = display._measure_text_width(draw, line, prompt_font)
        line_x = int((context.width - text_width) / 2)
        draw.text((line_x, current_y), line, font=prompt_font, fill=255)
        current_y += prompt_line_step

    buttons = [("CHECK", left_x), ("UPDATE", right_x)]
    for index, (label, x_pos) in enumerate(buttons):
        is_selected = index == selected_index
        rect = (x_pos, button_y, x_pos + button_width, button_y + button_height)
        if is_selected:
            draw.rectangle(rect, outline=255, fill=255)
        else:
            draw.rectangle(rect, outline=255, fill=0)
        text_width = display._measure_text_width(draw, label, button_font)
        text_bbox = draw.textbbox((0, 0), label, font=button_font)
        text_height = text_bbox[3] - text_bbox[1]
        content_x = int(x_pos + (button_width - text_width) / 2)
        text_y = button_y + (button_height - text_height) // 2 - text_bbox[1]
        fill = 0 if is_selected else 255
        draw.text((content_x, text_y), label, font=button_font, fill=fill)
    context.disp.display(context.image)
    display.mark_display_dirty()
    return selected_index


def render_verify_finish_buttons_screen(
    title: str,
    prompt_lines: Iterable[str],
    *,
    selected_index: int = 0,
    title_icon: Optional[str] = None,
    title_icon_font: Optional[ImageFont.ImageFont] = None,
) -> int:
    context = display.get_display_context()
    draw = context.draw
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)
    title_font = context.fonts.get("title", context.fontdisks)
    prompt_font = context.fontdisks
    button_font = context.fontcopy
    confirmation_font_path = display.ASSETS_DIR / "fonts" / "Born2bSportyFS.otf"
    try:
        button_font = ImageFont.truetype(confirmation_font_path, 14)
    except OSError:
        button_font = context.fontcopy
    layout = display.draw_title_with_icon(
        title,
        title_font=title_font,
        icon=title_icon,
        icon_font=title_icon_font,
        extra_gap=2,
        left_margin=context.x - 11,
    )
    content_top = layout.content_top
    if isinstance(prompt_lines, str):
        line_list = [prompt_lines]
    else:
        line_list = list(prompt_lines)
    wrapped_prompt_lines = display._wrap_lines_to_width(
        line_list,
        prompt_font,
        context.width - 8,
    )
    prompt_line_height = display._get_line_height(prompt_font)
    prompt_line_step = prompt_line_height + 2
    button_labels = ("VERIFY", "FINISH")
    max_label_width = 0
    max_text_height = 0
    for button_label in button_labels:
        label_width = display._measure_text_width(draw, button_label, button_font)
        max_label_width = max(max_label_width, label_width)
        text_bbox = draw.textbbox((0, 0), button_label, font=button_font)
        text_height = text_bbox[3] - text_bbox[1]
        max_text_height = max(max_text_height, text_height)
    button_height = max(10, max_text_height + 4)
    max_button_y = context.height - button_height - 4
    max_prompt_height = max(0, max_button_y - content_top - 6)
    max_prompt_lines = max(1, int((max_prompt_height + 2) / prompt_line_step))
    if wrapped_prompt_lines:
        if len(wrapped_prompt_lines) > max_prompt_lines:
            wrapped_prompt_lines = wrapped_prompt_lines[:max_prompt_lines]
            last_line = f"{wrapped_prompt_lines[-1]}…"
            wrapped_prompt_lines[-1] = display._truncate_text(
                draw,
                last_line,
                prompt_font,
                context.width - 8,
            )
    else:
        wrapped_prompt_lines = [""]
    prompt_height = max(
        prompt_line_height,
        len(wrapped_prompt_lines) * prompt_line_step - 2,
    )
    button_width = max(
        36,
        max_label_width + 16,
    )
    button_gap = 18
    block_width = button_width * 2 + button_gap
    available_width = context.width - 4
    min_button_gap = 2
    if block_width > available_width:
        max_gap = max(min_button_gap, available_width - button_width * 2)
        button_gap = min(button_gap, max_gap)
        block_width = button_width * 2 + button_gap
        if block_width > available_width:
            max_button_width = max(1, int((available_width - button_gap) / 2))
            button_width = min(button_width, max_button_width)
            block_width = button_width * 2 + button_gap
    button_y = int(content_top + (context.height - content_top) * 0.55)
    prompt_area_height = max(0, button_y - content_top - 6)
    prompt_start_y = content_top + max(0, (prompt_area_height - prompt_height) // 2)
    prompt_bottom = prompt_start_y + prompt_height
    min_button_y = int(prompt_bottom + 4)
    button_y = max(min_button_y, min(button_y, max_button_y))
    left_x = int((context.width - block_width) / 2)
    right_x = left_x + button_width + button_gap

    current_y = prompt_start_y
    for line in wrapped_prompt_lines:
        text_width = display._measure_text_width(draw, line, prompt_font)
        line_x = int((context.width - text_width) / 2)
        draw.text((line_x, current_y), line, font=prompt_font, fill=255)
        current_y += prompt_line_step

    buttons = [("VERIFY", left_x), ("FINISH", right_x)]
    for index, (label, x_pos) in enumerate(buttons):
        is_selected = index == selected_index
        rect = (x_pos, button_y, x_pos + button_width, button_y + button_height)
        if is_selected:
            draw.rectangle(rect, outline=255, fill=255)
        else:
            draw.rectangle(rect, outline=255, fill=0)
        text_width = display._measure_text_width(draw, label, button_font)
        text_bbox = draw.textbbox((0, 0), label, font=button_font)
        text_height = text_bbox[3] - text_bbox[1]
        content_x = int(x_pos + (button_width - text_width) / 2)
        text_y = button_y + (button_height - text_height) // 2 - text_bbox[1]
        fill = 0 if is_selected else 255
        draw.text((content_x, text_y), label, font=button_font, fill=fill)
    context.disp.display(context.image)
    display.mark_display_dirty()
    return selected_index
