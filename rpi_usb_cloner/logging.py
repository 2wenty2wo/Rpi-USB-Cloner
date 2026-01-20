from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

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


def setup_logging(
    app_context: AppContext | None,
    *,
    debug: bool = False,
    log_dir: Path | None = None,
) -> Logger:
    logger.remove()
    logger.configure(extra={"job_id": "-", "tags": [], "source": "APP"})
    level = "DEBUG" if debug else "INFO"

    logger.add(
        sys.stderr,
        level=level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level} | {extra[source]} | {extra[job_id]} |"
            " {message}"
        ),
    )

    log_dir = log_dir or DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "rpi-usb-cloner.log",
        rotation="5 MB",
        retention="7 days",
        compression="zip",
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level} | {extra[source]} | {extra[job_id]} |"
            " {message}"
        ),
    )

    if app_context is not None:

        def _app_context_sink(message) -> None:
            record = message.record
            app_context.add_log(
                record["message"],
                level=record["level"].name.lower(),
                tags=record["extra"].get("tags", []),
                timestamp=record["time"],
                source=record["extra"].get("source"),
            )

        logger.add(_app_context_sink, enqueue=True)

    return logger


def get_logger(
    *,
    job_id: str | None = None,
    tags: Iterable[str] | None = None,
    source: str | None = None,
) -> Logger:
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
    yield get_logger(job_id=job_id, **extra)
