"""WiFi Direct transfer actions for peer-to-peer wireless transfers.

This module provides UI flows for hosting and joining WiFi Direct groups,
then reuses HTTP transfers from network_transfer_actions.
"""

from __future__ import annotations

import contextlib
import threading
import time

from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.hardware import gpio
from loguru import logger

from rpi_usb_cloner.services import discovery, wifi_direct
from rpi_usb_cloner.services.peer_transfer_server import TransferServer
from rpi_usb_cloner.storage import image_repo
from rpi_usb_cloner.ui import display, menus, screens
from rpi_usb_cloner.ui.icons import ALERT_ICON, FOLDER_ICON, WIFI_ICON

from .network_transfer_actions import (
    _enter_pin,
    _execute_network_transfer,
    _select_images_checklist,
)


log = logger.bind(source=__name__)


def wifi_direct_host(*, app_context: AppContext) -> None:
    """Host a WiFi Direct group and receive images.

    Flow:
    1. Check P2P support
    2. Select destination repo
    3. Start Group Owner
    4. Display network name + PIN
    5. Wait for connection + receive
    6. Cleanup
    """
    # Step 1: Check P2P support
    wd = wifi_direct.WiFiDirectService()

    if not wd.is_p2p_supported():
        screens.render_error_screen(
            "WIFI DIRECT",
            message="WiFi Direct not\\nsupported",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(2)
        return

    # Step 2: Select destination repo
    repos = image_repo.find_image_repos()

    if not repos:
        screens.render_error_screen(
            "WIFI DIRECT",
            message="No image repo found",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1.5)
        return

    if len(repos) > 1:
        repo_index = menus.select_list(
            "DESTINATION REPO",
            [repo.path.name for repo in repos],
            title_icon=FOLDER_ICON,
            transition_direction="forward",
        )
        if repo_index is None:
            return
        dest_repo = repos[repo_index]
    else:
        dest_repo = repos[0]

    # Step 3: Start Group Owner
    screens.render_progress_screen(
        "WIFI DIRECT",
        ["Starting group..."],
        progress_ratio=0,
        animate=True,
        title_icon=WIFI_ICON,
    )

    try:
        p2p_interface = wd.start_group_owner()
    except wifi_direct.WiFiDirectError as e:
        log.error(f"Failed to start GO: {e}")
        screens.render_error_screen(
            "WIFI DIRECT",
            message="Failed to start\\nWiFi Direct",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(2)
        return

    try:
        # Get group name
        group_name = wd.get_group_name() or "DIRECT-RpiCloner"
        go_ip = wd.get_p2p_ip() or "192.168.49.1"

        # Step 4: Start mDNS + HTTP server
        disc = discovery.DiscoveryService(port=8765)
        server = TransferServer(dest_repo, port=8765)

        # Generate PIN
        import asyncio

        pin = server._generate_pin()
        server_loop = asyncio.new_event_loop()

        def _run_server_loop() -> None:
            asyncio.set_event_loop(server_loop)
            server_loop.run_forever()
            server_loop.close()

        server_thread = threading.Thread(
            target=_run_server_loop, name="wifi-direct-server", daemon=True
        )
        server_thread.start()

        try:
            disc.start_publishing(lambda: pin)
            start_future = asyncio.run_coroutine_threadsafe(
                server.start(pin_callback=lambda: pin),
                server_loop,
            )
            start_future.result()
        except Exception as exc:
            log.error(f"Failed to start transfer services: {exc}")
            screens.render_error_screen(
                "WIFI DIRECT",
                message="Failed to start\\ntransfer services",
                title_icon=WIFI_ICON,
                message_icon=ALERT_ICON,
                message_icon_size=24,
            )
            return

        # Display info and wait
        _host_waiting_screen(group_name, pin, wd, server)

    finally:
        # Cleanup
        with contextlib.suppress(Exception):
            import asyncio

            if "server_loop" in locals() and server_loop.is_running():
                stop_future = asyncio.run_coroutine_threadsafe(
                    server.stop(), server_loop
                )
                stop_future.result(timeout=5)
                server_loop.call_soon_threadsafe(server_loop.stop)
            if "server_thread" in locals():
                server_thread.join(timeout=2)

        with contextlib.suppress(Exception):
            disc.shutdown()

        wd.stop_group_owner()
        log.info("WiFi Direct host session ended")


def _host_waiting_screen(
    group_name: str, pin: str, wd: wifi_direct.WiFiDirectService, server: TransferServer
) -> None:
    """Display waiting screen while hosting.

    Shows group name and PIN, waits for connection or cancel.
    """
    # Poll for transfers or cancel
    while True:
        progress = server.get_transfer_progress()

        if progress:
            # Active transfer
            img_name = list(progress.keys())[0]
            img_progress = progress[img_name]

            if len(img_name) > 18:
                img_name = img_name[:15] + "..."

            screens.render_progress_screen(
                "RECEIVING",
                [img_name],
                progress_ratio=img_progress / 1e9 if img_progress > 0 else 0,
                animate=False,
                title_icon=WIFI_ICON,
            )
        else:
            # Waiting for connection
            lines = [
                "WIFI DIRECT HOST",
                "",
                "Network:",
                f"  {group_name[:20]}",
                "",
                f"PIN: {pin}",
            ]
            display.display_lines(lines)

        # Check for cancel
        if gpio.is_pressed(gpio.PIN_A) or gpio.is_pressed(gpio.PIN_B):
            break

        time.sleep(0.1)


def wifi_direct_join(*, app_context: AppContext) -> None:
    """Join a WiFi Direct group and send images.

    Flow:
    1. Check P2P support
    2. Select source repo + images
    3. Scan for groups
    4. Connect to group
    5. Discover peer via mDNS
    6. Enter PIN + send
    """
    # Step 1: Check P2P support
    wd = wifi_direct.WiFiDirectService()

    if not wd.is_p2p_supported():
        screens.render_error_screen(
            "WIFI DIRECT",
            message="WiFi Direct not\\nsupported",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(2)
        return

    # Step 2: Select source repo
    repos = image_repo.find_image_repos()

    if not repos:
        screens.render_error_screen(
            "WIFI DIRECT",
            message="No image repo found",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1.5)
        return

    if len(repos) > 1:
        repo_index = menus.select_list(
            "SOURCE REPO",
            [repo.path.name for repo in repos],
            title_icon=FOLDER_ICON,
            transition_direction="forward",
        )
        if repo_index is None:
            return
        source_repo = repos[repo_index]
    else:
        source_repo = repos[0]

    # Get images
    all_images = image_repo.list_clonezilla_images(source_repo.path)

    if not all_images:
        screens.render_error_screen(
            "WIFI DIRECT",
            message="No images found",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1.5)
        return

    # Select images
    selected_flags = _select_images_checklist([img.name for img in all_images])

    if selected_flags is None:
        return

    selected_images = [img for i, img in enumerate(all_images) if selected_flags[i]]

    if not selected_images:
        screens.render_error_screen(
            "WIFI DIRECT",
            message="No images selected",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(1.5)
        return

    # Step 3: Scan for WiFi Direct groups
    screens.render_progress_screen(
        "SCANNING",
        ["Finding WiFi Direct..."],
        progress_ratio=0,
        animate=True,
        title_icon=WIFI_ICON,
    )

    peers = wd.find_peers(timeout=10)

    if not peers:
        screens.render_error_screen(
            "WIFI DIRECT",
            message="No groups found\\nMake sure host is ready",
            title_icon=WIFI_ICON,
            message_icon=ALERT_ICON,
            message_icon_size=24,
        )
        time.sleep(2)
        return

    # Step 4: Select group
    peer_index = menus.select_list(
        "SELECT GROUP",
        [p.name for p in peers],
        title_icon=WIFI_ICON,
        transition_direction="forward",
    )

    if peer_index is None:
        return

    selected_peer = peers[peer_index]

    # Step 5: Connect
    screens.render_progress_screen(
        "CONNECTING",
        [selected_peer.name[:20]],
        progress_ratio=0,
        animate=True,
        title_icon=WIFI_ICON,
    )

    try:
        if not wd.connect_to_group(selected_peer.address):
            screens.render_error_screen(
                "WIFI DIRECT",
                message="Connection failed",
                title_icon=WIFI_ICON,
                message_icon=ALERT_ICON,
                message_icon_size=24,
            )
            time.sleep(2)
            return

        # Step 6: Discover peer via mDNS
        screens.render_progress_screen(
            "DISCOVERING",
            ["Finding receiver..."],
            progress_ratio=0,
            animate=True,
            title_icon=WIFI_ICON,
        )

        disc = discovery.DiscoveryService()
        mdns_peers = disc.browse_peers(timeout_seconds=5.0)
        disc.shutdown()

        if not mdns_peers:
            screens.render_error_screen(
                "WIFI DIRECT",
                message="Peer not found\\nCheck host is ready",
                title_icon=WIFI_ICON,
                message_icon=ALERT_ICON,
                message_icon_size=24,
            )
            time.sleep(2)
            wd.disconnect()
            return

        # Use first peer (should be the GO)
        peer = mdns_peers[0]

        # Step 7: Enter PIN + send
        pin = _enter_pin()

        if pin is None:
            wd.disconnect()
            return

        _execute_network_transfer(selected_images, peer, pin)

    finally:
        wd.disconnect()
        log.info("WiFi Direct join session ended")
