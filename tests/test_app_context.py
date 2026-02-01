"""
Tests for app/context.py module.

Covers:
- LogEntry dataclass creation and serialization
- AppContext initialization and state management
- add_log method with various input types
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

import pytest

from rpi_usb_cloner.app.context import AppContext, LogEntry


class TestLogEntry:
    """Test LogEntry dataclass."""

    def test_log_entry_creation_defaults(self):
        """Test LogEntry with default values."""
        entry = LogEntry(message="Test message")
        assert entry.message == "Test message"
        assert entry.level == "info"
        assert entry.tags == []
        assert entry.source is None
        assert entry.details is None
        assert isinstance(entry.timestamp, datetime)

    def test_log_entry_creation_full(self):
        """Test LogEntry with all values provided."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        entry = LogEntry(
            message="Test message",
            level="error",
            tags=["test", "error"],
            timestamp=timestamp,
            source="test_module",
            details={"key": "value"},
        )
        assert entry.message == "Test message"
        assert entry.level == "error"
        assert entry.tags == ["test", "error"]
        assert entry.timestamp == timestamp
        assert entry.source == "test_module"
        assert entry.details == {"key": "value"}

    def test_log_entry_to_dict(self):
        """Test LogEntry serialization to dict."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        entry = LogEntry(
            message="Test message",
            level="warning",
            tags=["tag1", "tag2"],
            timestamp=timestamp,
            source="test_source",
            details={"count": 42},
        )
        result = entry.to_dict()
        assert result["message"] == "Test message"
        assert result["level"] == "warning"
        assert result["tags"] == ["tag1", "tag2"]
        assert result["timestamp"] == timestamp.isoformat()
        assert result["source"] == "test_source"
        assert result["details"] == {"count": 42}

    def test_log_entry_to_dict_no_details(self):
        """Test LogEntry serialization with None details."""
        entry = LogEntry(message="Simple message")
        result = entry.to_dict()
        assert result["details"] is None

    def test_log_entry_tags_isolation(self):
        """Test that tags list is properly isolated between instances."""
        entry1 = LogEntry(message="Test 1", tags=["tag1"])
        entry2 = LogEntry(message="Test 2", tags=["tag2"])
        entry1.tags.append("extra")
        assert entry1.tags == ["tag1", "extra"]
        assert entry2.tags == ["tag2"]

    def test_log_entry_details_isolation(self):
        """Test that details dict is properly isolated between instances."""
        entry1 = LogEntry(message="Test 1", details={"key": "value1"})
        entry2 = LogEntry(message="Test 2", details={"key": "value2"})
        entry1.details["extra"] = "added"
        assert entry1.details == {"key": "value1", "extra": "added"}
        assert entry2.details == {"key": "value2"}


class TestAppContext:
    """Test AppContext dataclass."""

    def test_app_context_defaults(self):
        """Test AppContext with default values."""
        ctx = AppContext()
        assert ctx.display is None
        assert ctx.input_state == {}
        assert ctx.active_drive is None
        assert ctx.discovered_drives == []
        assert isinstance(ctx.log_buffer, deque)
        assert ctx.log_buffer.maxlen == 500
        assert ctx.operation_active is False
        assert ctx.allow_back_interrupt is False

    def test_app_context_custom_values(self):
        """Test AppContext with custom values."""
        ctx = AppContext(
            display=None,
            input_state={"button_a": True},
            active_drive="sda",
            discovered_drives=["sda", "sdb"],
            operation_active=True,
            allow_back_interrupt=True,
        )
        assert ctx.input_state == {"button_a": True}
        assert ctx.active_drive == "sda"
        assert ctx.discovered_drives == ["sda", "sdb"]
        assert ctx.operation_active is True
        assert ctx.allow_back_interrupt is True

    def test_add_log_string_message(self):
        """Test add_log with a string message."""
        ctx = AppContext()
        ctx.add_log("Test message", level="info", tags=["test"])
        
        assert len(ctx.log_buffer) == 1
        entry = ctx.log_buffer[0]
        assert entry.message == "Test message"
        assert entry.level == "info"
        assert entry.tags == ["test"]

    def test_add_log_empty_message(self):
        """Test add_log with empty string returns early."""
        ctx = AppContext()
        ctx.add_log("")
        assert len(ctx.log_buffer) == 0

    def test_add_log_log_entry_object(self):
        """Test add_log with LogEntry object."""
        ctx = AppContext()
        entry = LogEntry(message="Existing entry", level="error")
        ctx.add_log(entry)
        
        assert len(ctx.log_buffer) == 1
        result = ctx.log_buffer[0]
        assert result.message == "Existing entry"
        assert result.level == "error"

    def test_add_log_with_details(self):
        """Test add_log with details dictionary."""
        ctx = AppContext()
        ctx.add_log(
            "Operation completed",
            level="info",
            details={"duration": 10.5, "bytes": 1024},
        )
        
        entry = ctx.log_buffer[0]
        assert entry.details == {"duration": 10.5, "bytes": 1024}

    def test_add_log_with_source(self):
        """Test add_log with source parameter."""
        ctx = AppContext()
        ctx.add_log("Message", source="test_module")
        
        entry = ctx.log_buffer[0]
        assert entry.source == "test_module"

    def test_add_log_with_timestamp(self):
        """Test add_log with explicit timestamp."""
        ctx = AppContext()
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        ctx.add_log("Message", timestamp=timestamp)
        
        entry = ctx.log_buffer[0]
        assert entry.timestamp == timestamp

    def test_add_log_generates_timestamp(self):
        """Test that add_log generates timestamp if not provided."""
        ctx = AppContext()
        before = datetime.now()
        ctx.add_log("Message")
        after = datetime.now()
        
        entry = ctx.log_buffer[0]
        assert before <= entry.timestamp <= after

    def test_log_buffer_maxlen(self):
        """Test that log buffer respects maxlen."""
        ctx = AppContext()
        
        # Add more entries than maxlen
        for i in range(550):
            ctx.add_log(f"Message {i}")
        
        # Buffer should only contain the last 500 entries
        assert len(ctx.log_buffer) == 500
        # Oldest entry should be "Message 50"
        assert ctx.log_buffer[0].message == "Message 50"
        # Newest entry should be "Message 549"
        assert ctx.log_buffer[-1].message == "Message 549"

    def test_add_log_copies_details(self):
        """Test that add_log copies details to prevent mutation."""
        ctx = AppContext()
        details = {"key": "value"}
        ctx.add_log("Message", details=details)
        
        # Mutate original
        details["key"] = "mutated"
        
        # Entry should not be affected
        entry = ctx.log_buffer[0]
        assert entry.details == {"key": "value"}

    def test_add_log_copies_tags(self):
        """Test that add_log copies tags to prevent mutation."""
        ctx = AppContext()
        tags = ["tag1"]
        ctx.add_log("Message", tags=tags)
        
        # Mutate original
        tags.append("tag2")
        
        # Entry should not be affected
        entry = ctx.log_buffer[0]
        assert entry.tags == ["tag1"]

    def test_log_entry_with_none_message_in_buffer(self):
        """Test that entries with None message are not added."""
        ctx = AppContext()
        # This shouldn't happen in normal use, but test the edge case
        entry = LogEntry(message="")
        ctx.add_log(entry)
        assert len(ctx.log_buffer) == 0

    def test_app_context_log_buffer_isolation(self):
        """Test that each AppContext has isolated log buffer."""
        ctx1 = AppContext()
        ctx2 = AppContext()
        
        ctx1.add_log("Message 1")
        ctx2.add_log("Message 2")
        
        assert len(ctx1.log_buffer) == 1
        assert len(ctx2.log_buffer) == 1
        assert ctx1.log_buffer[0].message == "Message 1"
        assert ctx2.log_buffer[0].message == "Message 2"
