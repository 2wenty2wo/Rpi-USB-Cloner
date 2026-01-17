"""Minimal HTTP server for serving the OLED display buffer."""
from __future__ import annotations

import asyncio
import pkgutil
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from aiohttp import web

from rpi_usb_cloner.app.context import AppContext, LogEntry
from rpi_usb_cloner.ui import display
from rpi_usb_cloner.hardware import gpio, virtual_gpio

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
FRAME_DELAY_SECONDS = 0.15


@dataclass
class ServerHandle:
    runner: web.AppRunner
    thread: threading.Thread
    loop: asyncio.AbstractEventLoop
    stop_event: threading.Event

    def stop(self, timeout: float = 5.0) -> None:
        if self.loop.is_running():
            self.stop_event.set()
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=timeout)


_current_handle: Optional[ServerHandle] = None


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
        self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self._mark_update()))

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


def _diff_log_buffer(
    previous: list[LogEntry | str], current: list[LogEntry | str]
) -> tuple[list[LogEntry | str], bool]:
    if not previous:
        return current, bool(current)
    if previous == current:
        return [], False
    if current[: len(previous)] == previous:
        return current[len(previous) :], False
    max_overlap = min(len(previous), len(current))
    for overlap in range(max_overlap, 0, -1):
        if previous[-overlap:] == current[:overlap]:
            return current[overlap:], False
    return current, True


def _serialize_log_entries(entries: list[LogEntry | str]) -> list[object]:
    serialized: list[object] = []
    for entry in entries:
        if isinstance(entry, LogEntry):
            serialized.append(entry.to_dict())
        else:
            serialized.append(str(entry))
    return serialized


async def handle_root(request: web.Request) -> web.Response:
    return web.Response(
        text=_load_template(), content_type="text/html", headers=_build_headers()
    )


async def handle_screen_png(request: web.Request) -> web.Response:
    png_bytes = display.get_display_png_bytes()
    return web.Response(body=png_bytes, content_type="image/png", headers=_build_headers())


async def handle_screen_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler that streams OLED display updates.

    This handler waits for display updates (dirty flag) before sending frames,
    which prevents flickering caused by capturing partial renders.
    """
    notifier = request.app["display_notifier"]
    log_debug = request.app.get("log_debug")
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)
    if log_debug:
        log_debug(f"Screen WebSocket connected from {request.remote}")
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
        raise
    except Exception as exc:
        if log_debug:
            log_debug(f"Screen WebSocket error: {exc}")
    finally:
        await ws.close()
        if log_debug:
            log_debug(f"Screen WebSocket disconnected from {request.remote}")
    return ws


async def handle_control_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler for button control messages from the web UI.

    Receives button press commands and injects them as virtual GPIO events.
    Message format: {"button": "UP|DOWN|LEFT|RIGHT|BACK|OK"}
    """
    log_debug = request.app.get("log_debug")
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)
    if log_debug:
        log_debug(f"Control WebSocket connected from {request.remote}")

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
                    else:
                        if log_debug:
                            log_debug(f"Unknown control button payload: {data}")
                        await ws.send_json({"error": f"Unknown button: {button}"})
                except (json.JSONDecodeError, KeyError) as e:
                    if log_debug:
                        log_debug(f"Invalid control payload: {msg.data} ({e})")
                    await ws.send_json({"error": f"Invalid message format: {e}"})
            elif msg.type == web.WSMsgType.ERROR:
                break
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if log_debug:
            log_debug(f"Control WebSocket error: {exc}")
    finally:
        await ws.close()
        if log_debug:
            log_debug(f"Control WebSocket disconnected from {request.remote}")

    return ws


async def handle_logs_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler that streams application log buffer updates."""
    log_debug = request.app.get("log_debug")
    app_context: Optional[AppContext] = request.app.get("app_context")
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)
    if not app_context:
        await ws.send_json({"type": "error", "message": "Log buffer unavailable"})
        await ws.close()
        return ws
    if log_debug:
        log_debug(f"Log WebSocket connected from {request.remote}")
    last_snapshot: list[LogEntry | str] = []
    try:
        snapshot = list(app_context.log_buffer)
        if snapshot:
            await ws.send_json({"type": "snapshot", "entries": _serialize_log_entries(snapshot)})
        last_snapshot = snapshot
        while not ws.closed:
            await asyncio.sleep(0.5)
            current = list(app_context.log_buffer)
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
        raise
    except Exception as exc:
        if log_debug:
            log_debug(f"Log WebSocket error: {exc}")
    finally:
        await ws.close()
        if log_debug:
            log_debug(f"Log WebSocket disconnected from {request.remote}")
    return ws


def is_running() -> bool:
    return _current_handle is not None and _current_handle.thread.is_alive()


def stop_server(timeout: float = 5.0, log_debug=None) -> bool:
    global _current_handle
    handle = _current_handle
    if handle is None:
        return False
    handle.stop(timeout=timeout)
    _current_handle = None
    if log_debug:
        log_debug("Web server stopped")
    return True


def start_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    log_debug=None,
    app_context: Optional[AppContext] = None,
):
    global _current_handle
    if is_running():
        return _current_handle
    runner_queue: "queue.Queue[tuple[str, object]]"
    import queue

    runner_queue = queue.Queue(maxsize=1)

    def run_app() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = web.Application()
        notifier = DisplayUpdateNotifier(loop)
        stop_event = threading.Event()
        app["display_notifier"] = notifier
        app["display_stop_event"] = stop_event
        app["log_debug"] = log_debug
        app["app_context"] = app_context
        app.router.add_get("/", handle_root)
        app.router.add_get("/screen.png", handle_screen_png)
        app.router.add_get("/ws/screen", handle_screen_ws)
        app.router.add_get("/ws/control", handle_control_ws)
        app.router.add_get("/ws/logs", handle_logs_ws)
        static_dir = Path(__file__).resolve().parent / "static"
        app.router.add_static("/static/", str(static_dir))

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

        try:
            runner = loop.run_until_complete(start_site())
        except Exception as exc:
            runner_queue.put(("error", exc))
            loop.close()
            return
        runner_queue.put(("ok", (runner, loop, stop_event)))
        if log_debug:
            log_debug(f"Web server started at http://{host}:{port}")
        notifier_thread = threading.Thread(
            target=notify_display_updates, daemon=True
        )
        notifier_thread.start()
        try:
            loop.run_forever()
        finally:
            stop_event.set()
            notifier_thread.join(timeout=1)
            loop.run_until_complete(runner.cleanup())
            loop.close()

    thread = threading.Thread(target=run_app, daemon=True)
    thread.start()
    try:
        status, payload = runner_queue.get(timeout=5)
    except queue.Empty as exc:
        raise TimeoutError("Web server failed to start within timeout.") from exc
    if status == "error":
        raise payload
    runner, loop, stop_event = payload
    handle = ServerHandle(
        runner=runner,
        thread=thread,
        loop=loop,
        stop_event=stop_event,
    )
    _current_handle = handle
    return handle
