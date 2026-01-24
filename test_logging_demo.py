#!/usr/bin/env python3
"""
Test script to demonstrate the comprehensive logging system.

Usage:
    python3 test_logging_demo.py              # Normal mode (INFO+)
    python3 test_logging_demo.py --debug      # Debug mode (DEBUG+)
    python3 test_logging_demo.py --trace      # Trace mode (TRACE+)
"""
import argparse
import sys
import time
from pathlib import Path


# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from rpi_usb_cloner.logging import (
    EventLogger,
    LoggerFactory,
    ThrottledLogger,
    operation_context,
    setup_logging,
)


def main():
    parser = argparse.ArgumentParser(description="Logging System Test")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument("--trace", action="store_true", help="Enable TRACE logging")
    args = parser.parse_args()

    # Setup logging (without app_context for this test)
    setup_logging(None, debug=args.debug, trace=args.trace)

    print("=" * 80)
    print("LOGGING SYSTEM TEST")
    print("=" * 80)
    print(f"Mode: {'TRACE' if args.trace else 'DEBUG' if args.debug else 'INFO'}")
    print("=" * 80)
    print()

    # Test 1: LoggerFactory domain-specific loggers
    print("TEST 1: LoggerFactory Domain-Specific Loggers")
    print("-" * 80)

    system_log = LoggerFactory.for_system()
    system_log.info("System logger initialized", component="test")

    usb_log = LoggerFactory.for_usb()
    usb_log.info(
        "USB device detected", device="sda", vendor="Kingston", size_bytes=8589934592
    )
    usb_log.debug("USB poll completed", devices_found=3, duration_ms=145)
    usb_log.trace("USB device state unchanged")  # Only visible in trace mode

    web_log = LoggerFactory.for_web()
    web_log.info("Web server started", host="0.0.0.0", port=8000)
    web_log.debug(
        "WebSocket connected from 192.168.1.100", tags=["ws", "websocket", "connection"]
    )
    web_log.trace("WebSocket frame sent", bytes=4096)  # Only visible in trace mode

    gpio_log = LoggerFactory.for_gpio()
    gpio_log.info("GPIO initialized", pins_configured=7)
    gpio_log.trace(
        "Button pressed: RIGHT", tags=["gpio", "hardware", "button"]
    )  # Only visible in trace mode

    print()

    # Test 2: operation_context with automatic timing
    print("TEST 2: operation_context() - Automatic Timing & Job Tracking")
    print("-" * 80)

    try:
        with operation_context(
            "clone", source="/dev/sda", target="/dev/sdb", mode="smart"
        ) as log:
            log.debug("Unmounting source device")
            time.sleep(0.5)  # Simulate work
            log.debug("Partition table replicated", method="sfdisk")
            time.sleep(0.5)  # Simulate work
            log.info("Cloning partition 1 of 2", progress=50)
            time.sleep(0.5)  # Simulate work
            # Success is logged automatically
    except Exception:
        # Failure would be logged automatically
        pass

    print()

    # Test 3: EventLogger structured events
    print("TEST 3: EventLogger - Structured Event Logging")
    print("-" * 80)

    clone_log = LoggerFactory.for_clone()
    EventLogger.log_clone_started(
        clone_log,
        source="/dev/sda",
        target="/dev/sdb",
        mode="smart",
        total_bytes=8589934592,
    )
    EventLogger.log_clone_progress(
        clone_log,
        percent=25.0,
        bytes_copied=2147483648,
        speed_mbps=98.5,
        eta_seconds=180,
    )
    EventLogger.log_device_hotplug(
        usb_log,
        action="connected",
        device="sdc",
        vendor="SanDisk",
        size_bytes=16106127360,
    )
    EventLogger.log_operation_metric(
        clone_log,
        operation="clone",
        metric_name="throughput",
        value=105.3,
        unit="mbps",
    )

    print()

    # Test 4: ThrottledLogger for high-frequency events
    print("TEST 4: ThrottledLogger - Rate-Limited Logging (5s interval)")
    print("-" * 80)

    throttled = ThrottledLogger(clone_log, interval_seconds=2.0)
    for i in range(10):
        # This will only log every 2 seconds, even though we call it 10 times
        throttled.info(
            "clone-job123",
            "Progress update",
            percent=i * 10,
            speed_mbps=100.0,
        )
        time.sleep(0.3)

    print()

    # Test 5: Log levels demonstration
    print("TEST 5: All Log Levels")
    print("-" * 80)

    test_log = LoggerFactory.for_system()
    test_log.trace("TRACE level - Ultra-verbose (button presses, cache hits)")
    test_log.debug("DEBUG level - Detailed diagnostics (command execution)")
    test_log.info("INFO level - Important events (operations, state changes)")
    test_log.success("SUCCESS level - Successful completion")
    test_log.warning("WARNING level - Unexpected but handled situations")
    test_log.error("ERROR level - Errors that were handled")
    # test_log.critical("CRITICAL level - System failures (uncomment to see)")

    print()

    # Test 6: Tag-based filtering
    print("TEST 6: Tag-Based Filtering (WebSocket connection logs)")
    print("-" * 80)
    print("Note: WebSocket connection/disconnection logs are filtered in normal mode")
    print("      They only appear in DEBUG or TRACE mode")
    print()

    ws_log = LoggerFactory.for_web()
    ws_log.debug(
        "Screen WebSocket connected from 192.168.1.100",
        tags=["ws", "websocket", "connection"],
    )
    ws_log.debug(
        "Control WebSocket connected from 192.168.1.101",
        tags=["ws", "websocket", "connection"],
    )
    ws_log.warning(
        "WebSocket error: Connection closed", tags=["ws", "websocket", "error"]
    )
    ws_log.debug(
        "Screen WebSocket disconnected from 192.168.1.100",
        tags=["ws", "websocket", "connection"],
    )

    print()

    # Test 7: Simulated clone operation with errors
    print("TEST 7: operation_context() - Error Handling")
    print("-" * 80)

    try:
        with operation_context("format", device="/dev/sdc") as log:
            log.debug("Unmounting device")
            time.sleep(0.3)
            log.debug("Creating new partition table")
            time.sleep(0.3)
            # Simulate an error
            raise RuntimeError("Device is write-protected")
    except RuntimeError:
        pass  # Error was already logged

    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print()
    print("Log files created in: ~/.local/state/rpi-usb-cloner/logs/")
    print("- operations.log   (INFO+ events)")
    print("- debug.log        (DEBUG+ events, if --debug or --trace)")
    print("- trace.log        (TRACE+ events, if --trace)")
    print("- structured.jsonl (JSON logs for analysis)")
    print()
    print("Try running with different modes:")
    print("  python3 test_logging_demo.py              # Normal (INFO+)")
    print("  python3 test_logging_demo.py --debug      # Debug (DEBUG+)")
    print("  python3 test_logging_demo.py --trace      # Trace (TRACE+)")
    print()


if __name__ == "__main__":
    main()
