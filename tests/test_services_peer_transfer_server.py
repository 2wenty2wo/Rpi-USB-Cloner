"""Tests for peer transfer HTTP server.

Tests cover:
- Server start/stop lifecycle
- Authentication with PIN
- Transfer initialization
- File uploads
- Rate limiting
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch
import asyncio

import pytest
import aiohttp
from aiohttp import web

from rpi_usb_cloner.services.peer_transfer_server import (
    TransferServer,
    _active_sessions,
    _current_pin,
    _failed_attempts,
)
from rpi_usb_cloner.domain import ImageRepo, ImageType


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global state before each test."""
    global _current_pin, _active_sessions, _failed_attempts
    _current_pin = None
    _active_sessions.clear()
    _failed_attempts.clear()
    yield
    _current_pin = None
    _active_sessions.clear()
    _failed_attempts.clear()


class TestTransferServerInit:
    """Test TransferServer initialization."""

    def test_default_initialization(self, tmp_path):
        """Test initialization with defaults."""
        repo = Mock(spec=ImageRepo, path=tmp_path)

        server = TransferServer(repo)

        assert server.destination_repo == repo
        assert server.port == 8765
        assert server.app is None
        assert server.runner is None

    def test_custom_port_initialization(self, tmp_path):
        """Test initialization with custom port."""
        repo = Mock(spec=ImageRepo, path=tmp_path)

        server = TransferServer(repo, port=9999)

        assert server.port == 9999


class TestServerLifecycle:
    """Test server start/stop."""

    @pytest.mark.asyncio
    async def test_start_generates_pin(self, tmp_path):
        """Test server generates PIN on start."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        assert server.get_current_pin() is not None
        assert len(server.get_current_pin()) == 4

        await server.stop()

    @pytest.mark.asyncio
    async def test_start_with_custom_pin_callback(self, tmp_path):
        """Test using custom PIN callback."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        pin_callback = Mock(return_value="5678")

        await server.start(pin_callback=pin_callback)

        assert server.get_current_pin() == "5678"

        await server.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_state(self, tmp_path):
        """Test stop clears PIN and sessions."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()
        initial_pin = server.get_current_pin()
        assert initial_pin is not None

        await server.stop()

        assert server.get_current_pin() is None


class TestAuthEndpoint:
    """Test authentication endpoint."""

    @pytest.mark.asyncio
    async def test_auth_success(self, aiohttp_client, tmp_path):
        """Test successful authentication."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()
        pin = server.get_current_pin()

        client = await aiohttp_client(server.app)

        resp = await client.post("/auth", json={"pin": pin})

        assert resp.status == 200
        data = await resp.json()
        assert "token" in data

        await server.stop()

    @pytest.mark.asyncio
    async def test_auth_invalid_pin(self, aiohttp_client, tmp_path):
        """Test authentication with invalid PIN."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        client = await aiohttp_client(server.app)

        resp = await client.post("/auth", json={"pin": "0000"})

        assert resp.status == 401
        data = await resp.json()
        assert "error" in data

        await server.stop()

    @pytest.mark.asyncio
    async def test_auth_rate_limiting(self, aiohttp_client, tmp_path):
        """Test rate limiting on failed attempts."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        client = await aiohttp_client(server.app)

        # Make 3 failed attempts
        for _ in range(3):
            resp = await client.post("/auth", json={"pin": "0000"})
            assert resp.status == 401

        # 4th attempt should be rate limited
        resp = await client.post("/auth", json={"pin": "0000"})
        assert resp.status == 429
        data = await resp.json()
        assert "retry_after" in data

        await server.stop()

    @pytest.mark.asyncio
    async def test_auth_clears_failed_on_success(self, aiohttp_client, tmp_path):
        """Test successful auth clears failed attempts."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()
        pin = server.get_current_pin()

        client = await aiohttp_client(server.app)

        # 2 failed attempts
        await client.post("/auth", json={"pin": "0000"})
        await client.post("/auth", json={"pin": "0000"})

        # Success should clear failed attempts
        resp = await client.post("/auth", json={"pin": pin})
        assert resp.status == 200

        # Should not be rate limited now
        resp = await client.post("/auth", json={"pin": "0000"})
        assert resp.status == 401  # Still invalid, but not rate limited

        await server.stop()


class TestTransferInitEndpoint:
    """Test transfer initialization endpoint."""

    @pytest.mark.asyncio
    async def test_transfer_init_success(self, aiohttp_client, tmp_path, mocker):
        """Test successful transfer initialization."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        # First authenticate
        client = await aiohttp_client(server.app)
        auth_resp = await client.post("/auth", json={"pin": server.get_current_pin()})
        token = (await auth_resp.json())["token"]

        # Mock repo usage check
        mocker.patch(
            "rpi_usb_cloner.services.peer_transfer_server.image_repo.get_repo_usage",
            return_value={"free_bytes": 10000000, "used_bytes": 0},
        )

        # Initialize transfer
        resp = await client.post(
            "/transfer",
            json={"images": [{"name": "test.iso", "type": "iso", "size_bytes": 1000000}]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status == 200
        data = await resp.json()
        assert data["accepted"] is True
        assert "transfer_id" in data

        await server.stop()

    @pytest.mark.asyncio
    async def test_transfer_init_unauthorized(self, aiohttp_client, tmp_path):
        """Test transfer init without authentication."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        client = await aiohttp_client(server.app)

        resp = await client.post(
            "/transfer",
            json={"images": [{"name": "test.iso", "type": "iso", "size_bytes": 1000}]},
        )

        assert resp.status == 401

        await server.stop()

    @pytest.mark.asyncio
    async def test_transfer_init_insufficient_space(self, aiohttp_client, tmp_path, mocker):
        """Test transfer init with insufficient space."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        client = await aiohttp_client(server.app)
        auth_resp = await client.post("/auth", json={"pin": server.get_current_pin()})
        token = (await auth_resp.json())["token"]

        # Mock repo usage - not enough space
        mocker.patch(
            "rpi_usb_cloner.services.peer_transfer_server.image_repo.get_repo_usage",
            return_value={"free_bytes": 1000, "used_bytes": 9000},
        )

        resp = await client.post(
            "/transfer",
            json={"images": [{"name": "test.iso", "type": "iso", "size_bytes": 10000}]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status == 507
        data = await resp.json()
        assert "error" in data
        assert data["required"] == 10000

        await server.stop()

    @pytest.mark.asyncio
    async def test_transfer_init_no_images(self, aiohttp_client, tmp_path):
        """Test transfer init with no images."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        client = await aiohttp_client(server.app)
        auth_resp = await client.post("/auth", json={"pin": server.get_current_pin()})
        token = (await auth_resp.json())["token"]

        resp = await client.post(
            "/transfer",
            json={"images": []},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status == 400

        await server.stop()


class TestUploadEndpoint:
    """Test file upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_iso_file(self, aiohttp_client, tmp_path):
        """Test uploading ISO file."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        client = await aiohttp_client(server.app)
        auth_resp = await client.post("/auth", json={"pin": server.get_current_pin()})
        token = (await auth_resp.json())["token"]

        # Upload file
        test_data = b"ISO file content"
        resp = await client.post(
            "/upload/test.iso",
            data=test_data,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Image-Type": "iso",
                "Content-Type": "application/octet-stream",
            },
        )

        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "complete"
        assert data["received_bytes"] == len(test_data)

        # Verify file was saved
        assert (tmp_path / "test.iso").exists()
        assert (tmp_path / "test.iso").read_bytes() == test_data

        await server.stop()

    @pytest.mark.asyncio
    async def test_upload_to_clonezilla_subdir(self, aiohttp_client, tmp_path):
        """Test uploading to clonezilla subdirectory."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        client = await aiohttp_client(server.app)
        auth_resp = await client.post("/auth", json={"pin": server.get_current_pin()})
        token = (await auth_resp.json())["token"]

        test_data = b"Clonezilla image data"
        resp = await client.post(
            "/upload/my_image",
            data=test_data,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Image-Type": "clonezilla_dir",
                "Content-Type": "application/octet-stream",
            },
        )

        assert resp.status == 200

        # Verify file was saved in clonezilla subdirectory
        assert (tmp_path / "clonezilla" / "my_image").exists()

        await server.stop()

    @pytest.mark.asyncio
    async def test_upload_unauthorized(self, aiohttp_client, tmp_path):
        """Test upload without authentication."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        client = await aiohttp_client(server.app)

        resp = await client.post(
            "/upload/test.iso",
            data=b"test",
            headers={"X-Image-Type": "iso"},
        )

        assert resp.status == 401

        await server.stop()

    @pytest.mark.asyncio
    async def test_upload_multipart_clonezilla(self, aiohttp_client, tmp_path):
        """Test multipart upload for Clonezilla directory."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        client = await aiohttp_client(server.app)
        auth_resp = await client.post("/auth", json={"pin": server.get_current_pin()})
        token = (await auth_resp.json())["token"]

        # Create multipart data
        data = aiohttp.FormData()
        data.add_field("file", b"disk data", filename="disk")
        data.add_field("file", b"parts data", filename="parts")
        data.add_field("file", b"partition table", filename="sda-pt.sf")

        resp = await client.post(
            "/upload/clonezilla_image",
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Image-Type": "clonezilla_dir",
            },
        )

        assert resp.status == 200

        # Verify files were saved
        clonezilla_dir = tmp_path / "clonezilla" / "clonezilla_image"
        assert (clonezilla_dir / "disk").exists()
        assert (clonezilla_dir / "parts").exists()
        assert (clonezilla_dir / "sda-pt.sf").exists()

        await server.stop()


class TestStatusEndpoint:
    """Test status endpoint."""

    @pytest.mark.asyncio
    async def test_status_endpoint(self, aiohttp_client, tmp_path):
        """Test status endpoint returns server info."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        client = await aiohttp_client(server.app)

        resp = await client.get("/status")

        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ready"
        assert data["pin_required"] is True
        assert "destination" in data

        await server.stop()


class TestTokenVerification:
    """Test token verification logic."""

    @pytest.mark.asyncio
    async def test_token_timeout(self, aiohttp_client, tmp_path, mocker):
        """Test token expires after timeout."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        await server.start()

        client = await aiohttp_client(server.app)
        auth_resp = await client.post("/auth", json={"pin": server.get_current_pin()})
        token = (await auth_resp.json())["token"]

        # Verify token works
        mocker.patch(
            "rpi_usb_cloner.services.peer_transfer_server.image_repo.get_repo_usage",
            return_value={"free_bytes": 10000000, "used_bytes": 0},
        )

        resp = await client.post(
            "/transfer",
            json={"images": [{"name": "test.iso", "type": "iso", "size_bytes": 1000}]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status == 200

        # Simulate timeout by manipulating session age
        from rpi_usb_cloner.services.peer_transfer_server import _active_sessions
        import time
        _active_sessions[token]["created_at"] = time.time() - 700  # 700 seconds ago (timeout is 600)

        # Token should now be invalid
        resp = await client.post(
            "/transfer",
            json={"images": [{"name": "test.iso", "type": "iso", "size_bytes": 1000}]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status == 401

        await server.stop()


class TestProgressTracking:
    """Test transfer progress tracking."""

    @pytest.mark.asyncio
    async def test_progress_callback(self, aiohttp_client, tmp_path):
        """Test progress callback is called during upload."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        progress_calls = []

        def on_progress(name, progress):
            progress_calls.append((name, progress))

        await server.start(on_progress=on_progress)

        client = await aiohttp_client(server.app)
        auth_resp = await client.post("/auth", json={"pin": server.get_current_pin()})
        token = (await auth_resp.json())["token"]

        # Upload a larger file
        test_data = b"X" * (1024 * 1024)  # 1MB
        resp = await client.post(
            "/upload/test.iso",
            data=test_data,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Image-Type": "iso",
                "Content-Type": "application/octet-stream",
            },
        )

        assert resp.status == 200

        # Check progress was tracked
        progress = server.get_transfer_progress()
        assert "test.iso" in progress

        await server.stop()


class TestPinGeneration:
    """Test PIN generation."""

    def test_pin_format(self, tmp_path):
        """Test PIN is 4 digits."""
        repo = Mock(spec=ImageRepo, path=tmp_path)
        server = TransferServer(repo)

        for _ in range(10):
            pin = server._generate_pin()
            assert len(pin) == 4
            assert pin.isdigit()
            assert 0 <= int(pin) <= 9999
