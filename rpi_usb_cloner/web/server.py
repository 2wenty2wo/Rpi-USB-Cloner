"""Minimal HTTP server for serving the OLED display buffer."""
from __future__ import annotations

import asyncio
import threading
from typing import Optional

from aiohttp import web

from rpi_usb_cloner.ui import display
from rpi_usb_cloner.hardware import gpio, virtual_gpio

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
FRAME_DELAY_SECONDS = 0.15


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

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Rpi USB Cloner</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      background: #0f1115;
      color: #f5f5f5;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      margin: 0;
      padding: 20px;
      box-sizing: border-box;
    }
    .panel {
      background: #1c1f26;
      border-radius: 12px;
      padding: 24px;
      max-width: 600px;
      width: 100%;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
    }
    h1 {
      font-size: 20px;
      margin: 0 0 12px;
      text-align: center;
    }
    .screen {
      background: #000;
      border: 2px solid #3a3f4b;
      border-radius: 6px;
      width: 100%;
      height: 200px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 24px;
      overflow: hidden;
    }
    .screen canvas {
      width: 100%;
      height: 100%;
      image-rendering: pixelated;
    }
    .controls-container {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 40px;
      padding: 0 20px;
    }
    /* D-pad on the left */
    .dpad-container {
      position: relative;
      width: 140px;
      height: 140px;
    }
    .dpad-btn {
      position: absolute;
      background: #000;
      border: none;
      color: #fff;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      user-select: none;
    }
    .dpad-btn:active {
      background: #333;
    }
    .dpad-center {
      position: absolute;
      width: 40px;
      height: 40px;
      background: #1c1f26;
      top: 50px;
      left: 50px;
      border-radius: 4px;
    }
    .dpad-up {
      width: 40px;
      height: 50px;
      left: 50px;
      top: 0;
      clip-path: polygon(20% 100%, 50% 0%, 80% 100%);
    }
    .dpad-down {
      width: 40px;
      height: 50px;
      left: 50px;
      bottom: 0;
      clip-path: polygon(20% 0%, 50% 100%, 80% 0%);
    }
    .dpad-left {
      width: 50px;
      height: 40px;
      left: 0;
      top: 50px;
      clip-path: polygon(100% 20%, 0% 50%, 100% 80%);
    }
    .dpad-right {
      width: 50px;
      height: 40px;
      right: 0;
      top: 50px;
      clip-path: polygon(0% 20%, 100% 50%, 0% 80%);
    }
    /* Action buttons on the right */
    .action-buttons {
      display: flex;
      flex-direction: column;
      gap: 20px;
      align-items: center;
    }
    .action-btn {
      width: 80px;
      height: 80px;
      border-radius: 50%;
      border: none;
      cursor: pointer;
      font-size: 16px;
      font-weight: bold;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      user-select: none;
    }
    .btn-back {
      background: #1a1a1a;
    }
    .btn-back:active {
      background: #333;
    }
    .btn-ok {
      background: #1a1a1a;
    }
    .btn-ok:active {
      background: #333;
    }
    .status {
      margin-top: 20px;
      text-align: center;
      font-size: 12px;
      color: #888;
    }
    .status.connected {
      color: #4a9;
    }
    .status.disconnected {
      color: #c44;
    }
  </style>
</head>
<body>
  <div class="panel">
    <h1>OLED Display</h1>
    <div class="screen">
      <canvas id="screen" width="128" height="64"></canvas>
    </div>
    <div class="controls-container">
      <!-- D-pad on the left -->
      <div class="dpad-container">
        <button class="dpad-btn dpad-up" data-button="UP"></button>
        <button class="dpad-btn dpad-down" data-button="DOWN"></button>
        <button class="dpad-btn dpad-left" data-button="LEFT"></button>
        <button class="dpad-btn dpad-right" data-button="RIGHT"></button>
        <div class="dpad-center"></div>
      </div>
      <!-- Action buttons on the right -->
      <div class="action-buttons">
        <button class="action-btn btn-back" data-button="BACK">BACK</button>
        <button class="action-btn btn-ok" data-button="OK">OK</button>
      </div>
    </div>
    <div class="status" id="status">Connecting...</div>
  </div>
  <script>
    const canvas = document.getElementById('screen');
    const ctx = canvas.getContext('2d');
    const statusEl = document.getElementById('status');
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const screenSocketUrl = `${protocol}//${window.location.host}/ws/screen`;
    const controlSocketUrl = `${protocol}//${window.location.host}/ws/control`;

    let screenSocket = null;
    let controlSocket = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;

    // Connect to screen WebSocket for display streaming
    function connectScreenSocket() {
      screenSocket = new WebSocket(screenSocketUrl);
      screenSocket.binaryType = 'arraybuffer';

      screenSocket.addEventListener('open', () => {
        console.log('Screen WebSocket connected');
        updateStatus();
      });

      screenSocket.addEventListener('message', async (event) => {
        const blob = new Blob([event.data], { type: 'image/png' });
        const bitmap = await createImageBitmap(blob);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        if (typeof bitmap.close === 'function') {
          bitmap.close();
        }
      });

      screenSocket.addEventListener('close', () => {
        console.log('Screen WebSocket disconnected');
        updateStatus();
        setTimeout(connectScreenSocket, 2000);
      });

      screenSocket.addEventListener('error', (err) => {
        console.error('Screen WebSocket error:', err);
      });
    }

    // Connect to control WebSocket for button presses
    function connectControlSocket() {
      controlSocket = new WebSocket(controlSocketUrl);

      controlSocket.addEventListener('open', () => {
        console.log('Control WebSocket connected');
        reconnectAttempts = 0;
        updateStatus();
      });

      controlSocket.addEventListener('close', () => {
        console.log('Control WebSocket disconnected');
        updateStatus();
        if (reconnectAttempts < maxReconnectAttempts) {
          reconnectAttempts++;
          setTimeout(connectControlSocket, 2000);
        }
      });

      controlSocket.addEventListener('error', (err) => {
        console.error('Control WebSocket error:', err);
      });
    }

    function updateStatus() {
      const screenConnected = screenSocket && screenSocket.readyState === WebSocket.OPEN;
      const controlConnected = controlSocket && controlSocket.readyState === WebSocket.OPEN;

      if (screenConnected && controlConnected) {
        statusEl.textContent = 'Connected';
        statusEl.className = 'status connected';
      } else if (screenConnected || controlConnected) {
        statusEl.textContent = 'Partially Connected';
        statusEl.className = 'status';
      } else {
        statusEl.textContent = 'Disconnected';
        statusEl.className = 'status disconnected';
      }
    }

    // Send button press to the server
    function sendButtonPress(button) {
      if (controlSocket && controlSocket.readyState === WebSocket.OPEN) {
        controlSocket.send(JSON.stringify({ button: button }));
        console.log('Button pressed:', button);
      } else {
        console.warn('Control socket not connected');
      }
    }

    // Add click handlers to all buttons
    document.querySelectorAll('[data-button]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const button = btn.getAttribute('data-button');
        sendButtonPress(button);
      });

      // Prevent text selection on touch devices
      btn.addEventListener('touchstart', (e) => {
        e.preventDefault();
        const button = btn.getAttribute('data-button');
        sendButtonPress(button);
      });
    });

    // Initialize connections
    connectScreenSocket();
    connectControlSocket();
  </script>
</body>
</html>
"""


def _build_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    }


async def handle_root(request: web.Request) -> web.Response:
    return web.Response(text=HTML_PAGE, content_type="text/html", headers=_build_headers())


async def handle_screen_png(request: web.Request) -> web.Response:
    png_bytes = display.get_display_png_bytes()
    return web.Response(body=png_bytes, content_type="image/png", headers=_build_headers())


async def handle_screen_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler that streams OLED display updates.

    This handler waits for display updates (dirty flag) before sending frames,
    which prevents flickering caused by capturing partial renders.
    """
    notifier = request.app["display_notifier"]
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)
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
    except Exception:
        pass
    finally:
        await ws.close()
    return ws


async def handle_control_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler for button control messages from the web UI.

    Receives button press commands and injects them as virtual GPIO events.
    Message format: {"button": "UP|DOWN|LEFT|RIGHT|BACK|OK"}
    """
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)

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
                        await ws.send_json({"error": f"Unknown button: {button}"})
                except (json.JSONDecodeError, KeyError) as e:
                    await ws.send_json({"error": f"Invalid message format: {e}"})
            elif msg.type == web.WSMsgType.ERROR:
                break
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
    finally:
        await ws.close()

    return ws


def start_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, log_debug=None):
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
        app.router.add_get("/", handle_root)
        app.router.add_get("/screen.png", handle_screen_png)
        app.router.add_get("/ws/screen", handle_screen_ws)
        app.router.add_get("/ws/control", handle_control_ws)

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
        runner_queue.put(("ok", runner))
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
    runner = payload
    return runner, thread
