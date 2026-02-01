"""Minimal HTTP server for serving the OLED display buffer."""

from __future__ import annotations

import asyncio
import pkgutil
import threading
import time
import weakref
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence, Union, cast

from aiohttp import WSCloseCode, web
from typing_extensions import TypeAlias

from rpi_usb_cloner.app.context import AppContext, LogEntry
from rpi_usb_cloner.hardware import gpio, virtual_gpio
from rpi_usb_cloner.logging import LoggerFactory
from rpi_usb_cloner.storage import image_repo
from rpi_usb_cloner.storage.device_lock import is_operation_active
from rpi_usb_cloner.ui import display
from rpi_usb_cloner.web.system_health import (
    SystemHealth,
    get_system_health,
    get_temperature_status,
    get_usage_status,
)


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
FRAME_DELAY_SECONDS = 0.15
REPO_STATS_REFRESH_SECONDS = 30.0


@dataclass
class ServerHandle:
    runner: web.AppRunner
    thread: threading.Thread
    loop: asyncio.AbstractEventLoop
    stop_event: threading.Event

    def stop(self, timeout: float = 5.0) -> None:
        if self.loop.is_running():
            self.stop_event.set()
            # Trigger graceful shutdown signal first
            self.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._trigger_shutdown())
            )
            # Give shutdown handler time to close WebSockets
            time.sleep(0.5)
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=timeout)

    async def _trigger_shutdown(self) -> None:
        """Trigger app shutdown signal for graceful WebSocket cleanup."""
        # This is called within the event loop
        # The actual cleanup is handled by on_shutdown signal


_current_handle: ServerHandle | None = None

# WebSocket connection tracking keys
WEBSOCKETS_KEY: web.AppKey[weakref.WeakSet[web.WebSocketResponse]] = web.AppKey(
    "websockets", cast(Any, weakref.WeakSet)
)


class DisplayUpdateNotifier:
    """Async notifier for display updates shared across websocket clients."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._condition = asyncio.Condition()
        self._update_id = 0

    def get_update_id(self) -> int:
        return self._update_id

    async def wait_for_update(self, last_update_id: int, timeout: float) -> int:
        async with self._condition:
            if self._update_id > last_update_id:
                return self._update_id
            try:
                await asyncio.wait_for(self._condition.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                return self._update_id
            return self._update_id

    async def _mark_update(self) -> None:
        async with self._condition:
            self._update_id += 1
            self._condition.notify_all()

    def mark_update_threadsafe(self) -> None:
        self._loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._mark_update())
        )


DISPLAY_NOTIFIER_KEY: web.AppKey[DisplayUpdateNotifier] = web.AppKey(
    "display_notifier", DisplayUpdateNotifier
)
DISPLAY_STOP_EVENT_KEY: web.AppKey[threading.Event] = web.AppKey(
    "display_stop_event", threading.Event
)
APP_CONTEXT_KEY: web.AppKey[AppContext | None] = web.AppKey("app_context", AppContext)


async def _on_shutdown(app: web.Application) -> None:
    """Gracefully close all WebSocket connections on shutdown.

    This signal handler ensures all connected clients receive a proper
    close code (WSCloseCode.GOING_AWAY) when the server is shutting down,
    rather than abruptly disconnecting.
    """
    log = LoggerFactory.for_web()
    websockets = app.get(WEBSOCKETS_KEY)
    if not websockets:
        return

    # Create a snapshot to avoid modification during iteration
    active_ws = set(websockets)
    if not active_ws:
        return

    log.info(
        f"Closing {len(active_ws)} WebSocket connection(s) gracefully",
        tags=["ws", "websocket", "shutdown"],
    )

    # Close all connections concurrently with timeout
    close_tasks = [_close_websocket_gracefully(ws, log) for ws in active_ws]
    await asyncio.gather(*close_tasks, return_exceptions=True)


async def _close_websocket_gracefully(ws: web.WebSocketResponse, log) -> None:
    """Close a single WebSocket connection with proper error handling."""
    try:
        if not ws.closed:
            await ws.close(code=WSCloseCode.GOING_AWAY, message=b"Server shutdown")
    except Exception as exc:
        log.debug(
            f"Error closing WebSocket: {exc}",
            tags=["ws", "websocket", "shutdown", "error"],
        )


def _register_websocket(app: web.Application, ws: web.WebSocketResponse) -> None:
    """Register a WebSocket connection for tracking.

    Uses WeakSet so connections are automatically removed when
    the WebSocketResponse is garbage collected.
    """
    websockets = app.get(WEBSOCKETS_KEY)
    if websockets is not None:
        websockets.add(ws)


def _unregister_websocket(app: web.Application, ws: web.WebSocketResponse) -> None:
    """Unregister a WebSocket connection."""
    websockets = app.get(WEBSOCKETS_KEY)
    if websockets is not None:
        websockets.discard(ws)


TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "index.html"


@lru_cache(maxsize=1)
def _load_template() -> str:
    template_bytes = pkgutil.get_data("rpi_usb_cloner.web", "templates/index.html")
    if template_bytes is not None:
        return template_bytes.decode("utf-8")
    if TEMPLATE_PATH.exists():
        return TEMPLATE_PATH.read_text(encoding="utf-8")
    raise FileNotFoundError(
        "Web UI template not found. Ensure templates/index.html is packaged."
    )


def _build_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    }


LogEntryLike: TypeAlias = Union[LogEntry, str]


def _diff_log_buffer(
    previous: Sequence[LogEntryLike], current: Sequence[LogEntryLike]
) -> tuple[list[LogEntryLike], bool]:
    previous_list = list(previous)
    current_list = list(current)
    if not previous_list:
        return current_list, bool(current_list)
    if previous_list == current_list:
        return [], False
    if current_list[: len(previous_list)] == previous_list:
        return current_list[len(previous_list) :], False
    max_overlap = min(len(previous_list), len(current_list))
    for overlap in range(max_overlap, 0, -1):
        if previous_list[-overlap:] == current_list[:overlap]:
            return current_list[overlap:], False
    return current_list, True


def _serialize_log_entries(entries: Sequence[LogEntryLike]) -> list[object]:
    serialized: list[object] = []
    for entry in entries:
        if isinstance(entry, LogEntry):
            serialized.append(
                {
                    "message": entry.message,
                    "level": entry.level,
                    "tags": list(entry.tags),
                    "timestamp": entry.timestamp.isoformat(),
                    "source": entry.source,
                    "details": dict(entry.details) if entry.details else None,
                }
            )
        else:
            serialized.append(str(entry))
    return serialized


def _build_health_payload(health: SystemHealth) -> dict[str, object]:
    response: dict[str, object] = {
        "cpu": {
            "percent": round(health.cpu_percent, 1),
            "status": get_usage_status(health.cpu_percent),
        },
        "memory": {
            "percent": round(health.memory_percent, 1),
            "used_mb": health.memory_used_mb,
            "total_mb": health.memory_total_mb,
            "status": get_usage_status(health.memory_percent),
        },
        "disk": {
            "percent": round(health.disk_percent, 1),
            "used_gb": round(health.disk_used_gb, 1),
            "total_gb": round(health.disk_total_gb, 1),
            "status": get_usage_status(health.disk_percent),
        },
        "temperature": None,
    }

    if health.temperature_celsius is not None:
        response["temperature"] = {
            "celsius": round(health.temperature_celsius, 1),
            "status": get_temperature_status(health.temperature_celsius),
        }
    return response


async def handle_root(request: web.Request) -> web.Response:
    return web.Response(
        text=_load_template(), content_type="text/html", headers=_build_headers()
    )


async def handle_screen_png(request: web.Request) -> web.Response:
    png_bytes = display.get_display_png_bytes()
    return web.Response(
        body=png_bytes, content_type="image/png", headers=_build_headers()
    )


async def handle_health(request: web.Request) -> web.Response:
    health = get_system_health()
    return web.json_response(_build_health_payload(health), headers=_build_headers())


async def handle_screen_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler that streams OLED display updates.

    This handler waits for display updates (dirty flag) before sending frames,
    which prevents flickering caused by capturing partial renders.
    """
    notifier = request.app[DISPLAY_NOTIFIER_KEY]
    log = LoggerFactory.for_web()
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)

    # Register for tracking
    _register_websocket(request.app, ws)
    connection_id = id(ws)

    log.debug(
        f"Screen WebSocket connected from {request.remote} (id={connection_id})",
        tags=["ws", "websocket", "connection"],
        connection_id=connection_id,
    )
    try:
        # Send initial frame
        png_bytes = display.get_display_png_bytes()
        await ws.send_bytes(png_bytes)
        display.clear_dirty_flag()

        last_update_id = notifier.get_update_id()
        while not ws.closed:
            # Wait for display to be updated (with timeout to keep connection alive)
            last_update_id = await notifier.wait_for_update(
                last_update_id, FRAME_DELAY_SECONDS
            )
            if ws.closed:
                break
            png_bytes = display.get_display_png_bytes()
            await ws.send_bytes(png_bytes)
            display.clear_dirty_flag()
    except asyncio.CancelledError:
        # Server shutdown - close gracefully
        raise
    except Exception as exc:
        log.warning(
            f"Screen WebSocket error: {exc}",
            tags=["ws", "websocket", "error"],
            connection_id=connection_id,
        )
    finally:
        _unregister_websocket(request.app, ws)
        if not ws.closed:
            await ws.close()
        log.debug(
            f"Screen WebSocket disconnected from {request.remote} (id={connection_id})",
            tags=["ws", "websocket", "connection"],
            connection_id=connection_id,
        )
    return ws


async def handle_control_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler for button control messages from the web UI.

    Receives button press commands and injects them as virtual GPIO events.
    Message format: {"button": "UP|DOWN|LEFT|RIGHT|BACK|OK"}
    """
    log = LoggerFactory.for_web()
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)

    # Register for tracking
    _register_websocket(request.app, ws)
    connection_id = id(ws)

    log.debug(
        f"Control WebSocket connected from {request.remote} (id={connection_id})",
        tags=["ws", "websocket", "connection"],
        connection_id=connection_id,
    )

    # Button name to GPIO pin mapping
    button_map = {
        "UP": gpio.PIN_U,
        "DOWN": gpio.PIN_D,
        "LEFT": gpio.PIN_L,
        "RIGHT": gpio.PIN_R,
        "BACK": gpio.PIN_A,  # A button on Pi
        "OK": gpio.PIN_B,  # B button on Pi
    }

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    import json

                    data = json.loads(msg.data)
                    button = data.get("button", "").upper()

                    if button in button_map:
                        pin = button_map[button]
                        virtual_gpio.inject_button_press(pin)
                        # Button presses are TRACE-level (very verbose)
                        log.trace(
                            f"Web UI button pressed: {button}",
                            tags=["web", "input", "button"],
                            connection_id=connection_id,
                        )
                    else:
                        log.warning(
                            f"Unknown control button payload: {data}",
                            tags=["web", "input", "error"],
                            connection_id=connection_id,
                        )
                        await ws.send_json({"error": f"Unknown button: {button}"})
                except (json.JSONDecodeError, KeyError) as e:
                    log.warning(
                        f"Invalid control payload: {msg.data} ({e})",
                        tags=["web", "input", "error"],
                        connection_id=connection_id,
                    )
                    await ws.send_json({"error": f"Invalid message format: {e}"})
            elif msg.type == web.WSMsgType.ERROR:
                log.debug(
                    f"Control WebSocket error: {ws.exception()}",
                    tags=["ws", "websocket", "error"],
                    connection_id=connection_id,
                )
                break
    except asyncio.CancelledError:
        # Server shutdown - close gracefully
        raise
    except Exception as exc:
        log.warning(
            f"Control WebSocket error: {exc}",
            tags=["ws", "websocket", "error"],
            connection_id=connection_id,
        )
    finally:
        _unregister_websocket(request.app, ws)
        if not ws.closed:
            await ws.close()
        log.debug(
            f"Control WebSocket disconnected from {request.remote} (id={connection_id})",
            tags=["ws", "websocket", "connection"],
            connection_id=connection_id,
        )

    return ws


async def handle_logs_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler that streams application log buffer updates."""
    log = LoggerFactory.for_web()
    app_context: AppContext | None = request.app.get(APP_CONTEXT_KEY)
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)

    # Register for tracking
    _register_websocket(request.app, ws)
    connection_id = id(ws)

    if not app_context:
        _unregister_websocket(request.app, ws)
        await ws.send_json({"type": "error", "message": "Log buffer unavailable"})
        await ws.close()
        return ws

    log.debug(
        f"Log WebSocket connected from {request.remote} (id={connection_id})",
        tags=["ws", "websocket", "connection"],
        connection_id=connection_id,
    )
    last_snapshot: list[LogEntryLike] = []
    try:
        snapshot: list[LogEntryLike] = list(app_context.log_buffer)
        if snapshot:
            await ws.send_json(
                {"type": "snapshot", "entries": _serialize_log_entries(snapshot)}
            )
        last_snapshot = snapshot
        while not ws.closed:
            await asyncio.sleep(0.5)
            current: list[LogEntryLike] = list(app_context.log_buffer)
            new_entries, reset = _diff_log_buffer(last_snapshot, current)
            if reset and current:
                await ws.send_json(
                    {"type": "snapshot", "entries": _serialize_log_entries(current)}
                )
            elif new_entries:
                await ws.send_json(
                    {"type": "append", "entries": _serialize_log_entries(new_entries)}
                )
            last_snapshot = current
    except asyncio.CancelledError:
        # Server shutdown - close gracefully
        raise
    except Exception as exc:
        log.warning(
            f"Log WebSocket error: {exc}",
            tags=["ws", "websocket", "error"],
            connection_id=connection_id,
        )
    finally:
        _unregister_websocket(request.app, ws)
        if not ws.closed:
            await ws.close()
        log.debug(
            f"Log WebSocket disconnected from {request.remote} (id={connection_id})",
            tags=["ws", "websocket", "connection"],
            connection_id=connection_id,
        )
    return ws


async def handle_health_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler that streams system health metrics.

    Sends CPU, memory, disk, and temperature data every 2 seconds.
    """
    log = LoggerFactory.for_web()
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)

    # Register for tracking
    _register_websocket(request.app, ws)
    connection_id = id(ws)

    log.debug(
        f"Health WebSocket connected from {request.remote} (id={connection_id})",
        tags=["ws", "websocket", "connection"],
        connection_id=connection_id,
    )

    try:
        while not ws.closed:
            health = get_system_health()

            await ws.send_json(_build_health_payload(health))
            await asyncio.sleep(2.0)  # Update every 2 seconds

    except asyncio.CancelledError:
        # Server shutdown - close gracefully
        raise
    except Exception as exc:
        log.warning(
            f"Health WebSocket error: {exc}",
            tags=["ws", "websocket", "error"],
            connection_id=connection_id,
        )
    finally:
        _unregister_websocket(request.app, ws)
        if not ws.closed:
            await ws.close()
        log.debug(
            f"Health WebSocket disconnected from {request.remote} (id={connection_id})",
            tags=["ws", "websocket", "connection"],
            connection_id=connection_id,
        )

    return ws


async def handle_devices_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler that streams USB device information.

    Sends list of detected USB devices with their status every 2 seconds.
    """
    log = LoggerFactory.for_web()
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)

    # Register for tracking
    _register_websocket(request.app, ws)
    connection_id = id(ws)

    log.debug(
        f"Devices WebSocket connected from {request.remote} (id={connection_id})",
        tags=["ws", "websocket", "connection"],
        connection_id=connection_id,
    )

    try:
        # Cache for when operations are in progress
        cached_device_list: list[dict] = []

        while not ws.closed:
            # Skip filesystem scanning if a device operation is in progress
            if is_operation_active():
                # Send cached data to keep connection alive
                await ws.send_json(
                    {"devices": cached_device_list, "operation_active": True}
                )
                await asyncio.sleep(2.0)
                continue

            from rpi_usb_cloner.services.drives import list_usb_disks_filtered
            from rpi_usb_cloner.storage.devices import get_children, human_size

            devices = list_usb_disks_filtered()

            # Build response with device information
            device_list = []
            for device in devices:
                name = device.get("name", "")
                size = device.get("size", 0)
                vendor = device.get("vendor", "").strip()
                model = device.get("model", "").strip()
                tran = device.get("tran", "")
                fstype = device.get("fstype", "")

                # Collect mountpoints
                mountpoints = []
                if device.get("mountpoint"):
                    mountpoints.append(device.get("mountpoint"))
                for child in get_children(device):
                    if child.get("mountpoint"):
                        mountpoints.append(child.get("mountpoint"))

                # Determine status
                if mountpoints:
                    status = "mounted"
                elif fstype:
                    status = "ready"
                else:
                    status = "unformatted"

                # Build device label
                device_label = (
                    f"{vendor} {model}".strip() if vendor or model else "Unknown Device"
                )

                device_list.append(
                    {
                        "name": name,
                        "path": f"/dev/{name}",
                        "size": size,
                        "size_formatted": human_size(size),
                        "vendor": vendor,
                        "model": model,
                        "label": device_label,
                        "transport": tran,
                        "fstype": fstype,
                        "mountpoints": mountpoints,
                        "status": status,
                    }
                )

            # Update cache for when operations are in progress
            cached_device_list = device_list

            await ws.send_json({"devices": device_list})
            await asyncio.sleep(2.0)  # Update every 2 seconds

    except asyncio.CancelledError:
        # Server shutdown - close gracefully
        raise
    except Exception as exc:
        log.warning(
            f"Devices WebSocket error: {exc}",
            tags=["ws", "websocket", "error"],
            connection_id=connection_id,
        )
    finally:
        _unregister_websocket(request.app, ws)
        if not ws.closed:
            await ws.close()
        log.debug(
            f"Devices WebSocket disconnected from {request.remote} (id={connection_id})",
            tags=["ws", "websocket", "connection"],
            connection_id=connection_id,
        )

    return ws


async def handle_images_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler that streams image repository contents."""
    log = LoggerFactory.for_web()
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)

    # Register for tracking
    _register_websocket(request.app, ws)
    connection_id = id(ws)

    log.debug(
        f"Images WebSocket connected from {request.remote} (id={connection_id})",
        tags=["ws", "websocket", "connection"],
        connection_id=connection_id,
    )

    try:
        repo_stats: dict[str, dict[str, dict[str, int] | int]] = {}
        repo_stats_task: (
            asyncio.Task[dict[str, dict[str, dict[str, int] | int]]] | None
        ) = None
        next_repo_stats_refresh = 0.0
        image_sizes: dict[str, int | None] = {}
        image_sizes_task: asyncio.Task[dict[str, int | None]] | None = None
        next_image_sizes_refresh = 0.0

        # Cache for when operations are in progress
        cached_payload: dict = {"images": [], "repo_stats": {}}

        while not ws.closed:
            # Skip filesystem scanning if a device operation is in progress
            if is_operation_active():
                # Send cached data to keep connection alive
                cached_payload["operation_active"] = True
                await ws.send_json(cached_payload)
                await asyncio.sleep(2.0)
                continue

            repos = image_repo.find_image_repos()
            image_list = []
            repo_images: dict[Path, list[image_repo.DiskImage]] = {}
            all_images: list[image_repo.DiskImage] = []

            for repo in repos:
                images = image_repo.list_clonezilla_images(repo.path)
                repo_images[repo.path] = images
                all_images.extend(images)

            now = time.monotonic()
            if now >= next_repo_stats_refresh and repo_stats_task is None:
                repo_stats_task = asyncio.create_task(
                    asyncio.to_thread(_build_repo_stats, repos)
                )
                next_repo_stats_refresh = now + REPO_STATS_REFRESH_SECONDS

            if now >= next_image_sizes_refresh and image_sizes_task is None:
                image_sizes_task = asyncio.create_task(
                    asyncio.to_thread(_build_image_sizes, all_images)
                )
                next_image_sizes_refresh = now + REPO_STATS_REFRESH_SECONDS

            if repo_stats_task is not None and repo_stats_task.done():
                try:
                    repo_stats = repo_stats_task.result()
                except Exception as exc:
                    log.warning(
                        f"Repo stats refresh failed: {exc}",
                        tags=["ws", "websocket", "error", "repo"],
                        connection_id=connection_id,
                    )
                repo_stats_task = None

            if image_sizes_task is not None and image_sizes_task.done():
                try:
                    image_sizes = image_sizes_task.result()
                except Exception as exc:
                    log.warning(
                        f"Image size refresh failed: {exc}",
                        tags=["ws", "websocket", "error", "repo"],
                        connection_id=connection_id,
                    )
                image_sizes_task = None

            for repo in repos:
                for image in repo_images.get(repo.path, []):
                    size_bytes = image.size_bytes
                    if size_bytes is None:
                        size_bytes = image_sizes.get(str(image.path))
                    image_list.append(
                        {
                            "name": image.name,
                            "path": str(image.path),
                            "type": image.image_type.value,
                            "repo_label": str(repo.path),
                            "size_bytes": size_bytes,
                        }
                    )

            # Update cache for when operations are in progress
            cached_payload = {"images": image_list, "repo_stats": repo_stats}

            await ws.send_json(cached_payload)
            await asyncio.sleep(2.0)

    except asyncio.CancelledError:
        # Server shutdown - close gracefully
        raise
    except Exception as exc:
        log.warning(
            f"Images WebSocket error: {exc}",
            tags=["ws", "websocket", "error"],
            connection_id=connection_id,
        )
    finally:
        _unregister_websocket(request.app, ws)
        if not ws.closed:
            await ws.close()
        log.debug(
            f"Images WebSocket disconnected from {request.remote} (id={connection_id})",
            tags=["ws", "websocket", "connection"],
            connection_id=connection_id,
        )

    return ws


def _build_repo_stats(
    repos: list[image_repo.ImageRepo],
) -> dict[str, dict[str, dict[str, int] | int]]:
    stats: dict[str, dict[str, dict[str, int] | int]] = {}
    for repo in repos:
        stats[str(repo.path)] = image_repo.get_repo_usage(repo)
    return stats


def _build_image_sizes(
    images: list[image_repo.DiskImage],
) -> dict[str, int | None]:
    sizes: dict[str, int | None] = {}
    for image in images:
        sizes[str(image.path)] = image_repo.get_image_size_bytes(image)
    return sizes


def is_running() -> bool:
    return _current_handle is not None and _current_handle.thread.is_alive()


def stop_server(timeout: float = 5.0, log_debug=None) -> bool:
    global _current_handle
    handle = _current_handle
    if handle is None:
        return False
    handle.stop(timeout=timeout)
    _current_handle = None
    log = LoggerFactory.for_web()
    log.info("Web server stopped")
    return True


def start_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    log_debug=None,
    app_context: AppContext | None = None,
):
    global _current_handle
    if is_running():
        return _current_handle
    runner_queue: queue.Queue[
        tuple[
            str,
            BaseException
            | tuple[web.AppRunner, asyncio.AbstractEventLoop, threading.Event],
        ]
    ]
    import queue

    runner_queue = queue.Queue(maxsize=1)

    def run_app() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = web.Application()

        # Initialize WebSocket tracking
        app[WEBSOCKETS_KEY] = weakref.WeakSet()

        # Register graceful shutdown handler
        app.on_shutdown.append(cast(Any, _on_shutdown))

        notifier = DisplayUpdateNotifier(loop)
        stop_event = threading.Event()
        app[DISPLAY_NOTIFIER_KEY] = notifier
        app[DISPLAY_STOP_EVENT_KEY] = stop_event
        app[APP_CONTEXT_KEY] = app_context
        app.router.add_get("/", handle_root)
        app.router.add_get("/health", handle_health)
        app.router.add_get("/screen.png", handle_screen_png)
        app.router.add_get("/ws/screen", handle_screen_ws)
        app.router.add_get("/ws/control", handle_control_ws)
        app.router.add_get("/ws/logs", handle_logs_ws)
        app.router.add_get("/ws/health", handle_health_ws)
        app.router.add_get("/ws/devices", handle_devices_ws)
        app.router.add_get("/ws/images", handle_images_ws)
        static_dir = Path(__file__).resolve().parent / "static"
        app.router.add_static("/static/", str(static_dir))
        ui_assets_dir = Path(__file__).resolve().parents[1] / "ui" / "assets"
        if ui_assets_dir.is_dir():
            app.router.add_static("/ui-assets/", str(ui_assets_dir))
        elif log_debug:
            log_debug(f"UI assets directory missing: {ui_assets_dir}")

        def notify_display_updates() -> None:
            while not stop_event.is_set():
                updated = display.wait_for_display_update(FRAME_DELAY_SECONDS)
                if stop_event.is_set():
                    break
                if updated:
                    notifier.mark_update_threadsafe()
                    display.clear_dirty_flag()

        async def start_site() -> web.AppRunner:
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host, port)
            await site.start()
            return runner

        runner: web.AppRunner | None = None
        try:
            runner = loop.run_until_complete(start_site())
        except Exception as exc:
            runner_queue.put(("error", exc))
            loop.close()
            return
        runner_queue.put(("ok", (runner, loop, stop_event)))
        log = LoggerFactory.for_web()
        log.info(f"Web server started at http://{host}:{port}")
        notifier_thread = threading.Thread(target=notify_display_updates, daemon=True)
        notifier_thread.start()
        try:
            loop.run_forever()
        finally:
            log.debug("Web server shutting down...", tags=["web", "shutdown"])
            stop_event.set()
            notifier_thread.join(timeout=1)
            # on_shutdown signal is triggered by runner.cleanup()
            # which closes WebSockets gracefully with WSCloseCode.GOING_AWAY
            loop.run_until_complete(runner.cleanup())
            loop.close()
            log.info("Web server stopped", tags=["web", "shutdown"])

    thread = threading.Thread(target=run_app, daemon=True)
    thread.start()
    try:
        status, payload = runner_queue.get(timeout=5)
    except queue.Empty as exc:
        raise TimeoutError("Web server failed to start within timeout.") from exc
    if status == "error":
        if isinstance(payload, BaseException):
            raise payload
        raise RuntimeError("Web server failed to start with an unknown error.")
    if not isinstance(payload, tuple):
        raise RuntimeError("Web server startup returned invalid payload.")
    runner, loop, stop_event = payload
    handle = ServerHandle(
        runner=runner,
        thread=thread,
        loop=loop,
        stop_event=stop_event,
    )
    _current_handle = handle
    return handle
