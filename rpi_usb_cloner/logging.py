from __future__ import annotations

import os
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable

if TYPE_CHECKING:
    from loguru import Logger
    from rpi_usb_cloner.app.context import AppContext

from loguru import logger

DEFAULT_LOG_DIR = Path(
    os.environ.get(
        "RPI_USB_CLONER_LOG_DIR",
        Path.home() / ".local" / "state" / "rpi-usb-cloner" / "logs",
    )
)

# Note: TRACE level already exists in loguru at level 5 (below DEBUG which is 10)
# We don't need to add it, just use it with log.trace()


def _should_log_websocket(record) -> bool:
    """Filter WebSocket connection/disconnection logs to reduce noise."""
    message = record["message"].lower()
    tags = record["extra"].get("tags", [])

    # Always log errors
    if record["level"].no >= logger.level("WARNING").no:
        return True

    # For WebSocket connection/disconnection logs, only log if:
    # 1. It's an error/warning, OR
    # 2. It's not a connection/disconnection message
    if "ws" in tags or "websocket" in tags:
        if "connected" in message or "disconnected" in message:
            # Suppress routine connection logs, only show in debug
            return record["level"].no >= logger.level("DEBUG").no

    return True


def _should_log_button(record) -> bool:
    """Filter button press logs - only show in TRACE mode."""
    message = record["message"].lower()
    tags = record["extra"].get("tags", [])

    # Button presses are TRACE-level only
    if "button" in tags or "gpio" in tags:
        if "button" in message or "press" in message:
            return record["level"].no <= logger.level("TRACE").no

    return True


def _should_log_cache(record) -> bool:
    """Filter cache hit logs - these are noisy and not useful."""
    message = record["message"].lower()

    # Suppress cache hit logs
    if "cache hit" in message or "cached" in message:
        # Only show cache operations in TRACE mode
        return record["level"].no <= logger.level("TRACE").no

    return True


def _combined_filter(record) -> bool:
    """Combined filter for all log suppression rules."""
    return (
        _should_log_websocket(record)
        and _should_log_button(record)
        and _should_log_cache(record)
    )


def setup_logging(
    app_context: AppContext | None,
    *,
    debug: bool = False,
    trace: bool = False,
    log_dir: Path | None = None,
    web_ui_min_level: str | None = None,
) -> Logger:
    """
    Setup multi-tier logging with separate sinks for different log levels.

    Logging Tiers:
    - CRITICAL/ERROR: System failures, unrecoverable errors
    - SUCCESS/INFO: Operations, state changes, important events
    - DEBUG: Detailed diagnostics, command execution
    - TRACE: Ultra-verbose (button presses, every WebSocket message, etc.)

    Log Files:
    - operations.log: INFO+ events (7 day retention)
    - debug.log: DEBUG+ events when --debug is enabled (3 day retention)
    - trace.log: TRACE+ events when --trace is enabled (1 day retention)
    - structured.jsonl: Structured JSON logs for analysis (7 day retention)

    Args:
        app_context: Application context for web UI log sink
        debug: Enable DEBUG level logging
        trace: Enable TRACE level logging (very verbose)
        log_dir: Custom log directory (defaults to ~/.local/state/rpi-usb-cloner/logs)
        web_ui_min_level: Minimum log level for web UI log buffer sink
    """
    logger.remove()
    logger.configure(extra={"job_id": "-", "tags": [], "source": "APP"})

    # Determine log levels
    if trace:
        console_level = "TRACE"
        file_level = "TRACE"
    elif debug:
        console_level = "DEBUG"
        file_level = "DEBUG"
    else:
        console_level = "INFO"
        file_level = "INFO"

    # SINK 1: Console (stderr) - User-facing, filtered
    logger.add(
        sys.stderr,
        level=console_level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        filter=_combined_filter,
        colorize=True,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[source]: <15}</cyan> | "
            "<blue>{extra[job_id]: <15}</blue> | "
            "{message}"
        ),
    )

    # Setup log directory
    log_dir = log_dir or DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    # SINK 2: Operations Log - Important events only (INFO+)
    logger.add(
        log_dir / "operations.log",
        level="INFO",
        rotation="5 MB",
        retention="7 days",
        compression="zip",
        enqueue=True,
        backtrace=False,
        diagnose=False,
        filter=lambda record: record["level"].no >= logger.level("INFO").no,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{extra[source]: <15} | "
            "{extra[job_id]: <15} | "
            "{message}"
        ),
    )

    # SINK 3: Debug Log - Detailed diagnostics (DEBUG+ when debug=True)
    if debug or trace:
        logger.add(
            log_dir / "debug.log",
            level="DEBUG",
            rotation="10 MB",
            retention="3 days",
            compression="zip",
            enqueue=True,
            backtrace=True,
            diagnose=True,
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{extra[source]: <15} | "
                "{extra[job_id]: <15} | "
                "{extra[tags]} | "
                "{message}"
            ),
        )

    # SINK 4: Trace Log - Ultra-verbose (TRACE only, when trace=True)
    if trace:
        logger.add(
            log_dir / "trace.log",
            level="TRACE",
            rotation="50 MB",
            retention="1 day",
            compression="zip",
            enqueue=True,
            backtrace=False,
            diagnose=False,
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{extra[source]: <15} | "
                "{extra[job_id]: <15} | "
                "{message}"
            ),
        )

    # SINK 5: Structured JSON Log - For analysis tools (INFO+)
    logger.add(
        log_dir / "structured.jsonl",
        level="INFO",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        enqueue=True,
        serialize=True,  # Built-in JSON serialization
        format="{message}",
    )

    # SINK 6: App Context Buffer - For Web UI
    if app_context is not None:
        if web_ui_min_level is None:
            resolved_web_ui_level = "TRACE" if trace else "DEBUG" if debug else "INFO"
        else:
            resolved_web_ui_level = web_ui_min_level.upper()

        def _app_context_sink(message) -> None:
            record = message.record
            # Apply level threshold before sending to the web UI.
            if record["level"].no >= logger.level(resolved_web_ui_level).no:
                app_context.add_log(
                    record["message"],
                    level=record["level"].name.lower(),
                    tags=record["extra"].get("tags", []),
                    timestamp=record["time"],
                    source=record["extra"].get("source"),
                )

        # Keep the combined filter so button/websocket/cache noise stays hidden
        # from the web UI log stream unless explicitly logged at higher levels.
        logger.add(_app_context_sink, enqueue=True, filter=_combined_filter)

    return logger


def get_logger(
    *,
    job_id: str | None = None,
    tags: Iterable[str] | None = None,
    source: str | None = None,
) -> Logger:
    """
    Get a logger with bound context.

    Args:
        job_id: Job identifier for tracking operations
        tags: Tags for filtering (e.g., ["clone", "storage"])
        source: Source component (e.g., "clone", "usb", "web")

    Returns:
        Logger with bound context
    """
    extras: dict[str, object] = {}
    if job_id is not None:
        extras["job_id"] = job_id
    if tags is not None:
        extras["tags"] = list(tags)
    if source is not None:
        extras["source"] = source
    return logger.bind(**extras)


@contextmanager
def job_context(job_id: str, **extra):
    """
    Context manager for simple job tracking.

    Args:
        job_id: Job identifier
        **extra: Additional context to bind

    Yields:
        Logger with bound job_id
    """
    yield get_logger(job_id=job_id, **extra)


@contextmanager
def operation_context(operation: str, **details):
    """
    Context manager for tracking long-running operations with automatic timing.

    Automatically logs operation start, completion, and failure with duration tracking.

    Args:
        operation: Operation name (e.g., "clone", "backup", "format")
        **details: Operation-specific details to log

    Yields:
        Logger bound with job_id and operation context

    Example:
        with operation_context("clone", source="/dev/sda", target="/dev/sdb") as log:
            log.debug("Unmounting devices")
            # ... perform clone ...
            log.info("Clone progress", percent=50)
    """
    job_id = f"{operation}-{uuid.uuid4().hex[:8]}"

    # Bind context for all logs in this block
    with logger.contextualize(
        job_id=job_id,
        operation=operation,
        **details,
    ):
        start_time = time.time()
        log = logger.bind(source=operation, job_id=job_id, tags=[operation])

        # Log operation start
        log.info(f"{operation.capitalize()} started", **details)

        try:
            yield log
            duration = time.time() - start_time
            log.success(
                f"{operation.capitalize()} completed", duration_seconds=round(duration, 2)
            )
        except Exception as e:
            duration = time.time() - start_time
            log.error(
                f"{operation.capitalize()} failed",
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 2),
            )
            raise


class LoggerFactory:
    """
    Factory for creating domain-specific loggers with automatic context.

    Each factory method returns a logger pre-configured with appropriate
    source, tags, and context for the domain.
    """

    @staticmethod
    def for_clone(job_id: str | None = None, **details) -> Logger:
        """Logger for clone operations."""
        if job_id is None:
            job_id = f"clone-{uuid.uuid4().hex[:8]}"
        return logger.bind(
            job_id=job_id, source="clone", tags=["clone", "storage"], **details
        )

    @staticmethod
    def for_usb() -> Logger:
        """Logger for USB device detection and management."""
        return logger.bind(source="usb", tags=["usb", "hardware"])

    @staticmethod
    def for_web(connection_id: str | None = None) -> Logger:
        """Logger for web server operations."""
        if connection_id is None:
            connection_id = "-"
        return logger.bind(
            source="web", tags=["web", "ws"], connection_id=connection_id
        )

    @staticmethod
    def for_menu() -> Logger:
        """Logger for menu navigation and UI operations."""
        return logger.bind(source="menu", tags=["ui", "menu"])

    @staticmethod
    def for_gpio() -> Logger:
        """Logger for GPIO/hardware button operations."""
        return logger.bind(source="gpio", tags=["gpio", "hardware", "button"])

    @staticmethod
    def for_clonezilla(job_id: str | None = None) -> Logger:
        """Logger for Clonezilla backup/restore operations."""
        if job_id is None:
            job_id = f"clonezilla-{uuid.uuid4().hex[:8]}"
        return logger.bind(
            job_id=job_id, source="clonezilla", tags=["clonezilla", "backup"]
        )

    @staticmethod
    def for_system() -> Logger:
        """Logger for system operations (startup, shutdown, config)."""
        return logger.bind(source="system", tags=["system"])


class ThrottledLogger:
    """
    Logger wrapper that throttles high-frequency log events.

    Useful for progress updates or other high-volume logs that should
    only be emitted at intervals.
    """

    def __init__(self, log: Logger, interval_seconds: float = 5.0):
        """
        Initialize throttled logger.

        Args:
            log: Base logger to wrap
            interval_seconds: Minimum seconds between log emissions
        """
        self.log = log
        self.interval = interval_seconds
        self.last_log_time: dict[str, float] = {}

    def debug(self, key: str, message: str, **kwargs) -> None:
        """Log at DEBUG level, throttled by key."""
        self._throttled_log("DEBUG", key, message, **kwargs)

    def info(self, key: str, message: str, **kwargs) -> None:
        """Log at INFO level, throttled by key."""
        self._throttled_log("INFO", key, message, **kwargs)

    def _throttled_log(self, level: str, key: str, message: str, **kwargs) -> None:
        """
        Log message, but only if interval has passed since last log for this key.

        Args:
            level: Log level (DEBUG, INFO, etc.)
            key: Throttle key (e.g., job_id)
            message: Log message
            **kwargs: Additional context
        """
        now = time.time()
        last_time = self.last_log_time.get(key, 0)

        if now - last_time >= self.interval:
            log_method = getattr(self.log, level.lower())
            log_method(message, **kwargs)
            self.last_log_time[key] = now


class EventLogger:
    """
    Structured event logger using standardized schemas.

    Provides type-safe methods for logging common events with
    consistent structure and fields.
    """

    @staticmethod
    def log_clone_started(
        log: Logger, source: str, target: str, mode: str, **extra
    ) -> None:
        """Log clone operation start."""
        log.info(
            "Clone operation started",
            event_type="clone_started",
            source_device=source,
            target_device=target,
            clone_mode=mode,
            **extra,
        )

    @staticmethod
    def log_clone_progress(
        log: Logger, percent: float, bytes_copied: int, speed_mbps: float, **extra
    ) -> None:
        """Log clone progress update."""
        log.debug(
            "Clone progress update",
            event_type="clone_progress",
            percent=round(percent, 2),
            bytes_copied=bytes_copied,
            speed_mbps=round(speed_mbps, 2),
            **extra,
        )

    @staticmethod
    def log_device_hotplug(log: Logger, action: str, device: str, **extra) -> None:
        """Log USB device hotplug event."""
        log.info(
            f"USB device {action}",
            event_type="device_hotplug",
            action=action,  # "connected" or "disconnected"
            device_name=device,
            **extra,
        )

    @staticmethod
    def log_operation_metric(
        log: Logger, operation: str, metric_name: str, value: float, unit: str = "", **extra
    ) -> None:
        """Log operation performance metric."""
        log.debug(
            f"{operation} metric: {metric_name}",
            event_type="operation_metric",
            operation=operation,
            metric=metric_name,
            value=round(value, 2),
            unit=unit,
            **extra,
        )
