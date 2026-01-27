"""Tests for web server module."""

import asyncio
import contextlib
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from aiohttp import ClientSession, WSMsgType, web

from rpi_usb_cloner.app.context import LogEntry
from rpi_usb_cloner.web import server
from rpi_usb_cloner.web.system_health import SystemHealth


# ==============================================================================
# Test Fixtures
# ==============================================================================


@dataclass
class WebClient:
    session: ClientSession
    base_url: str
    app: web.Application


def _ws_url(client: WebClient, path: str) -> str:
    return f"{client.base_url.replace('http', 'ws', 1)}{path}"


@pytest_asyncio.fixture
async def web_client(aiohttp_client) -> WebClient:
    app = web.Application()
    app[server.DISPLAY_NOTIFIER_KEY] = server.DisplayUpdateNotifier(
        asyncio.get_running_loop()
    )
    app[server.DISPLAY_STOP_EVENT_KEY] = threading.Event()
    app[server.APP_CONTEXT_KEY] = None
    app.router.add_get("/", server.handle_root)
    app.router.add_get("/health", server.handle_health)
    app.router.add_get("/screen.png", server.handle_screen_png)
    app.router.add_get("/ws/screen", server.handle_screen_ws)
    app.router.add_get("/ws/control", server.handle_control_ws)
    app.router.add_get("/ws/logs", server.handle_logs_ws)
    app.router.add_get("/ws/health", server.handle_health_ws)
    app.router.add_get("/ws/devices", server.handle_devices_ws)
    app.router.add_get("/ws/images", server.handle_images_ws)

    static_dir = Path(server.__file__).resolve().parent / "static"
    app.router.add_static("/static/", str(static_dir))
    session, base_url = await aiohttp_client(app)
    return WebClient(session=session, base_url=base_url, app=app)


# ==============================================================================
# Helper Logic Tests
# ==============================================================================


class TestLogDiffing:
    """Test log buffer diffing logic."""

    def test_diff_empty(self):
        """Test diffing against empty previous buffer."""
        previous = []
        current = ["Line 1", "Line 2"]
        new_entries, reset = server._diff_log_buffer(previous, current)

        assert reset is True
        assert new_entries == current

    def test_diff_identical(self):
        """Test diffing identical buffers returns nothing."""
        current = ["Line 1"]
        previous = ["Line 1"]
        new_entries, reset = server._diff_log_buffer(previous, current)

        assert reset is False
        assert new_entries == []

    def test_diff_append(self):
        """Test detecting appended lines."""
        previous = ["Line 1"]
        current = ["Line 1", "Line 2"]
        new_entries, reset = server._diff_log_buffer(previous, current)

        assert reset is False
        assert new_entries == ["Line 2"]

    def test_diff_reset(self):
        """Test detecting full buffer reset (circular buffer wrap or clear)."""
        previous = ["Line 1", "Line 2"]
        current = ["Line 3", "Line 4"]
        new_entries, reset = server._diff_log_buffer(previous, current)

        # When no overlap found, it treats as reset
        assert reset is True
        assert new_entries == current

    def test_diff_partial_overlap(self):
        """Test diff with partial overlap at end of previous."""
        previous = ["A", "B", "C"]
        current = ["B", "C", "D"]
        # Overlap is B, C

        new_entries, reset = server._diff_log_buffer(previous, current)
        assert reset is False
        assert new_entries == ["D"]


class TestLogSerialization:
    """Test log entry serialization."""

    def test_serialize_strings(self):
        """Test serializing simple strings."""
        entries = ["Log 1", "Log 2"]
        result = server._serialize_log_entries(entries)
        assert result == ["Log 1", "Log 2"]

    def test_serialize_log_entry_objects(self):
        """Test serializing LogEntry dataclass objects."""
        now = datetime.now()
        entry = LogEntry(
            message="Test",
            level="INFO",
            tags={"tag1"},
            timestamp=now,
            source="TEST",
            details={"key": "val"},
        )

        result = server._serialize_log_entries([entry])
        serialized = result[0]

        assert serialized["message"] == "Test"
        assert serialized["level"] == "INFO"
        assert serialized["timestamp"] == now.isoformat()
        assert "tag1" in serialized["tags"]
        assert serialized["details"] == {"key": "val"}


# ==============================================================================
# HTTP Request Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_index_route_loads(web_client, mocker):
    """Test root endpoint returns HTML template."""
    mocker.patch(
        "rpi_usb_cloner.web.server._load_template", return_value="<html></html>"
    )
    async with web_client.session.get(f"{web_client.base_url}/") as response:
        assert response.status == 200
        assert response.content_type == "text/html"
        assert "<html></html>" in await response.text()


@pytest.mark.asyncio
async def test_static_asset_route(web_client):
    """Test static asset routing returns expected file."""
    async with web_client.session.get(
        f"{web_client.base_url}/static/tabler/tabler.min.css"
    ) as response:
        assert response.status == 200
        assert response.content_type == "text/css"
        assert await response.text()


@pytest.mark.asyncio
async def test_health_endpoint_returns_stats(web_client, mocker):
    """Test health endpoint returns expected system stats shape."""
    mocker.patch(
        "rpi_usb_cloner.web.server.get_system_health",
        return_value=SystemHealth(
            cpu_percent=50.2,
            memory_percent=41.7,
            memory_used_mb=512,
            memory_total_mb=1024,
            disk_percent=60.4,
            disk_used_gb=12.3,
            disk_total_gb=64.0,
            temperature_celsius=55.1,
        ),
    )

    async with web_client.session.get(f"{web_client.base_url}/health") as response:
        assert response.status == 200
        payload = await response.json()

    assert payload["cpu"] == {"percent": 50.2, "status": "success"}
    assert payload["memory"] == {
        "percent": 41.7,
        "used_mb": 512,
        "total_mb": 1024,
        "status": "success",
    }
    assert payload["disk"] == {
        "percent": 60.4,
        "used_gb": 12.3,
        "total_gb": 64.0,
        "status": "success",
    }
    assert payload["temperature"] == {"celsius": 55.1, "status": "success"}


# ==============================================================================
# WebSocket Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_screen_ws_initial_frame_delivery(web_client, mocker):
    """Test screen WebSocket sends initial frame on connection."""
    mocker.patch(
        "rpi_usb_cloner.ui.display.get_display_png_bytes", return_value=b"frame"
    )
    mocker.patch("rpi_usb_cloner.ui.display.clear_dirty_flag")

    ws = await asyncio.wait_for(
        web_client.session.ws_connect(_ws_url(web_client, "/ws/screen")), timeout=1
    )
    message = await asyncio.wait_for(ws.receive(), timeout=1)

    assert message.type == WSMsgType.BINARY
    assert message.data == b"frame"
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(ws.close(), timeout=1)


@pytest.mark.asyncio
async def test_screen_ws_disconnect_handled(web_client, mocker):
    """Test screen WebSocket disconnects cleanly."""
    mocker.patch(
        "rpi_usb_cloner.ui.display.get_display_png_bytes", return_value=b"frame"
    )
    mocker.patch("rpi_usb_cloner.ui.display.clear_dirty_flag")

    ws = await asyncio.wait_for(
        web_client.session.ws_connect(_ws_url(web_client, "/ws/screen")), timeout=1
    )
    await asyncio.wait_for(ws.receive(), timeout=1)
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(ws.close(), timeout=1)
    assert ws.closed


@pytest.mark.asyncio
async def test_screen_ws_broadcasts_to_multiple_clients(web_client, mocker):
    """Test screen WebSocket broadcasts frames to multiple clients."""
    mocker.patch(
        "rpi_usb_cloner.ui.display.get_display_png_bytes", return_value=b"frame"
    )
    mocker.patch("rpi_usb_cloner.ui.display.clear_dirty_flag")

    ws_one = await asyncio.wait_for(
        web_client.session.ws_connect(_ws_url(web_client, "/ws/screen")), timeout=1
    )
    ws_two = await asyncio.wait_for(
        web_client.session.ws_connect(_ws_url(web_client, "/ws/screen")), timeout=1
    )

    await asyncio.wait_for(ws_one.receive(), timeout=1)
    await asyncio.wait_for(ws_two.receive(), timeout=1)

    notifier = web_client.app[server.DISPLAY_NOTIFIER_KEY]
    notifier.mark_update_threadsafe()

    message_one = await asyncio.wait_for(ws_one.receive(), timeout=1)
    message_two = await asyncio.wait_for(ws_two.receive(), timeout=1)

    assert message_one.type == WSMsgType.BINARY
    assert message_two.type == WSMsgType.BINARY

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(ws_one.close(), timeout=1)
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(ws_two.close(), timeout=1)
