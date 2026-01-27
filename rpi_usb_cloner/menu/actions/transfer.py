"""Transfer-related menu actions."""

from __future__ import annotations

from rpi_usb_cloner.actions import transfer_actions

from . import get_action_context


def copy_images() -> None:
    """Menu action for COPY IMAGES."""
    context = get_action_context()
    transfer_actions.copy_images_to_usb(app_context=context.app_context)
