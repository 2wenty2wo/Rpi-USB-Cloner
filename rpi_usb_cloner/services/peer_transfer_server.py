"""HTTP server for receiving image transfers from peer devices.

Provides endpoints for PIN authentication and chunked file uploads.
"""

from __future__ import annotations

import random
import secrets
import time
from pathlib import Path
from typing import Callable

from aiohttp import web

from rpi_usb_cloner.domain import ImageRepo, ImageType
from rpi_usb_cloner.logging import get_logger
from rpi_usb_cloner.storage import image_repo


log = get_logger(source=__name__)

# Session management
_active_sessions: dict[str, dict] = {}  # token -> {created_at, pin, peer_ip}
SESSION_TIMEOUT = 600  # 10 minutes

# PIN authentication
_current_pin: str | None = None
_failed_attempts: dict[str, list[float]] = {}  # ip -> [timestamp, ...]
MAX_FAILED_ATTEMPTS = 3
RATE_LIMIT_WINDOW = 30  # seconds


class TransferServer:
    """HTTP server for receiving image transfers."""

    def __init__(self, destination_repo: ImageRepo, port: int = 8765):
        """Initialize transfer server.

        Args:
            destination_repo: ImageRepo where received images will be saved
            port: HTTP server port
        """
        self.destination_repo = destination_repo
        self.port = port
        self.app: web.Application | None = None
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self._transfer_progress: dict[str, float] = {}  # image_name -> progress
        self._on_progress_callback: Callable[[str, float], None] | None = None

    async def start(
        self,
        pin_callback: Callable[[], str] | None = None,
        on_progress: Callable[[str, float], None] | None = None,
    ) -> None:
        """Start HTTP server.

        Args:
            pin_callback: Optional callback to get current PIN (for display)
            on_progress: Optional callback for transfer progress updates
        """
        global _current_pin

        # Generate PIN if not provided
        _current_pin = pin_callback() if pin_callback else self._generate_pin()

        self._on_progress_callback = on_progress

        # Create aiohttp app
        self.app = web.Application()
        self.app.router.add_post("/auth", self._handle_auth)
        self.app.router.add_post("/transfer", self._handle_transfer_init)
        self.app.router.add_post("/upload/{image_name}", self._handle_upload)
        self.app.router.add_get("/status", self._handle_status)

        # Start server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await self.site.start()

        log.info(f"Transfer server started on port {self.port}, PIN: {_current_pin}")

    async def stop(self) -> None:
        """Gracefully shutdown server."""
        global _current_pin, _active_sessions

        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

        _current_pin = None
        _active_sessions.clear()
        log.info("Transfer server stopped")

    def get_current_pin(self) -> str | None:
        """Get the current PIN for display."""
        return _current_pin

    def get_transfer_progress(self) -> dict[str, float]:
        """Get current transfer progress for all images."""
        return self._transfer_progress.copy()

    def _generate_pin(self) -> str:
        """Generate a random 4-digit PIN."""
        return f"{random.randint(0, 9999):04d}"

    async def _handle_auth(self, request: web.Request) -> web.Response:
        """Handle POST /auth - PIN verification.

        Request: {"pin": "1234"}
        Response: {"token": "abc..."} or error
        """
        global _current_pin

        client_ip = request.remote or "unknown"

        # Check rate limiting
        if not self._check_rate_limit(client_ip):
            log.warning(f"Rate limit exceeded for {client_ip}")
            return web.json_response(
                {"error": "Too many failed attempts", "retry_after": RATE_LIMIT_WINDOW},
                status=429,
            )

        try:
            data = await request.json()
            submitted_pin = data.get("pin", "")

            if submitted_pin == _current_pin:
                # Generate session token
                token = secrets.token_urlsafe(32)
                _active_sessions[token] = {
                    "created_at": time.time(),
                    "pin": submitted_pin,
                    "peer_ip": client_ip,
                }

                log.info(f"Successful auth from {client_ip}")
                # Clear failed attempts on success
                _failed_attempts.pop(client_ip, None)

                return web.json_response({"token": token})
            # Record failed attempt
            self._record_failed_attempt(client_ip)
            log.warning(f"Failed auth attempt from {client_ip}")
            return web.json_response({"error": "Invalid PIN"}, status=401)

        except Exception as e:
            log.error(f"Auth error: {e}")
            return web.json_response({"error": "Bad request"}, status=400)

    async def _handle_transfer_init(self, request: web.Request) -> web.Response:
        """Handle POST /transfer - Initialize transfer, validate space.

        Request:
        {
          "images": [
            {"name": "test.iso", "type": "iso", "size_bytes": 1000000},
            ...
          ]
        }

        Response: {"transfer_id": "xyz", "accepted": true}
        """
        # Verify session token
        if not self._verify_token(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            data = await request.json()
            images = data.get("images", [])

            if not images:
                return web.json_response({"error": "No images specified"}, status=400)

            # Calculate required space
            total_size = sum(img.get("size_bytes", 0) for img in images)

            # Check available space
            usage = image_repo.get_repo_usage(self.destination_repo)
            available = usage["free_bytes"]

            if total_size > available:
                log.warning(f"Insufficient space: need {total_size}, have {available}")
                return web.json_response(
                    {
                        "error": "Insufficient space",
                        "required": total_size,
                        "available": available,
                    },
                    status=507,
                )

            # Generate transfer ID
            transfer_id = secrets.token_hex(16)

            log.info(
                f"Transfer initialized: {len(images)} images, {total_size} bytes (ID: {transfer_id})"
            )
            return web.json_response({"transfer_id": transfer_id, "accepted": True})

        except Exception as e:
            log.error(f"Transfer init error: {e}")
            return web.json_response({"error": "Bad request"}, status=400)

    async def _handle_upload(self, request: web.Request) -> web.Response:
        """Handle POST /upload/{image_name} - Receive file upload.

        Headers:
          Authorization: Bearer {token}
          X-Image-Type: iso | clonezilla_dir | imageusb_bin
          Content-Type: application/octet-stream OR multipart/form-data

        Body: Binary stream or multipart data
        """
        # Verify session token
        if not self._verify_token(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        image_name = request.match_info["image_name"]
        image_type_str = request.headers.get("X-Image-Type", "iso")

        try:
            # Parse image type
            image_type = ImageType[
                image_type_str.upper().replace("CLONEZILLA_DIR", "CLONEZILLA_DIR")
            ]

            # Determine destination path
            if image_type == ImageType.CLONEZILLA_DIR:
                dest_base = self.destination_repo.path / "clonezilla"
                dest_base.mkdir(exist_ok=True)
                dest_path = dest_base / image_name
            else:
                dest_path = self.destination_repo.path / image_name

            # Handle multipart (for directories) vs binary stream
            content_type = request.headers.get("Content-Type", "")

            if "multipart/form-data" in content_type:
                received_bytes = await self._handle_multipart_upload(
                    request, dest_path, image_name
                )
            else:
                received_bytes = await self._handle_binary_upload(
                    request, dest_path, image_name
                )

            log.info(f"Upload complete: {image_name} ({received_bytes} bytes)")

            return web.json_response(
                {"received_bytes": received_bytes, "status": "complete"}
            )

        except Exception as e:
            log.error(f"Upload error for {image_name}: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_binary_upload(
        self, request: web.Request, dest_path: Path, image_name: str
    ) -> int:
        """Handle binary file upload (for ISOs and .BIN files)."""
        received_bytes = 0
        chunk_size = 1024 * 1024  # 1MB chunks

        with open(dest_path, "wb") as f:
            async for chunk in request.content.iter_chunked(chunk_size):
                f.write(chunk)
                received_bytes += len(chunk)

                # Update progress
                self._transfer_progress[image_name] = received_bytes
                if self._on_progress_callback:
                    # We don't know total size here, callback will get bytes received
                    self._on_progress_callback(image_name, received_bytes)

        return received_bytes

    async def _handle_multipart_upload(
        self, request: web.Request, dest_dir: Path, image_name: str
    ) -> int:
        """Handle multipart upload (for Clonezilla directories)."""
        received_bytes = 0
        dest_dir.mkdir(parents=True, exist_ok=True)

        reader = await request.multipart()

        async for part in reader:
            if part.filename:
                # This is a file field
                file_path = dest_dir / part.filename
                file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(file_path, "wb") as f:
                    while True:
                        chunk = await part.read_chunk()
                        if not chunk:
                            break
                        f.write(chunk)
                        received_bytes += len(chunk)

                        # Update progress
                        self._transfer_progress[image_name] = received_bytes
                        if self._on_progress_callback:
                            self._on_progress_callback(image_name, received_bytes)

        return received_bytes

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Handle GET /status - Server status check."""
        return web.json_response(
            {
                "status": "ready",
                "pin_required": True,
                "destination": str(self.destination_repo.path),
            }
        )

    def _verify_token(self, request: web.Request) -> bool:
        """Verify session token from Authorization header."""
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return False

        token = auth_header[7:]  # Remove "Bearer " prefix

        if token not in _active_sessions:
            return False

        # Check session timeout
        session = _active_sessions[token]
        age = time.time() - session["created_at"]

        if age > SESSION_TIMEOUT:
            _active_sessions.pop(token, None)
            return False

        return True

    def _check_rate_limit(self, client_ip: str) -> bool:
        """Check if client has exceeded failed attempt rate limit."""
        now = time.time()

        # Clean old attempts
        if client_ip in _failed_attempts:
            _failed_attempts[client_ip] = [
                ts for ts in _failed_attempts[client_ip] if now - ts < RATE_LIMIT_WINDOW
            ]

            # Check if exceeded limit
            if len(_failed_attempts[client_ip]) >= MAX_FAILED_ATTEMPTS:
                return False

        return True

    def _record_failed_attempt(self, client_ip: str) -> None:
        """Record a failed authentication attempt."""
        now = time.time()

        if client_ip not in _failed_attempts:
            _failed_attempts[client_ip] = []

        _failed_attempts[client_ip].append(now)
