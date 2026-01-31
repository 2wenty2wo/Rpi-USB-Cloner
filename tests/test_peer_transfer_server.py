"""Tests for HTTP peer transfer server (services/peer_transfer_server.py)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from aiohttp import web

from rpi_usb_cloner.domain import ImageRepo, ImageType
from rpi_usb_cloner.services.peer_transfer_server import (
    TransferServer,
    _active_sessions,
    _current_pin,
    _failed_attempts,
    SESSION_TIMEOUT,
    MAX_FAILED_ATTEMPTS,
)


@pytest.fixture
def destination_repo(tmp_path):
    """Create a temporary destination repository."""
    return ImageRepo(path=tmp_path, drive_name="sda1")


@pytest.fixture
def transfer_server(destination_repo):
    """Create a TransferServer instance."""
    return TransferServer(destination_repo, port=8765)


class TestTransferServerInit:
    """Test TransferServer initialization."""

    def test_initialization(self, destination_repo):
        """Test server initialization."""
        server = TransferServer(destination_repo, port=9999)
        
        assert server.destination_repo == destination_repo
        assert server.port == 9999
        assert server.app is None
        assert server.runner is None
        assert server.site is None


class TestGeneratePin:
    """Test PIN generation."""

    def test_generate_pin_format(self, transfer_server):
        """Test PIN is 4 digits."""
        pin = transfer_server._generate_pin()
        
        assert len(pin) == 4
        assert pin.isdigit()

    def test_generate_pin_range(self, transfer_server):
        """Test PIN is in valid range."""
        # Test multiple times to cover randomness
        for _ in range(10):
            pin = transfer_server._generate_pin()
            assert 0 <= int(pin) <= 9999


class TestStartStop:
    """Test server start and stop."""

    @pytest.mark.asyncio
    async def test_start_generates_pin(self, transfer_server):
        """Test starting server generates PIN."""
        mock_site = AsyncMock()
        mock_runner = AsyncMock()
        mock_runner.setup = AsyncMock()
        
        captured_pin = None
        
        def capture_pin(*args, **kwargs):
            nonlocal captured_pin
            captured_pin = transfer_server.get_current_pin()
            return mock_site
        
        mock_site.start = AsyncMock(side_effect=capture_pin)
        mock_site.stop = AsyncMock()
        
        with patch("rpi_usb_cloner.services.peer_transfer_server.web.TCPSite", return_value=mock_site):
            with patch("rpi_usb_cloner.services.peer_transfer_server.web.AppRunner", return_value=mock_runner):
                await transfer_server.start()
                
                assert captured_pin is not None
                assert len(captured_pin) == 4
                
                await transfer_server.stop()

    @pytest.mark.asyncio
    async def test_start_with_custom_pin_callback(self, transfer_server):
        """Test starting with custom PIN callback."""
        pin_callback = Mock(return_value="5678")
        
        mock_site = AsyncMock()
        mock_runner = AsyncMock()
        mock_runner.setup = AsyncMock()
        
        captured_pin = None
        
        def capture_pin(*args, **kwargs):
            nonlocal captured_pin
            captured_pin = transfer_server.get_current_pin()
            return mock_site
        
        mock_site.start = AsyncMock(side_effect=capture_pin)
        mock_site.stop = AsyncMock()
        
        with patch("rpi_usb_cloner.services.peer_transfer_server.web.TCPSite", return_value=mock_site):
            with patch("rpi_usb_cloner.services.peer_transfer_server.web.AppRunner", return_value=mock_runner):
                await transfer_server.start(pin_callback=pin_callback)
                
                assert captured_pin == "5678"
                
                await transfer_server.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_sessions(self, transfer_server):
        """Test stopping clears active sessions."""
        global _active_sessions
        
        # Store original state
        original_sessions = dict(_active_sessions)
        _active_sessions["test_token"] = {"created_at": time.time()}
        
        mock_site = AsyncMock()
        mock_runner = AsyncMock()
        mock_runner.setup = AsyncMock()
        mock_runner.cleanup = AsyncMock()
        
        with patch("rpi_usb_cloner.services.peer_transfer_server.web.TCPSite", return_value=mock_site):
            with patch("rpi_usb_cloner.services.peer_transfer_server.web.AppRunner", return_value=mock_runner):
                await transfer_server.start()
                await transfer_server.stop()
        
        # After stop, sessions should be cleared
        assert len(_active_sessions) == 0
        
        # Restore original state
        _active_sessions.clear()
        _active_sessions.update(original_sessions)


class TestHandleAuth:
    """Test authentication endpoint."""

    @pytest.mark.asyncio
    async def test_auth_success(self, transfer_server):
        """Test successful authentication."""
        # Set the PIN using the server's method
        import rpi_usb_cloner.services.peer_transfer_server as server_module
        original_pin = server_module._current_pin
        server_module._current_pin = "1234"
        
        try:
            mock_request = AsyncMock()
            mock_request.remote = "192.168.1.50"
            mock_request.json = AsyncMock(return_value={"pin": "1234"})
            
            with patch.object(transfer_server, "_check_rate_limit", return_value=True):
                response = await transfer_server._handle_auth(mock_request)
            
            assert response.status == 200
            # aiohttp Response doesn't have json() method directly, check the text
            response_text = response.text
            assert "token" in response_text
        finally:
            server_module._current_pin = original_pin

    @pytest.mark.asyncio
    async def test_auth_invalid_pin(self, transfer_server):
        """Test authentication with invalid PIN."""
        global _current_pin
        _current_pin = "1234"
        
        mock_request = AsyncMock()
        mock_request.remote = "192.168.1.50"
        mock_request.json = AsyncMock(return_value={"pin": "0000"})
        
        with patch.object(transfer_server, "_check_rate_limit", return_value=True):
            with patch.object(transfer_server, "_record_failed_attempt"):
                response = await transfer_server._handle_auth(mock_request)
        
        assert response.status == 401
        response_text = response.text
        assert "Invalid PIN" in response_text

    @pytest.mark.asyncio
    async def test_auth_rate_limited(self, transfer_server):
        """Test authentication when rate limited."""
        mock_request = AsyncMock()
        mock_request.remote = "192.168.1.50"
        
        with patch.object(transfer_server, "_check_rate_limit", return_value=False):
            response = await transfer_server._handle_auth(mock_request)
        
        assert response.status == 429
        response_text = response.text
        assert "retry_after" in response_text


class TestHandleTransferInit:
    """Test transfer initialization endpoint."""

    @pytest.mark.asyncio
    async def test_transfer_init_success(self, transfer_server):
        """Test successful transfer initialization."""
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "images": [
                {"name": "test.iso", "type": "iso", "size_bytes": 1000}
            ]
        })
        
        with patch.object(transfer_server, "_verify_token", return_value=True):
            with patch("rpi_usb_cloner.services.peer_transfer_server.image_repo.get_repo_usage", return_value={"free_bytes": 10000}):
                response = await transfer_server._handle_transfer_init(mock_request)
        
        assert response.status == 200
        response_text = response.text
        assert "accepted" in response_text
        assert "transfer_id" in response_text

    @pytest.mark.asyncio
    async def test_transfer_init_insufficient_space(self, transfer_server):
        """Test transfer init with insufficient space."""
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "images": [
                {"name": "test.iso", "type": "iso", "size_bytes": 10000}
            ]
        })
        
        with patch.object(transfer_server, "_verify_token", return_value=True):
            with patch("rpi_usb_cloner.services.peer_transfer_server.image_repo.get_repo_usage", return_value={"free_bytes": 1000}):
                response = await transfer_server._handle_transfer_init(mock_request)
        
        assert response.status == 507
        response_text = response.text
        assert "Insufficient space" in response_text

    @pytest.mark.asyncio
    async def test_transfer_init_no_images(self, transfer_server):
        """Test transfer init with no images."""
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={"images": []})
        
        with patch.object(transfer_server, "_verify_token", return_value=True):
            response = await transfer_server._handle_transfer_init(mock_request)
        
        assert response.status == 400
        response_text = response.text
        assert "No images specified" in response_text

    @pytest.mark.asyncio
    async def test_transfer_init_unauthorized(self, transfer_server):
        """Test transfer init without valid token."""
        mock_request = AsyncMock()
        
        with patch.object(transfer_server, "_verify_token", return_value=False):
            response = await transfer_server._handle_transfer_init(mock_request)
        
        assert response.status == 401


class TestVerifyToken:
    """Test token verification."""

    def test_verify_valid_token(self, transfer_server):
        """Test verifying valid token."""
        global _active_sessions
        
        token = "valid_token_123"
        _active_sessions[token] = {
            "created_at": time.time(),
            "pin": "1234",
            "peer_ip": "192.168.1.50",
        }
        
        mock_request = Mock()
        mock_request.headers = {"Authorization": f"Bearer {token}"}
        
        assert transfer_server._verify_token(mock_request) is True

    def test_verify_expired_token(self, transfer_server):
        """Test verifying expired token."""
        global _active_sessions
        
        token = "expired_token"
        _active_sessions[token] = {
            "created_at": time.time() - SESSION_TIMEOUT - 1,  # Expired
            "pin": "1234",
            "peer_ip": "192.168.1.50",
        }
        
        mock_request = Mock()
        mock_request.headers = {"Authorization": f"Bearer {token}"}
        
        assert transfer_server._verify_token(mock_request) is False
        assert token not in _active_sessions  # Should be removed

    def test_verify_invalid_header(self, transfer_server):
        """Test verifying with invalid Authorization header."""
        mock_request = Mock()
        mock_request.headers = {"Authorization": "Basic dXNlcjpwYXNz"}  # Not Bearer
        
        assert transfer_server._verify_token(mock_request) is False

    def test_verify_missing_token(self, transfer_server):
        """Test verifying missing token."""
        mock_request = Mock()
        mock_request.headers = {}
        
        assert transfer_server._verify_token(mock_request) is False


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_check_rate_limit_under_limit(self, transfer_server):
        """Test rate limit check under max attempts."""
        global _failed_attempts
        _failed_attempts.clear()
        
        assert transfer_server._check_rate_limit("192.168.1.50") is True

    def test_check_rate_limit_exceeded(self, transfer_server):
        """Test rate limit check when exceeded."""
        global _failed_attempts
        
        client_ip = "192.168.1.50"
        now = time.time()
        _failed_attempts[client_ip] = [now - 5, now - 10, now - 15]  # 3 failures within window
        
        assert transfer_server._check_rate_limit(client_ip) is False

    def test_check_rate_limit_old_attempts_cleaned(self, transfer_server):
        """Test old failed attempts are cleaned up."""
        global _failed_attempts
        
        client_ip = "192.168.1.50"
        now = time.time()
        # Old attempts outside window
        _failed_attempts[client_ip] = [now - 100, now - 90, now - 80]
        
        assert transfer_server._check_rate_limit(client_ip) is True

    def test_record_failed_attempt(self, transfer_server):
        """Test recording failed attempt."""
        global _failed_attempts
        _failed_attempts.clear()
        
        transfer_server._record_failed_attempt("192.168.1.50")
        
        assert "192.168.1.50" in _failed_attempts
        assert len(_failed_attempts["192.168.1.50"]) == 1


class TestHandleStatus:
    """Test status endpoint."""

    @pytest.mark.asyncio
    async def test_handle_status(self, transfer_server):
        """Test status endpoint."""
        mock_request = Mock()
        
        response = await transfer_server._handle_status(mock_request)
        
        assert response.status == 200
        response_text = response.text
        assert "ready" in response_text
        assert "pin_required" in response_text
