"""Error screen rendering functions."""

from typing import Optional

from rpi_usb_cloner.ui import display


def render_error_screen(
    title: str,
    message: str,
    *,
    title_icon: Optional[str] = None,
    message_icon: Optional[str] = None,
    message_icon_size: int = 24,
    title_icon_font: Optional[display.Font] = None,
) -> None:
    """Render an error screen with title icon and message with optional icon.

    Args:
        title: The screen title
        message: The error message text
        title_icon: Optional icon character for the title
        message_icon: Optional icon character to display next to the message
        message_icon_size: Size of the message icon font (default 24px)
        title_icon_font: Optional custom font for title icon
    """
    context = display.get_display_context()
    draw = context.draw

    # Clear screen
    draw.rectangle((0, 0, context.width, context.height), outline=0, fill=0)

    # Get fonts
    title_font = context.fonts.get("title", context.fontdisks)
    body_font = context.fontdisks

    # Draw title with icon
    if title:
        display.set_animated_icon(title_icon)
        layout = display.draw_title_with_icon(
            title,
            title_font=title_font,
            icon=title_icon,
            icon_font=title_icon_font,
            extra_gap=2,
            left_margin=context.x - 11,
            draw=draw,
        )
        content_top = layout.content_top
    else:
        content_top = context.top

    # Calculate vertical centering for message content
    message_icon_font: Optional[display.Font] = None
    icon_width = 0
    icon_height = 0

    if message_icon:
        # Load icon font at specified size
        try:
            message_icon_font = display.ImageFont.truetype(
                str(display.LUCIDE_FONT_PATH), message_icon_size
            )
        except OSError:
            message_icon_font = body_font

        # Measure icon dimensions
        if message_icon_font is None:
            message_icon_font = body_font
        icon_bbox = message_icon_font.getbbox(message_icon)
        icon_width = icon_bbox[2] - icon_bbox[0]
        icon_height = icon_bbox[3] - icon_bbox[1]

    # Measure message text
    message_bbox = body_font.getbbox(message)
    text_width = message_bbox[2] - message_bbox[0]
    text_height = message_bbox[3] - message_bbox[1]

    # Calculate total content dimensions
    icon_padding = 6 if message_icon else 0
    total_width = icon_width + icon_padding + text_width
    content_height = max(icon_height, text_height)

    # Calculate available space and center vertically
    available_height = context.height - content_top
    content_y = content_top + (available_height - content_height) // 2

    # Center horizontally
    content_x = (context.width - total_width) // 2

    # Draw icon if present - vertically centered within content area
    if message_icon and message_icon_font:
        icon_y = content_y + (content_height - icon_height) // 2
        draw.text((content_x, icon_y), message_icon, font=message_icon_font, fill=255)

    # Draw message text - vertically centered within content area
    text_x = content_x + icon_width + icon_padding
    text_y = content_y + (content_height - text_height) // 2
    draw.text((text_x, text_y), message, font=body_font, fill=255)

    # Display to screen
    context.disp.display(context.image)
