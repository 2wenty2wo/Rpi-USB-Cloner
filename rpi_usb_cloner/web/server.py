"""Minimal HTTP server for serving the OLED display buffer."""
from __future__ import annotations

import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rpi_usb_cloner.ui import display

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000

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
    }
    .screen img {
      width: 100%;
      height: 100%;
      object-fit: contain;
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
      <img src="/screen.png" alt="OLED screen preview" />
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
</body>
</html>
"""


class DisplayRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path.startswith("/screen.png"):
            png_bytes = display.get_display_png_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(len(png_bytes)))
            self.end_headers()
            self.wfile.write(png_bytes)
            return
        if self.path == "/" or self.path.startswith("/?"):
            body = HTML_PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def log_message(self, format: str, *args) -> None:
        return


def start_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, log_debug=None):
    server = ThreadingHTTPServer((host, port), DisplayRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if log_debug:
        log_debug(f"Web server started at http://{host}:{port}")
    return server, thread
