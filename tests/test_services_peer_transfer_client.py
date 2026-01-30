"""Tests for peer transfer HTTP client.

Tests cover:
- Authentication with PIN
- Sending images to peers
- Upload progress tracking
- Error handling
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import asyncio

import pytest
import aiohttp

from rpi_usb_cloner.services.peer_transfer_client import (
    TransferClient,
    AuthenticationError,
    TransferError,
)
from rpi_usb_cloner.services.discovery import PeerDevice
from rpi_usb_cloner.domain import DiskImage, ImageType


class TestTransferClientInit:
    """Test TransferClient initialization."""

    def test_default_initialization(self):
        """Test initialization with default timeout."""
        peer = Mock(
            spec=PeerDevice,
            address="192.168.1.100",
            port=8765,
            hostname="testpi",
        )

        client = TransferClient(peer)

        assert client.peer == peer
        assert client.base_url == "http://192.168.1.100:8765"
        assert client.session_token is None
        assert client.timeout.total == 300  # Default 5 minutes

    def test_custom_timeout_initialization(self):
        """Test initialization with custom timeout."""
        peer = Mock(
            spec=PeerDevice,
            address="192.168.1.100",
            port=8765,
            hostname="testpi",
        )

        client = TransferClient(peer, timeout_seconds=600)

        assert client.timeout.total == 600  # 10 minutes


class TestAuthenticate:
    """Test authentication with PIN."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, aiohttp_client, mocker):
        """Test successful authentication."""
        peer = Mock(
            spec=PeerDevice,
            address="127.0.0.1",
            port=8765,
            hostname="testpi",
        )

        async def handler(request):
            data = await request.json()
            if data.get("pin") == "1234":
                return aiohttp.web.json_response({"token": "abc123"})
            return aiohttp.web.json_response({"error": "Invalid PIN"}, status=401)

        app = aiohttp.web.Application()
        app.router.add_post("/auth", handler)

        session, base_url = await aiohttp_client(app)

        client = TransferClient(peer)
        client.base_url = base_url

        token = await client.authenticate("1234")

        assert token == "abc123"
        assert client.session_token == "abc123"

    @pytest.mark.asyncio
    async def test_authenticate_invalid_pin(self, aiohttp_client):
        """Test authentication with invalid PIN."""
        peer = Mock(
            spec=PeerDevice,
            address="127.0.0.1",
            port=8765,
            hostname="testpi",
        )

        async def handler(request):
            return aiohttp.web.json_response(
                {"error": "Invalid PIN"}, status=401
            )

        app = aiohttp.web.Application()
        app.router.add_post("/auth", handler)

        session, base_url = await aiohttp_client(app)

        client = TransferClient(peer)
        client.base_url = base_url

        with pytest.raises(AuthenticationError, match="Invalid PIN"):
            await client.authenticate("0000")

    @pytest.mark.asyncio
    async def test_authenticate_rate_limited(self, aiohttp_client):
        """Test authentication rate limiting."""
        peer = Mock(
            spec=PeerDevice,
            address="127.0.0.1",
            port=8765,
            hostname="testpi",
        )

        async def handler(request):
            return aiohttp.web.json_response(
                {"error": "Too many attempts", "retry_after": 60},
                status=429,
            )

        app = aiohttp.web.Application()
        app.router.add_post("/auth", handler)

        session, base_url = await aiohttp_client(app)

        client = TransferClient(peer)
        client.base_url = base_url

        with pytest.raises(AuthenticationError, match="Too many failed attempts"):
            await client.authenticate("1234")

    @pytest.mark.asyncio
    async def test_authenticate_network_error(self, mocker):
        """Test handling network errors during auth."""
        peer = Mock(
            spec=PeerDevice,
            address="192.168.1.100",
            port=8765,
            hostname="testpi",
        )

        client = TransferClient(peer)

        # Mock ClientSession to raise error
        mock_session = AsyncMock()
        mock_session.__aenter__.side_effect = aiohttp.ClientError("Connection refused")

        mocker.patch(
            "rpi_usb_cloner.services.peer_transfer_client.aiohttp.ClientSession",
            return_value=mock_session,
        )

        with pytest.raises(AuthenticationError, match="Network error"):
            await client.authenticate("1234")


class TestSendImages:
    """Test sending images to peer."""

    @pytest.mark.asyncio
    async def test_send_images_not_authenticated(self):
        """Test error when not authenticated."""
        peer = Mock(
            spec=PeerDevice,
            address="192.168.1.100",
            port=8765,
            hostname="testpi",
        )

        client = TransferClient(peer)
        mock_image = Mock(spec=DiskImage)

        with pytest.raises(AuthenticationError, match="Not authenticated"):
            await client.send_images([mock_image])

    @pytest.mark.asyncio
    async def test_send_images_success(self, aiohttp_client, mocker, tmp_path):
        """Test successful image transfer."""
        peer = Mock(
            spec=PeerDevice,
            address="127.0.0.1",
            port=8765,
            hostname="testpi",
        )

        transfer_initialized = {"initialized": False}

        async def auth_handler(request):
            return aiohttp.web.json_response({"token": "abc123"})

        async def transfer_handler(request):
            transfer_initialized["initialized"] = True
            return aiohttp.web.json_response({"transfer_id": "xyz789"})

        async def upload_handler(request):
            return aiohttp.web.json_response({"received_bytes": 100, "status": "complete"})

        app = aiohttp.web.Application()
        app.router.add_post("/auth", auth_handler)
        app.router.add_post("/transfer", transfer_handler)
        app.router.add_post("/upload/{image_name}", upload_handler)

        session, base_url = await aiohttp_client(app)

        client = TransferClient(peer)
        client.base_url = base_url
        client.session_token = "abc123"  # Pre-authenticate

        # Create test image file
        image_file = tmp_path / "test.iso"
        image_file.write_bytes(b"ISO content")

        mock_image = Mock(
            spec=DiskImage,
            name="test.iso",
            image_type=ImageType.ISO,
            path=image_file,
        )

        mocker.patch(
            "rpi_usb_cloner.services.peer_transfer_client.image_repo.get_image_size_bytes",
            return_value=100,
        )

        success, failure = await client.send_images([mock_image])

        assert success == 1
        assert failure == 0

    @pytest.mark.asyncio
    async def test_send_images_insufficient_space(self, aiohttp_client, mocker):
        """Test handling insufficient space error."""
        peer = Mock(
            spec=PeerDevice,
            address="127.0.0.1",
            port=8765,
            hostname="testpi",
        )

        async def transfer_handler(request):
            return aiohttp.web.json_response(
                {
                    "error": "Insufficient space",
                    "required": 1000000,
                    "available": 500000,
                },
                status=507,
            )

        app = aiohttp.web.Application()
        app.router.add_post("/transfer", transfer_handler)

        session, base_url = await aiohttp_client(app)

        client = TransferClient(peer)
        client.base_url = base_url
        client.session_token = "abc123"

        mock_image = Mock(
            spec=DiskImage,
            name="test.iso",
            image_type=ImageType.ISO,
            path=Mock(spec=Path),
        )

        mocker.patch(
            "rpi_usb_cloner.services.peer_transfer_client.image_repo.get_image_size_bytes",
            return_value=1000000,
        )

        with pytest.raises(TransferError, match="Insufficient space"):
            await client.send_images([mock_image])

    @pytest.mark.asyncio
    async def test_send_images_partial_failure(self, aiohttp_client, mocker, tmp_path):
        """Test partial failure during transfer."""
        peer = Mock(
            spec=PeerDevice,
            address="127.0.0.1",
            port=8765,
            hostname="testpi",
        )

        call_count = {"count": 0}

        async def transfer_handler(request):
            return aiohttp.web.json_response({"transfer_id": "xyz789"})

        async def upload_handler(request):
            call_count["count"] += 1
            if call_count["count"] == 1:
                return aiohttp.web.json_response({"error": "Failed"}, status=500)
            return aiohttp.web.json_response({"status": "complete"})

        app = aiohttp.web.Application()
        app.router.add_post("/transfer", transfer_handler)
        app.router.add_post("/upload/{image_name}", upload_handler)

        session, base_url = await aiohttp_client(app)

        client = TransferClient(peer)
        client.base_url = base_url
        client.session_token = "abc123"

        # Create test files
        image1_file = tmp_path / "test1.iso"
        image1_file.write_bytes(b"Content 1")
        image2_file = tmp_path / "test2.iso"
        image2_file.write_bytes(b"Content 2")

        mock_images = [
            Mock(spec=DiskImage, name="test1.iso", image_type=ImageType.ISO, path=image1_file),
            Mock(spec=DiskImage, name="test2.iso", image_type=ImageType.ISO, path=image2_file),
        ]

        mocker.patch(
            "rpi_usb_cloner.services.peer_transfer_client.image_repo.get_image_size_bytes",
            return_value=100,
        )

        success, failure = await client.send_images(mock_images)

        assert success == 1
        assert failure == 1


class TestCheckStatus:
    """Test server status check."""

    @pytest.mark.asyncio
    async def test_check_status_success(self, aiohttp_client):
        """Test successful status check."""
        peer = Mock(
            spec=PeerDevice,
            address="127.0.0.1",
            port=8765,
            hostname="testpi",
        )

        async def status_handler(request):
            return aiohttp.web.json_response(
                {"status": "ready", "pin_required": True}
            )

        app = aiohttp.web.Application()
        app.router.add_get("/status", status_handler)

        session, base_url = await aiohttp_client(app)

        client = TransferClient(peer)
        client.base_url = base_url

        status = await client.check_status()

        assert status["status"] == "ready"
        assert status["pin_required"] is True

    @pytest.mark.asyncio
    async def test_check_status_error(self, aiohttp_client):
        """Test status check with error response."""
        peer = Mock(
            spec=PeerDevice,
            address="127.0.0.1",
            port=8765,
            hostname="testpi",
        )

        async def status_handler(request):
            return aiohttp.web.json_response({"error": "Busy"}, status=503)

        app = aiohttp.web.Application()
        app.router.add_get("/status", status_handler)

        session, base_url = await aiohttp_client(app)

        client = TransferClient(peer)
        client.base_url = base_url

        status = await client.check_status()

        assert status["status"] == "error"
        assert status["code"] == 503

    @pytest.mark.asyncio
    async def test_check_status_unreachable(self, mocker):
        """Test status check when server is unreachable."""
        peer = Mock(
            spec=PeerDevice,
            address="192.168.1.100",
            port=8765,
            hostname="testpi",
        )

        client = TransferClient(peer)

        mock_session = AsyncMock()
        mock_session.__aenter__.side_effect = aiohttp.ClientError("Connection refused")

        mocker.patch(
            "rpi_usb_cloner.services.peer_transfer_client.aiohttp.ClientSession",
            return_value=mock_session,
        )

        status = await client.check_status()

        assert status["status"] == "unreachable"


class TestUploadFile:
    """Test file upload functionality."""

    @pytest.mark.asyncio
    async def test_upload_file_with_progress(self, aiohttp_client, tmp_path, mocker):
        """Test file upload with progress callback."""
        peer = Mock(
            spec=PeerDevice,
            address="127.0.0.1",
            port=8765,
            hostname="testpi",
        )

        received_data = []

        async def upload_handler(request):
            data = await request.read()
            received_data.append(data)
            return aiohttp.web.json_response({"status": "complete"})

        app = aiohttp.web.Application()
        app.router.add_post("/upload/{image_name}", upload_handler)

        session, base_url = await aiohttp_client(app)

        client = TransferClient(peer)
        client.base_url = base_url

        # Create test file
        image_file = tmp_path / "test.iso"
        image_file.write_bytes(b"X" * (1024 * 1024))  # 1MB file

        mock_image = Mock(
            spec=DiskImage,
            name="test.iso",
            image_type=ImageType.ISO,
            path=image_file,
        )

        progress_calls = []

        def progress_cb(name, progress):
            progress_calls.append(progress)

        mock_session = Mock()

        await client._upload_single_image(
            session, mock_image, {"Authorization": "Bearer token"}, progress_cb
        )

        # Progress should be called at start
        assert 0.0 in progress_calls


class TestUploadDirectory:
    """Test directory (Clonezilla) upload."""

    @pytest.mark.asyncio
    async def test_upload_clonezilla_directory(self, aiohttp_client, tmp_path, mocker):
        """Test uploading Clonezilla directory."""
        peer = Mock(
            spec=PeerDevice,
            address="127.0.0.1",
            port=8765,
            hostname="testpi",
        )

        received_files = []

        async def upload_handler(request):
            reader = await request.multipart()
            async for part in reader:
                if part.filename:
                    data = await part.read()
                    received_files.append((part.filename, data))
            return aiohttp.web.json_response({"status": "complete"})

        app = aiohttp.web.Application()
        app.router.add_post("/upload/{image_name}", upload_handler)

        session, base_url = await aiohttp_client(app)

        client = TransferClient(peer)
        client.base_url = base_url

        # Create test directory structure
        image_dir = tmp_path / "clonezilla_image"
        image_dir.mkdir()
        (image_dir / "disk").write_text("sda")
        (image_dir / "parts").write_text("sda1")
        subdir = image_dir / "subdir"
        subdir.mkdir()
        (subdir / "data.txt").write_text("data")

        mock_image = Mock(
            spec=DiskImage,
            name="clonezilla_image",
            image_type=ImageType.CLONEZILLA_DIR,
            path=image_dir,
        )

        await client._upload_single_image(
            session, mock_image, {"Authorization": "Bearer token"}, None
        )

        # Check that files were received
        filenames = [f[0] for f in received_files]
        assert "disk" in filenames
        assert "parts" in filenames
        assert "subdir/data.txt" in filenames

    @pytest.mark.asyncio
    async def test_upload_empty_directory(self, aiohttp_client, tmp_path):
        """Test error on empty directory upload."""
        peer = Mock(
            spec=PeerDevice,
            address="127.0.0.1",
            port=8765,
            hostname="testpi",
        )

        app = aiohttp.web.Application()
        session, base_url = await aiohttp_client(app)

        client = TransferClient(peer)
        client.base_url = base_url

        # Create empty directory
        image_dir = tmp_path / "empty_image"
        image_dir.mkdir()

        mock_image = Mock(
            spec=DiskImage,
            name="empty_image",
            image_type=ImageType.CLONEZILLA_DIR,
            path=image_dir,
        )

        mock_session = Mock()

        with pytest.raises(TransferError, match="is empty"):
            await client._upload_single_image(
                mock_session, mock_image, {}, None
            )
