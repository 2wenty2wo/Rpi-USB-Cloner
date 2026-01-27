"""Transfer-related menu actions."""

from __future__ import annotations

from rpi_usb_cloner.actions import network_transfer_actions, transfer_actions, wifi_direct_actions

from . import get_action_context


def copy_images_usb() -> None:
    """Menu action for USB TO USB transfer."""
    context = get_action_context()
    transfer_actions.copy_images_to_usb(app_context=context.app_context)


def copy_images_network() -> None:
    """Menu action for ETHERNET transfer."""
    context = get_action_context()
    network_transfer_actions.copy_images_network(app_context=context.app_context)


def wifi_direct_host() -> None:
    """Menu action for WIFI HOST."""
    context = get_action_context()
    wifi_direct_actions.wifi_direct_host(app_context=context.app_context)


def wifi_direct_join() -> None:
    """Menu action for WIFI JOIN."""
    context = get_action_context()
    wifi_direct_actions.wifi_direct_join(app_context=context.app_context)
