"""HTTP client for sending image transfers to peer devices.

Provides authentication and file upload capabilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import aiohttp

from rpi_usb_cloner.domain import DiskImage, ImageType
from rpi_usb_cloner.logging import get_logger
from rpi_usb_cloner.services.discovery import PeerDevice
from rpi_usb_cloner.storage import image_repo

log = get_logger(source=__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class TransferError(Exception):
    """Raised when transfer fails."""

    pass


class TransferClient:
    """HTTP client for sending images to peer devices."""

    def __init__(self, peer: PeerDevice, timeout_seconds: int = 300):
        """Initialize transfer client.

        Args:
            peer: Peer device to connect to
            timeout_seconds: HTTP request timeout
        """
        self.peer = peer
        self.base_url = f"http://{peer.address}:{peer.port}"
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.session_token: str | None = None

    async def authenticate(self, pin: str) -> str:
        """Authenticate with 4-digit PIN.

        Args:
            pin: 4-digit PIN from destination device

        Returns:
            Session token for subsequent requests

        Raises:
            AuthenticationError: Invalid PIN or rate limited
        """
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                async with session.post(f"{self.base_url}/auth", json={"pin": pin}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.session_token = data["token"]
                        log.info(f"Authenticated with {self.peer.hostname}")
                        return self.session_token

                    elif resp.status == 401:
                        raise AuthenticationError("Invalid PIN")

                    elif resp.status == 429:
                        data = await resp.json()
                        retry_after = data.get("retry_after", 30)
                        raise AuthenticationError(f"Too many failed attempts. Retry after {retry_after}s")

                    else:
                        raise AuthenticationError(f"Authentication failed with status {resp.status}")

            except aiohttp.ClientError as e:
                log.error(f"Network error during authentication: {e}")
                raise AuthenticationError(f"Network error: {e}")

    async def send_images(
        self,
        images: list[DiskImage],
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> tuple[int, int]:
        """Send images to peer device.

        Args:
            images: List of DiskImage objects to send
            progress_callback: Optional callback(image_name, progress_ratio)

        Returns:
            (success_count, failure_count)

        Raises:
            AuthenticationError: Not authenticated
            TransferError: Transfer initialization failed
        """
        if not self.session_token:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")

        # Build images metadata for transfer init
        images_meta = []
        for img in images:
            size_bytes = image_repo.get_image_size_bytes(img) or 0
            images_meta.append({"name": img.name, "type": img.image_type.name.lower(), "size_bytes": size_bytes})

        # Initialize transfer
        headers = {"Authorization": f"Bearer {self.session_token}"}

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                # POST /transfer to initialize
                async with session.post(
                    f"{self.base_url}/transfer", json={"images": images_meta}, headers=headers
                ) as resp:
                    if resp.status == 507:
                        data = await resp.json()
                        raise TransferError(
                            f"Insufficient space on destination: "
                            f"need {data.get('required', 0)}, "
                            f"have {data.get('available', 0)} bytes"
                        )

                    elif resp.status != 200:
                        error_data = await resp.json()
                        raise TransferError(f"Transfer init failed: {error_data.get('error', 'Unknown error')}")

                    data = await resp.json()
                    transfer_id = data["transfer_id"]
                    log.info(f"Transfer initialized: {transfer_id}")

            except aiohttp.ClientError as e:
                log.error(f"Network error during transfer init: {e}")
                raise TransferError(f"Network error: {e}")

            # Upload each image
            success_count = 0
            failure_count = 0

            for img in images:
                try:
                    await self._upload_single_image(session, img, headers, progress_callback)
                    success_count += 1
                    log.info(f"Successfully sent image: {img.name}")

                except Exception as e:
                    failure_count += 1
                    log.error(f"Failed to send image {img.name}: {e}")

            return success_count, failure_count

    async def _upload_single_image(
        self,
        session: aiohttp.ClientSession,
        image: DiskImage,
        headers: dict,
        progress_callback: Callable[[str, float], None] | None,
    ) -> None:
        """Upload a single image.

        Args:
            session: aiohttp session
            image: DiskImage to upload
            headers: HTTP headers (including auth)
            progress_callback: Optional progress callback
        """
        if progress_callback:
            progress_callback(image.name, 0.0)

        # Add image type header
        upload_headers = headers.copy()
        upload_headers["X-Image-Type"] = image.image_type.name.lower()

        url = f"{self.base_url}/upload/{image.name}"

        # Choose upload method based on image type
        if image.image_type == ImageType.CLONEZILLA_DIR:
            await self._upload_directory(session, url, image, upload_headers, progress_callback)
        else:
            await self._upload_file(session, url, image, upload_headers, progress_callback)

        if progress_callback:
            progress_callback(image.name, 1.0)

    async def _upload_file(
        self,
        session: aiohttp.ClientSession,
        url: str,
        image: DiskImage,
        headers: dict,
        progress_callback: Callable[[str, float], None] | None,
    ) -> None:
        """Upload a single file (ISO or .BIN).

        Args:
            session: aiohttp session
            url: Upload endpoint URL
            image: DiskImage
            headers: HTTP headers
            progress_callback: Optional progress callback
        """
        file_size = image.path.stat().st_size

        async def file_sender():
            """Generator for chunked file upload."""
            bytes_sent = 0
            chunk_size = 1024 * 1024  # 1MB chunks

            with open(image.path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break

                    yield chunk
                    bytes_sent += len(chunk)

                    if progress_callback and file_size > 0:
                        progress = bytes_sent / file_size
                        progress_callback(image.name, progress)

        headers["Content-Type"] = "application/octet-stream"

        async with session.post(url, data=file_sender(), headers=headers) as resp:
            if resp.status != 200:
                error_data = await resp.json()
                raise TransferError(f"Upload failed: {error_data.get('error', 'Unknown error')}")

    async def _upload_directory(
        self,
        session: aiohttp.ClientSession,
        url: str,
        image: DiskImage,
        headers: dict,
        progress_callback: Callable[[str, float], None] | None,
    ) -> None:
        """Upload a Clonezilla directory using multipart/form-data.

        Args:
            session: aiohttp session
            url: Upload endpoint URL
            image: DiskImage (directory)
            headers: HTTP headers
            progress_callback: Optional progress callback
        """
        # Collect all files in directory
        all_files = []
        total_size = 0

        for file_path in image.path.rglob("*"):
            if file_path.is_file():
                size = file_path.stat().st_size
                all_files.append((file_path, size))
                total_size += size

        if total_size == 0:
            raise TransferError(f"Directory {image.name} is empty")

        # Create multipart form data
        bytes_sent = 0

        with aiohttp.MultipartWriter("form-data") as mpwriter:
            for file_path, file_size in all_files:
                # Calculate relative path for file hierarchy
                rel_path = file_path.relative_to(image.path)

                # Read file content
                with open(file_path, "rb") as f:
                    content = f.read()

                # Add to multipart
                part = mpwriter.append(content)
                part.set_content_disposition("form-data", name="file", filename=str(rel_path))

                bytes_sent += file_size

                if progress_callback and total_size > 0:
                    progress = bytes_sent / total_size
                    progress_callback(image.name, progress)

        # Send multipart request
        async with session.post(url, data=mpwriter, headers=headers) as resp:
            if resp.status != 200:
                error_data = await resp.json()
                raise TransferError(f"Upload failed: {error_data.get('error', 'Unknown error')}")

    async def check_status(self) -> dict:
        """Check server status.

        Returns:
            Server status dictionary
        """
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                async with session.get(f"{self.base_url}/status") as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"status": "error", "code": resp.status}

            except aiohttp.ClientError as e:
                log.error(f"Status check error: {e}")
                return {"status": "unreachable", "error": str(e)}
