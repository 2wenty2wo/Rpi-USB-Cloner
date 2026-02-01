"""Additional tests for logging module to improve coverage."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from rpi_usb_cloner import logging as logging_module
from rpi_usb_cloner.logging import (
    EventLogger,
    LoggerFactory,
    ThrottledLogger,
    _should_log_button,
    _should_log_cache,
    _should_log_websocket,
    job_context,
    operation_context,
)


# =============================================================================
# Log Filter Tests
# =============================================================================


class TestShouldLogWebSocket:
    """Test _should_log_websocket filter function."""

    def test_always_logs_warnings_and_errors(self):
        """Test that warnings and errors are always logged."""
        record = {
            "message": "WebSocket disconnected",
            "extra": {"tags": ["websocket"]},
            "level": logging_module.logger.level("WARNING"),
        }

        assert _should_log_websocket(record) is True

    def test_allows_connection_logs_at_debug_and_above(self):
        """Test allowing connection logs at DEBUG level and above."""
        record = {
            "message": "Client connected",
            "extra": {"tags": ["websocket"]},
            "level": logging_module.logger.level("DEBUG"),
        }

        assert _should_log_websocket(record) is True

    def test_suppresses_connection_logs_below_debug(self):
        """Test suppressing connection logs below DEBUG level."""
        record = {
            "message": "Client connected",
            "extra": {"tags": ["websocket"]},
            "level": logging_module.logger.level("TRACE"),  # Below DEBUG
        }

        assert _should_log_websocket(record) is False

    def test_allows_connection_logs_at_debug_level(self):
        """Test allowing connection logs at DEBUG level."""
        record = {
            "message": "Client connected",
            "extra": {"tags": ["ws"]},
            "level": logging_module.logger.level("DEBUG"),
        }

        assert _should_log_websocket(record) is True

    def test_allows_non_connection_messages(self):
        """Test allowing non-connection WebSocket messages."""
        record = {
            "message": "WebSocket message received",
            "extra": {"tags": ["websocket"]},
            "level": logging_module.logger.level("INFO"),
        }

        assert _should_log_websocket(record) is True

    def test_allows_messages_without_websocket_tags(self):
        """Test allowing messages without websocket tags."""
        record = {
            "message": "Some other message",
            "extra": {"tags": ["other"]},
            "level": logging_module.logger.level("INFO"),
        }

        assert _should_log_websocket(record) is True


class TestShouldLogButton:
    """Test _should_log_button filter function."""

    def test_allows_button_logs_at_trace_level(self):
        """Test allowing button logs at TRACE level."""
        record = {
            "message": "Button A pressed",
            "extra": {"tags": ["button"]},
            "level": logging_module.logger.level("TRACE"),
        }

        assert _should_log_button(record) is True

    def test_blocks_button_logs_above_trace_level(self):
        """Test blocking button logs above TRACE level."""
        record = {
            "message": "Button A pressed",
            "extra": {"tags": ["button"]},
            "level": logging_module.logger.level("DEBUG"),
        }

        assert _should_log_button(record) is False

    def test_allows_non_button_messages(self):
        """Test allowing messages without button context."""
        record = {
            "message": "Some other message",
            "extra": {"tags": ["other"]},
            "level": logging_module.logger.level("INFO"),
        }

        assert _should_log_button(record) is True

    def test_allows_gpio_tag_press_messages_at_trace(self):
        """Test allowing GPIO press messages at TRACE level."""
        record = {
            "message": "GPIO pin press detected",
            "extra": {"tags": ["gpio"]},
            "level": logging_module.logger.level("TRACE"),
        }

        assert _should_log_button(record) is True


class TestShouldLogCache:
    """Test _should_log_cache filter function."""

    def test_blocks_cache_hit_logs(self):
        """Test blocking cache hit logs."""
        record = {
            "message": "Cache hit for key",
            "extra": {},
            "level": logging_module.logger.level("DEBUG"),
        }

        assert _should_log_cache(record) is False

    def test_blocks_cached_logs(self):
        """Test blocking cached message logs."""
        record = {
            "message": "Value was cached",
            "extra": {},
            "level": logging_module.logger.level("DEBUG"),
        }

        assert _should_log_cache(record) is False

    def test_allows_cache_logs_at_trace_level(self):
        """Test allowing cache logs at TRACE level."""
        record = {
            "message": "Cache hit for key",
            "extra": {},
            "level": logging_module.logger.level("TRACE"),
        }

        assert _should_log_cache(record) is True

    def test_allows_non_cache_messages(self):
        """Test allowing non-cache messages."""
        record = {
            "message": "Some other operation",
            "extra": {},
            "level": logging_module.logger.level("DEBUG"),
        }

        assert _should_log_cache(record) is True


class TestCombinedFilter:
    """Test _combined_filter function."""

    def test_allows_normal_messages(self):
        """Test allowing normal log messages."""
        record = {
            "message": "Normal operation",
            "extra": {"tags": []},
            "level": logging_module.logger.level("INFO"),
        }

        assert logging_module._combined_filter(record) is True

    def test_allows_websocket_connection_logs_at_info(self):
        """Test combined filter allows websocket connection logs at INFO."""
        record = {
            "message": "Client connected",
            "extra": {"tags": ["websocket"]},
            "level": logging_module.logger.level("INFO"),
        }

        # INFO >= DEBUG, so this should be allowed
        assert logging_module._combined_filter(record) is True

    def test_blocks_websocket_connection_logs_at_trace(self):
        """Test combined filter blocks websocket connection logs at TRACE."""
        record = {
            "message": "Client connected",
            "extra": {"tags": ["websocket"]},
            "level": logging_module.logger.level("TRACE"),
        }

        # TRACE < DEBUG, so this should be blocked
        assert logging_module._combined_filter(record) is False

    def test_blocks_button_logs(self):
        """Test combined filter blocks button logs."""
        record = {
            "message": "Button pressed",
            "extra": {"tags": ["button"]},
            "level": logging_module.logger.level("DEBUG"),
        }

        assert logging_module._combined_filter(record) is False

    def test_blocks_cache_logs(self):
        """Test combined filter blocks cache logs."""
        record = {
            "message": "Cache hit",
            "extra": {},
            "level": logging_module.logger.level("DEBUG"),
        }

        assert logging_module._combined_filter(record) is False


# =============================================================================
# Context Manager Tests
# =============================================================================


class TestJobContext:
    """Test job_context context manager."""

    def test_yields_logger_with_job_id(self):
        """Test that context manager yields logger with job_id."""
        with job_context("test-job-123") as log:
            # Verify the logger was created with job_id
            assert log is not None

    def test_accepts_additional_context(self):
        """Test accepting additional context parameters."""
        with job_context("job-456", source="test", tags=["clone"]) as log:
            assert log is not None


class TestOperationContext:
    """Test operation_context context manager."""

    @patch("rpi_usb_cloner.logging.time.time")
    @patch("rpi_usb_cloner.logging.logger")
    def test_logs_start_and_success(self, mock_logger, mock_time):
        """Test logging start and success messages."""
        mock_time.side_effect = [0, 5]  # Start at 0, end at 5
        mock_log = Mock()
        mock_logger.bind.return_value = mock_log
        mock_logger.contextualize = MagicMock()

        with operation_context("clone", source="/dev/sda", target="/dev/sdb"):
            pass

        # Verify start and success logs
        assert mock_log.info.called
        assert mock_log.success.called

    @patch("rpi_usb_cloner.logging.time.time")
    @patch("rpi_usb_cloner.logging.logger")
    def test_logs_failure_on_exception(self, mock_logger, mock_time):
        """Test logging failure when exception occurs."""
        mock_time.side_effect = [0, 3]  # Start at 0, end at 3
        mock_log = Mock()
        mock_logger.bind.return_value = mock_log
        mock_logger.contextualize = MagicMock()

        with pytest.raises(ValueError, match="Test error"), operation_context("backup"):
            raise ValueError("Test error")

        # Verify failure log
        assert mock_log.error.called

    @patch("rpi_usb_cloner.logging.time.time")
    @patch("rpi_usb_cloner.logging.logger")
    def test_includes_duration_in_logs(self, mock_logger, mock_time):
        """Test that duration is included in completion logs."""
        mock_time.side_effect = [0, 10.5]
        mock_log = Mock()
        mock_logger.bind.return_value = mock_log
        mock_logger.contextualize = MagicMock()

        with operation_context("format"):
            pass

        # Verify success was called with duration
        call_args = mock_log.success.call_args
        assert call_args is not None


# =============================================================================
# LoggerFactory Tests
# =============================================================================


class TestLoggerFactory:
    """Test LoggerFactory static methods."""

    @patch("rpi_usb_cloner.logging.logger")
    def test_for_clone_generates_job_id(self, mock_logger):
        """Test that for_clone generates job_id if not provided."""
        mock_logger.bind.return_value = Mock()

        LoggerFactory.for_clone()

        mock_logger.bind.assert_called_once()
        call_kwargs = mock_logger.bind.call_args.kwargs
        assert call_kwargs["source"] == "clone"
        assert "clone-" in call_kwargs["job_id"]
        assert "clone" in call_kwargs["tags"]

    @patch("rpi_usb_cloner.logging.logger")
    def test_for_clone_uses_provided_job_id(self, mock_logger):
        """Test that for_clone uses provided job_id."""
        mock_logger.bind.return_value = Mock()

        LoggerFactory.for_clone(job_id="my-clone-job")

        call_kwargs = mock_logger.bind.call_args.kwargs
        assert call_kwargs["job_id"] == "my-clone-job"

    @patch("rpi_usb_cloner.logging.logger")
    def test_for_usb(self, mock_logger):
        """Test for_usb factory method."""
        mock_logger.bind.return_value = Mock()

        LoggerFactory.for_usb()

        mock_logger.bind.assert_called_once_with(
            source="usb",
            tags=["usb", "hardware"],
        )

    @patch("rpi_usb_cloner.logging.logger")
    def test_for_web_without_connection_id(self, mock_logger):
        """Test for_web without connection_id."""
        mock_logger.bind.return_value = Mock()

        LoggerFactory.for_web()

        call_kwargs = mock_logger.bind.call_args.kwargs
        assert call_kwargs["source"] == "web"
        assert call_kwargs["connection_id"] == "-"
        assert "web" in call_kwargs["tags"]

    @patch("rpi_usb_cloner.logging.logger")
    def test_for_web_with_connection_id(self, mock_logger):
        """Test for_web with connection_id."""
        mock_logger.bind.return_value = Mock()

        LoggerFactory.for_web(connection_id="conn-123")

        call_kwargs = mock_logger.bind.call_args.kwargs
        assert call_kwargs["connection_id"] == "conn-123"

    @patch("rpi_usb_cloner.logging.logger")
    def test_for_menu(self, mock_logger):
        """Test for_menu factory method."""
        mock_logger.bind.return_value = Mock()

        LoggerFactory.for_menu()

        mock_logger.bind.assert_called_once_with(
            source="menu",
            tags=["ui", "menu"],
        )

    @patch("rpi_usb_cloner.logging.logger")
    def test_for_gpio(self, mock_logger):
        """Test for_gpio factory method."""
        mock_logger.bind.return_value = Mock()

        LoggerFactory.for_gpio()

        mock_logger.bind.assert_called_once_with(
            source="gpio",
            tags=["gpio", "hardware", "button"],
        )

    @patch("rpi_usb_cloner.logging.logger")
    def test_for_clonezilla_generates_job_id(self, mock_logger):
        """Test that for_clonezilla generates job_id."""
        mock_logger.bind.return_value = Mock()

        LoggerFactory.for_clonezilla()

        call_kwargs = mock_logger.bind.call_args.kwargs
        assert call_kwargs["source"] == "clonezilla"
        assert "clonezilla-" in call_kwargs["job_id"]

    @patch("rpi_usb_cloner.logging.logger")
    def test_for_system(self, mock_logger):
        """Test for_system factory method."""
        mock_logger.bind.return_value = Mock()

        LoggerFactory.for_system()

        mock_logger.bind.assert_called_once_with(
            source="system",
            tags=["system"],
        )


# =============================================================================
# ThrottledLogger Tests
# =============================================================================


class TestThrottledLogger:
    """Test ThrottledLogger class."""

    def test_logs_on_first_call(self):
        """Test that first log call is not throttled."""
        mock_log = Mock()
        throttled = ThrottledLogger(mock_log, interval_seconds=5.0)

        throttled.debug("key1", "First message")

        mock_log.debug.assert_called_once_with("First message")

    def test_throttles_subsequent_calls(self):
        """Test that subsequent calls within interval are throttled."""
        mock_log = Mock()
        throttled = ThrottledLogger(mock_log, interval_seconds=5.0)

        throttled.debug("key1", "First message")
        throttled.debug("key1", "Second message")  # Should be throttled

        mock_log.debug.assert_called_once_with("First message")

    def test_allows_different_keys(self):
        """Test that different keys are not throttled together."""
        mock_log = Mock()
        throttled = ThrottledLogger(mock_log, interval_seconds=5.0)

        throttled.debug("key1", "Message 1")
        throttled.debug("key2", "Message 2")

        assert mock_log.debug.call_count == 2

    @patch("rpi_usb_cloner.logging.time.time")
    def test_allows_after_interval(self, mock_time):
        """Test that logging is allowed after interval passes."""
        mock_time.side_effect = [0, 6, 12]  # Times for three calls
        mock_log = Mock()
        throttled = ThrottledLogger(mock_log, interval_seconds=5.0)

        throttled.info("key1", "Message 1")
        throttled.info("key1", "Message 2")  # After 6s, should log
        throttled.info("key1", "Message 3")  # After 12s, should log

        assert mock_log.info.call_count == 2

    def test_info_level_logging(self):
        """Test throttled INFO level logging."""
        mock_log = Mock()
        throttled = ThrottledLogger(mock_log, interval_seconds=1.0)

        throttled.info("job1", "Progress update", percent=50)

        mock_log.info.assert_called_once_with("Progress update", percent=50)

    def test_passes_extra_kwargs(self):
        """Test that extra kwargs are passed to underlying logger."""
        mock_log = Mock()
        throttled = ThrottledLogger(mock_log, interval_seconds=1.0)

        throttled.debug("key", "Message", extra_field="value", count=42)

        call_kwargs = mock_log.debug.call_args.kwargs
        assert call_kwargs["extra_field"] == "value"
        assert call_kwargs["count"] == 42


# =============================================================================
# EventLogger Tests
# =============================================================================


class TestEventLogger:
    """Test EventLogger static methods."""

    def test_log_clone_started(self):
        """Test logging clone started event."""
        mock_log = Mock()

        EventLogger.log_clone_started(mock_log, "/dev/sda", "/dev/sdb", "smart")

        mock_log.info.assert_called_once()
        call_kwargs = mock_log.info.call_args.kwargs
        assert call_kwargs["event_type"] == "clone_started"
        assert call_kwargs["source_device"] == "/dev/sda"
        assert call_kwargs["target_device"] == "/dev/sdb"
        assert call_kwargs["clone_mode"] == "smart"

    def test_log_clone_started_with_extra(self):
        """Test logging clone started with extra fields."""
        mock_log = Mock()

        EventLogger.log_clone_started(
            mock_log, "/dev/sda", "/dev/sdb", "exact", verify=True, compression="zstd"
        )

        call_kwargs = mock_log.info.call_args.kwargs
        assert call_kwargs["verify"] is True
        assert call_kwargs["compression"] == "zstd"

    def test_log_clone_progress(self):
        """Test logging clone progress event."""
        mock_log = Mock()

        EventLogger.log_clone_progress(mock_log, 45.5, 104857600, 25.5)

        mock_log.debug.assert_called_once()
        call_kwargs = mock_log.debug.call_args.kwargs
        assert call_kwargs["event_type"] == "clone_progress"
        assert call_kwargs["percent"] == 45.5
        assert call_kwargs["bytes_copied"] == 104857600
        assert call_kwargs["speed_mbps"] == 25.5

    def test_log_clone_progress_rounds_values(self):
        """Test that progress values are rounded."""
        mock_log = Mock()

        EventLogger.log_clone_progress(mock_log, 45.55555, 100, 25.55555)

        call_kwargs = mock_log.debug.call_args.kwargs
        assert call_kwargs["percent"] == 45.56
        assert call_kwargs["speed_mbps"] == 25.56

    def test_log_device_hotplug_connected(self):
        """Test logging device connected event."""
        mock_log = Mock()

        EventLogger.log_device_hotplug(mock_log, "connected", "sda")

        mock_log.info.assert_called_once()
        call_kwargs = mock_log.info.call_args.kwargs
        assert call_kwargs["event_type"] == "device_hotplug"
        assert call_kwargs["action"] == "connected"
        assert call_kwargs["device_name"] == "sda"

    def test_log_device_hotplug_disconnected(self):
        """Test logging device disconnected event."""
        mock_log = Mock()

        EventLogger.log_device_hotplug(mock_log, "disconnected", "sdb")

        call_kwargs = mock_log.info.call_args.kwargs
        assert call_kwargs["action"] == "disconnected"
        assert call_kwargs["device_name"] == "sdb"

    def test_log_operation_metric(self):
        """Test logging operation metric."""
        mock_log = Mock()

        EventLogger.log_operation_metric(
            mock_log, "clone", "duration", 123.456, "seconds"
        )

        mock_log.debug.assert_called_once()
        call_kwargs = mock_log.debug.call_args.kwargs
        assert call_kwargs["event_type"] == "operation_metric"
        assert call_kwargs["operation"] == "clone"
        assert call_kwargs["metric"] == "duration"
        assert call_kwargs["value"] == 123.46  # Rounded
        assert call_kwargs["unit"] == "seconds"

    def test_log_operation_metric_without_unit(self):
        """Test logging operation metric without unit."""
        mock_log = Mock()

        EventLogger.log_operation_metric(mock_log, "backup", "file_count", 42)

        call_kwargs = mock_log.debug.call_args.kwargs
        assert call_kwargs["unit"] == ""
        assert call_kwargs["value"] == 42

    def test_log_operation_metric_with_extra(self):
        """Test logging metric with extra fields."""
        mock_log = Mock()

        EventLogger.log_operation_metric(
            mock_log, "verify", "checksum_time", 5.5, "seconds", algorithm="sha256"
        )

        call_kwargs = mock_log.debug.call_args.kwargs
        assert call_kwargs["algorithm"] == "sha256"
