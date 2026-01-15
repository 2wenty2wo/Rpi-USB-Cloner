"""Minimal HTTP server for serving the OLED display buffer."""
from __future__ import annotations

import asyncio
import json
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
      margin: 0 0 16px;
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
    .controls {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 40px;
    }
    .dpad {
      display: grid;
      grid-template-columns: 60px 60px 60px;
      grid-template-rows: 60px 60px 60px;
      gap: 8px;
      flex-shrink: 0;
    }
    .action-buttons {
      display: flex;
      flex-direction: column;
      gap: 16px;
      flex-shrink: 0;
    }
    button {
      background: #2a2f3a;
      border: 2px solid #3c4250;
      color: #f5f5f5;
      border-radius: 50%;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
      transition: all 0.1s ease;
      user-select: none;
      -webkit-user-select: none;
      -webkit-tap-highlight-color: transparent;
    }
    button:active {
      background: #4a5568;
      border-color: #5a6478;
      transform: scale(0.95);
    }
    .dpad button {
      width: 60px;
      height: 60px;
      font-size: 18px;
    }
    .dpad .btn-up {
      grid-column: 2;
      grid-row: 1;
    }
    .dpad .btn-down {
      grid-column: 2;
      grid-row: 3;
    }
    .dpad .btn-left {
      grid-column: 1;
      grid-row: 2;
    }
    .dpad .btn-right {
      grid-column: 3;
      grid-row: 2;
    }
    .action-buttons button {
      width: 80px;
      height: 80px;
      font-size: 12px;
    }
    .status {
      margin-top: 16px;
      padding: 12px;
      background: #2a2f3a;
      border-radius: 6px;
      text-align: center;
      font-size: 12px;
      color: #9ca3af;
    }
    .status.connected {
      color: #10b981;
    }
    .status.error {
      color: #ef4444;
    }
  </style>
</head>
<body>
  <div class="panel">
    <h1>Rpi USB Cloner - Remote Control</h1>
    <div class="screen">
      <canvas id="screen" width="128" height="64"></canvas>
    </div>
    <div class="controls">
      <div class="dpad">
        <button class="btn-up" data-button="up">▲</button>
        <button class="btn-down" data-button="down">▼</button>
        <button class="btn-left" data-button="left">◄</button>
        <button class="btn-right" data-button="right">►</button>
      </div>
      <div class="action-buttons">
        <button data-button="ok">OK</button>
        <button data-button="back">BACK</button>
      </div>
    </div>
    <div id="status" class="status">Connecting...</div>
  </div>
  <script>
    const canvas = document.getElementById('screen');
    const ctx = canvas.getContext('2d');
    const statusEl = document.getElementById('status');
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

    // WebSocket for display updates
    const displaySocketUrl = `${protocol}//${window.location.host}/ws/screen`;
    const displaySocket = new WebSocket(displaySocketUrl);
    displaySocket.binaryType = 'arraybuffer';

    // WebSocket for button presses
    const buttonSocketUrl = `${protocol}//${window.location.host}/ws/button`;
    const buttonSocket = new WebSocket(buttonSocketUrl);

    displaySocket.addEventListener('open', () => {
      console.log('Display socket connected');
      checkConnectionStatus();
    });

    buttonSocket.addEventListener('open', () => {
      console.log('Button socket connected');
      checkConnectionStatus();
    });

    displaySocket.addEventListener('message', async (event) => {
      const blob = new Blob([event.data], { type: 'image/png' });
      const bitmap = await createImageBitmap(blob);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      if (typeof bitmap.close === 'function') {
        bitmap.close();
      }
    });

    displaySocket.addEventListener('close', () => {
      console.log('Display socket disconnected');
      statusEl.textContent = 'Disconnected - Attempting to reconnect...';
      statusEl.className = 'status error';
    });

    buttonSocket.addEventListener('close', () => {
      console.log('Button socket disconnected');
      statusEl.textContent = 'Disconnected - Attempting to reconnect...';
      statusEl.className = 'status error';
    });

    function checkConnectionStatus() {
      if (displaySocket.readyState === WebSocket.OPEN && buttonSocket.readyState === WebSocket.OPEN) {
        statusEl.textContent = 'Connected';
        statusEl.className = 'status connected';
      }
    }

    // Button press handler
    function sendButtonPress(button) {
      if (buttonSocket.readyState === WebSocket.OPEN) {
        buttonSocket.send(JSON.stringify({ button }));
        console.log('Button pressed:', button);
      } else {
        console.error('Button socket not ready');
      }
    }

    // Add click/touch handlers to all buttons
    document.querySelectorAll('button[data-button]').forEach(btn => {
      const buttonName = btn.getAttribute('data-button');

      btn.addEventListener('click', (e) => {
        e.preventDefault();
        sendButtonPress(buttonName);
      });

      // Prevent context menu on long press
      btn.addEventListener('contextmenu', (e) => {
        e.preventDefault();
      });

      // Prevent double-tap zoom on mobile
      let lastTap = 0;
      btn.addEventListener('touchend', (e) => {
        const currentTime = new Date().getTime();
        const tapLength = currentTime - lastTap;
        if (tapLength < 300 && tapLength > 0) {
          e.preventDefault();
        }
        lastTap = currentTime;
      });
    });
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


async def handle_button_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler for button press events from web UI.

    Receives button press messages and injects them as virtual GPIO events.
    """
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)

    # Button name to GPIO pin mapping
    button_map = {
        "up": gpio.PIN_U,
        "down": gpio.PIN_D,
        "left": gpio.PIN_L,
        "right": gpio.PIN_R,
        "back": gpio.PIN_A,
        "ok": gpio.PIN_B,
    }

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    button_name = data.get("button", "").lower()
                    if button_name in button_map:
                        pin = button_map[button_name]
                        virtual_gpio.inject_button_press(pin)
                        # Send acknowledgment
                        await ws.send_json({"status": "ok", "button": button_name})
                    else:
                        await ws.send_json({"status": "error", "message": "Unknown button"})
                except (json.JSONDecodeError, KeyError) as e:
                    await ws.send_json({"status": "error", "message": str(e)})
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
        app.router.add_get("/ws/button", handle_button_ws)

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
