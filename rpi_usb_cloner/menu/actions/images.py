"""Image-related menu actions."""

from __future__ import annotations

from rpi_usb_cloner.actions import image_actions
from . import get_action_context


def _run_operation(action, *, allow_back_interrupt: bool = False) -> None:
    context = get_action_context()
    context.app_context.operation_active = True
    context.app_context.allow_back_interrupt = allow_back_interrupt
    try:
        action()
    finally:
        context.app_context.operation_active = False
        context.app_context.allow_back_interrupt = False


def images_coming_soon() -> None:
    image_actions.coming_soon()


def backup_image() -> None:
    context = get_action_context()
    _run_operation(lambda: image_actions.backup_image(app_context=context.app_context, log_debug=context.log_debug))


def write_image() -> None:
    context = get_action_context()
    _run_operation(lambda: image_actions.write_image(app_context=context.app_context, log_debug=context.log_debug))
