"""Network transfer actions for peer-to-peer image transfers.

This module provides UI flows for discovering peers and transferring images
over network using mDNS and HTTP.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional

from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.domain import DiskImage
from rpi_usb_cloner.hardware import gpio
from rpi_usb_cloner.logging import get_logger
from rpi_usb_cloner.services import discovery, peer_transfer_client
from rpi_usb_cloner.services.transfer import estimate_transfer_size
from rpi_usb_cloner.storage import devices, image_repo
from rpi_usb_cloner.ui import display, menus, screens
from rpi_usb_cloner.ui.icons import ALERT_ICON, FOLDER_ICON, WIFI_ICON

from .transfer_actions import _select_images_checklist

log = get_logger(source=__name__)


def copy_images_network(*, app_context: AppContext) -> None:
    """ Network image transfer flow (sender).
    
    Flow:
    1. Find source repo and select images
    2. Discover peers on network
    3. Select destination peer
    4. Enter PIN
    5. Send images with progress
    6. Show success/failure summary
    """
    # Step 1: Find source repo
    source_repos = image_repo.find_image_repos()
    
    if not source_repos:
        screens.render_error_screen(
            "NETWORK TRANSFER",
            message="No image repo found",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1.5)
        return
    
    # Select source if multiple
    if len(source_repos) > 1:
        source_index = menus.select_list(
            "SOURCE REPO",
            [repo.path.name for repo in source_repos],
            title_icon=FOLDER_ICON,
            transition_direction="forward",
        )
        if source_index is None:
            return
        source_repo = source_repos[source_index]
    else:
        source_repo = source_repos[0]
    
    # Get images from source
    all_images = image_repo.list_clonezilla_images(source_repo.path)
    
    if not all_images:
        screens.render_error_screen(
            "NETWORK TRANSFER",
            message="No images found\\nin source repo",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1.5)
        return
    
    # Step 2: Multi-select images
    selected_flags = _select_images_checklist([img.name for img in all_images])
    
    if selected_flags is None:
        return
    
    selected_images = [
        img for i, img in enumerate(all_images) if selected_flags[i]
    ]
    
    if not selected_images:
        screens.render_error_screen(
            "NETWORK TRANSFER",
            message="No images selected",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1.5)
        return
    
    # Step 3: Discover peers
    peers = _discover_peers()
    
    if not peers:
        screens.render_error_screen(
            "NETWORK TRANSFER",
            message="No peers found\\nCheck network cable",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(2)
        return
    
    # Step 4: Select peer
    peer_index = menus.select_list(
        "SELECT DEVICE",
        [f"{p.hostname}\\n{p.address}" for p in peers],
        title_icon=WIFI_ICON,
        transition_direction="forward",
    )
    
    if peer_index is None:
        return
    
    peer = peers[peer_index]
    
    # Step 5: Enter PIN
    pin = _enter_pin()
    
    if pin is None:
        return
    
    # Step 6: Send images
    _execute_network_transfer(selected_images, peer, pin)


def _discover_peers() -> list[discovery.PeerDevice]:
    """Discover peer devices with progress display."""
    
    # Create discovery service
    disc = discovery.DiscoveryService()
    
    # Display scanning screen
    def show_scanning():
        screens.render_progress_screen(
            "DISCOVERING",
            ["Scanning network..."],
            progress_ratio=0,
            animate=True,
            title_icon=WIFI_ICON,
        )
    
    found_peers = []
    
    def on_peer_update(peers):
        """Called when peers list changes."""
        nonlocal found_peers
        found_peers = peers
    
    # Run discovery in thread
    def discover_worker():
        nonlocal found_peers
        found_peers = disc.browse_peers(timeout_seconds=5.0, on_update=on_peer_update)
    
    thread = threading.Thread(target=discover_worker, daemon=True)
    thread.start()
    
    # Show progress while discovering
    start_time = time.time()
    while thread.is_alive():
        elapsed = time.time() - start_time
        progress = min(1.0, elapsed / 5.0)
        
        if found_peers:
            screens.render_progress_screen(
                "DISCOVERING",
                [f"Found {len(found_peers)} device(s)"],
                progress_ratio=progress,
                animate=False,
                title_icon=WIFI_ICON,
            )
        else:
            show_scanning()
        
        time.sleep(0.1)
    
    thread.join()
    disc.shutdown()
    
    return found_peers


def _enter_pin() -> Optional[str]:
    """Show PIN entry UI.
    
    Returns:
        4-digit PIN string, or None if cancelled
    """
    digits = [0, 0, 0, 0]
    cursor_pos = 0
    
    def render_screen():
        pin_display = "".join(str(d) for d in digits)
        formatted = " ".join(pin_display)
        
        # Highlight current digit
        lines = [
            "ENTER PIN",
            "From destination",
            "",
            f"  {formatted}",
            f"  {'  ' * cursor_pos}^",
        ]
        
        display.display_lines(lines)
    
    render_screen()
    menus.wait_for_buttons_release(
        [gpio.PIN_U, gpio.PIN_D, gpio.PIN_L, gpio.PIN_R, gpio.PIN_A, gpio.PIN_B]
    )
    
    while True:
        render_screen()
        
        if gpio.is_pressed(gpio.PIN_U):
            # Increment digit
            digits[cursor_pos] = (digits[cursor_pos] + 1) % 10
            time.sleep(0.15)
        
        elif gpio.is_pressed(gpio.PIN_D):
            # Decrement digit
            digits[cursor_pos] = (digits[cursor_pos] - 1) % 10
            time.sleep(0.15)
        
        elif gpio.is_pressed(gpio.PIN_R):
            # Move cursor right
            if cursor_pos < 3:
                cursor_pos += 1
            time.sleep(0.15)
        
        elif gpio.is_pressed(gpio.PIN_L):
            # Move cursor left
            if cursor_pos > 0:
                cursor_pos -= 1
            time.sleep(0.15)
        
        elif gpio.is_pressed(gpio.PIN_B):
            # Confirm
            return "".join(str(d) for d in digits)
        
        elif gpio.is_pressed(gpio.PIN_A):
            # Cancel
            return None
        
        time.sleep(0.05)


def _execute_network_transfer(
    images: list[DiskImage],
    peer: discovery.PeerDevice,
    pin: str,
) -> None:
    """Execute network transfer with progress display."""
    
    done = threading.Event()
    progress_lock = threading.Lock()
    current_image = [""]
    progress_ratio = [0.0]
    success_count = [0]
    failure_count = [0]
    error_message = [""]
    
    def progress_callback(image_name: str, ratio: float):
        """Called by transfer client to report progress."""
        with progress_lock:
            current_image[0] = image_name
            progress_ratio[0] = ratio
    
    def worker():
        """Background thread for async network transfer."""
        try:
            # Run async code in thread
            asyncio.run(_async_transfer(images, peer, pin, progress_callback, success_count, failure_count, error_message))
        except Exception as e:
            log.error(f"Network transfer failed: {e}")
            with progress_lock:
                error_message[0] = str(e)
            failure_count[0] = len(images)
        finally:
            done.set()
    
    # Start background thread
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    
    # Show progress
    while not done.is_set():
        with progress_lock:
            img_name = current_image[0] or "Authenticating..."
            ratio = progress_ratio[0]
            err = error_message[0]
        
        if err:
            # Show error and exit
            screens.render_error_screen(
                "NETWORK TRANSFER",
                message=err[:40],  # Truncate long errors
                title_icon=WIFI_ICON,
                message_icon=ALERT_ICON,
                message_icon_size=24,
            )
            time.sleep(3)
            return
        
        # Truncate long image names
        if len(img_name) > 20:
            img_name = img_name[:17] + "..."
        
        screens.render_progress_screen(
            "SENDING",
            [img_name],
            progress_ratio=ratio,
            animate=False,
            title_icon=WIFI_ICON,
        )
        time.sleep(0.1)
    
    thread.join()
    
    # Show final result
    success = success_count[0]
    failure = failure_count[0]
    
    if failure == 0:
        screens.render_status_template(
            "NETWORK TRANSFER",
            "SUCCESS",
            extra_lines=[
                f"Sent {success} image(s)",
                f"to {peer.hostname}",
                "Press A/B to continue.",
            ],
            title_icon=WIFI_ICON,
        )
    elif success == 0:
        screens.render_status_template(
            "NETWORK TRANSFER",
            "FAILED",
            extra_lines=[
                f"Failed to send {failure} image(s).",
                "Check logs for details.",
                "Press A/B to continue.",
            ],
            title_icon=WIFI_ICON,
        )
    else:
        screens.render_status_template(
            "NETWORK TRANSFER",
            "PARTIAL",
            extra_lines=[
                f"Sent: {success}",
                f"Failed: {failure}",
                "Check logs for details.",
                "Press A/B to continue.",
            ],
            title_icon=WIFI_ICON,
        )
    
    screens.wait_for_ack()


async def _async_transfer(
    images: list[DiskImage],
    peer: discovery.PeerDevice,
    pin: str,
    progress_callback,
    success_count: list,
    failure_count: list,
    error_message: list,
) -> None:
    """Async function to handle network transfer."""
    
    client = peer_transfer_client.TransferClient(peer)
    
    try:
        # Authenticate
        await client.authenticate(pin)
        
        # Send images
        success, failure = await client.send_images(images, progress_callback=progress_callback)
        
        success_count[0] = success
        failure_count[0] = failure
        
    except peer_transfer_client.AuthenticationError as e:
        log.error(f"Auth error: {e}")
        error_message[0] = f"Auth failed: {str(e)}"
        
    except peer_transfer_client.TransferError as e:
        log.error(f"Transfer error: {e}")
        error_message[0] = f"Transfer failed: {str(e)}"
