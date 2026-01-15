"""Minimal HTTP server for serving the OLED display buffer."""
from __future__ import annotations

import asyncio
import threading
from typing import Optional

from aiohttp import web

from rpi_usb_cloner.ui import display

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
FRAME_DELAY_SECONDS = 0.15

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
    }
    .panel {
      background: #1c1f26;
      border-radius: 12px;
      padding: 24px;
      width: 360px;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
    }
    h1 {
      font-size: 20px;
      margin: 0 0 12px;
    }
    .screen {
      background: #000;
      border: 2px solid #3a3f4b;
      border-radius: 6px;
      width: 100%;
      height: 180px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 16px;
      overflow: hidden;
    }
    .screen canvas {
      width: 100%;
      height: 100%;
      image-rendering: pixelated;
    }
    .buttons {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }
    button {
      background: #2a2f3a;
      border: 1px solid #3c4250;
      color: #f5f5f5;
      padding: 10px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
    }
    button:active {
      background: #3b4252;
    }
  </style>
</head>
<body>
  <div class="panel">
    <h1>OLED Display</h1>
    <div class="screen">
      <canvas id="screen" width="128" height="64"></canvas>
    </div>
    <div class="buttons">
      <button>UP</button>
      <button>SELECT</button>
      <button>DOWN</button>
      <button>LEFT</button>
      <button>OK</button>
      <button>RIGHT</button>
    </div>
  </div>
  <script>
    const canvas = document.getElementById('screen');
    const ctx = canvas.getContext('2d');
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socketUrl = `${protocol}//${window.location.host}/ws/screen`;
    const socket = new WebSocket(socketUrl);
    socket.binaryType = 'arraybuffer';

    socket.addEventListener('message', async (event) => {
      const blob = new Blob([event.data], { type: 'image/png' });
      const bitmap = await createImageBitmap(blob);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      if (typeof bitmap.close === 'function') {
        bitmap.close();
      }
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
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)
    try:
        # Send initial frame
        png_bytes = display.get_display_png_bytes()
        await ws.send_bytes(png_bytes)
        display.clear_dirty_flag()

        while not ws.closed:
            # Wait for display to be updated (with timeout to keep connection alive)
            await asyncio.get_event_loop().run_in_executor(
                None, display.wait_for_display_update, FRAME_DELAY_SECONDS
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


def start_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, log_debug=None):
    runner_queue: "queue.Queue[tuple[str, object]]"
    import queue

    runner_queue = queue.Queue(maxsize=1)

    def run_app() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = web.Application()
        app.router.add_get("/", handle_root)
        app.router.add_get("/screen.png", handle_screen_png)
        app.router.add_get("/ws/screen", handle_screen_ws)

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
        try:
            loop.run_forever()
        finally:
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
