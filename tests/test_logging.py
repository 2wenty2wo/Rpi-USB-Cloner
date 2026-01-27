"""Tests for logging setup and helpers."""

from __future__ import annotations

from rpi_usb_cloner import logging as logging_module


class FakeAppContext:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def add_log(self, message, **kwargs) -> None:
        self.entries.append({"message": message, **kwargs})


def test_setup_logging_respects_web_ui_min_level(tmp_path):
    """Test web UI sink respects minimum log level."""
    app_context = FakeAppContext()
    logging_module.setup_logging(
        app_context,
        debug=False,
        trace=False,
        log_dir=tmp_path / "logs",
        web_ui_min_level="WARNING",
    )

    log = logging_module.get_logger(source="test", tags=["unit"])
    log.info("Info message")
    log.warning("Warning message")

    logging_module.logger.complete()

    assert len(app_context.entries) == 1
    assert app_context.entries[0]["message"] == "Warning message"


def test_get_logger_preserves_context_metadata():
    """Test bound logger keeps job_id, tags, and source metadata."""
    logging_module.logger.remove()
    records: list[dict] = []

    def sink(message):
        records.append(message.record)

    logging_module.logger.add(sink, enqueue=False)

    log = logging_module.get_logger(job_id="job-123", tags=["clone"], source="clone")
    log.info("Context test")

    assert records
    record = records[0]
    assert record["extra"]["job_id"] == "job-123"
    assert record["extra"]["tags"] == ["clone"]
    assert record["extra"]["source"] == "clone"


def test_combined_filter_blocks_button_logs_above_trace():
    """Test combined filter suppresses button logs above TRACE level."""
    record = {
        "message": "Button press",
        "extra": {"tags": ["button"]},
        "level": logging_module.logger.level("DEBUG"),
    }

    assert logging_module._combined_filter(record) is False

    record["level"] = logging_module.logger.level("TRACE")
    assert logging_module._combined_filter(record) is True
