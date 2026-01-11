"""Tests for command execution utilities with progress tracking."""
import subprocess
import time
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from rpi_usb_cloner.storage.clone.command_runners import (
    configure_progress_logger,
    run_checked_command,
    run_checked_with_progress,
    run_checked_with_streaming_progress,
    run_progress_command,
)


class TestRunCheckedCommand:
    """Tests for run_checked_command function."""

    def test_successful_command(self, mock_subprocess_run):
        """Test successful command execution."""
        mock_subprocess_run.return_value = Mock(returncode=0, stdout="output", stderr="")

        result = run_checked_command(["echo", "test"])

        assert result == "output"
        mock_subprocess_run.assert_called_once_with(
            ["echo", "test"],
            input=None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_command_with_input(self, mock_subprocess_run):
        """Test command execution with input text."""
        mock_subprocess_run.return_value = Mock(returncode=0, stdout="output", stderr="")

        result = run_checked_command(["cat"], input_text="input data")

        assert result == "output"
        mock_subprocess_run.assert_called_once_with(
            ["cat"],
            input="input data",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_command_failure_with_stderr(self, mock_subprocess_run):
        """Test command failure with stderr message."""
        mock_subprocess_run.return_value = Mock(returncode=1, stdout="", stderr="error message")

        with pytest.raises(RuntimeError, match="Command failed.*error message"):
            run_checked_command(["false"])

    def test_command_failure_with_stdout(self, mock_subprocess_run):
        """Test command failure with stdout message (no stderr)."""
        mock_subprocess_run.return_value = Mock(returncode=1, stdout="stdout error", stderr="")

        with pytest.raises(RuntimeError, match="Command failed.*stdout error"):
            run_checked_command(["false"])

    def test_command_failure_with_no_output(self, mock_subprocess_run):
        """Test command failure with no error output."""
        mock_subprocess_run.return_value = Mock(returncode=1, stdout="", stderr="")

        with pytest.raises(RuntimeError, match="Command failed"):
            run_checked_command(["false"])


class TestRunProgressCommand:
    """Tests for run_progress_command function."""

    @patch("rpi_usb_cloner.storage.clone.command_runners.display_lines")
    @patch("rpi_usb_cloner.storage.clone.command_runners.select")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clone.command_runners.time.time")
    def test_successful_command_with_progress(self, mock_time, mock_popen, mock_select, mock_display):
        """Test successful command with progress monitoring."""
        # Mock process
        process = Mock()
        process.returncode = 0
        process.poll.side_effect = [None, None, 0]  # Running, then complete
        process.stderr.readline.side_effect = [
            "12345678 bytes transferred\n",
            "50.5% complete\n",
            "",
        ]
        mock_popen.return_value = process

        # Mock select to return ready
        mock_select.select.side_effect = [
            ([process.stderr], [], []),
            ([process.stderr], [], []),
            ([], [], []),
        ]

        # Mock time
        mock_time.side_effect = [0, 0.5, 1.0, 1.5]

        result = run_progress_command(["dd", "if=/dev/zero", "of=/dev/null"], total_bytes=100000000)

        assert result is True
        assert mock_display.call_count > 0

    @patch("rpi_usb_cloner.storage.clone.command_runners.display_lines")
    @patch("rpi_usb_cloner.storage.clone.command_runners.select")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.Popen")
    def test_command_failure(self, mock_popen, mock_select, mock_display):
        """Test command failure handling."""
        process = Mock()
        process.returncode = 1
        process.poll.return_value = 1
        process.stderr.readline.return_value = ""
        process.stderr.read.return_value = "Error: disk full"
        mock_popen.return_value = process

        mock_select.select.return_value = ([], [], [])

        result = run_progress_command(["dd", "if=/dev/zero", "of=/dev/null"])

        assert result is False
        # Check that failure message was displayed
        failure_calls = [call for call in mock_display.call_args_list if "FAILED" in str(call)]
        assert len(failure_calls) > 0

    @patch("rpi_usb_cloner.storage.clone.command_runners.display_lines")
    @patch("rpi_usb_cloner.storage.clone.command_runners.select")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clone.command_runners.time.time")
    def test_progress_parsing_with_rate(self, mock_time, mock_popen, mock_select, mock_display):
        """Test progress parsing with transfer rate."""
        process = Mock()
        process.returncode = 0
        process.poll.side_effect = [None, 0]
        process.stderr.readline.side_effect = [
            "10485760 bytes transferred, 100.0 MiB/s\n",
            "",
        ]
        mock_popen.return_value = process

        mock_select.select.side_effect = [([process.stderr], [], []), ([], [], [])]
        mock_time.side_effect = [0, 1.0, 2.0]

        result = run_progress_command(
            ["dd", "if=/dev/zero", "of=/dev/null"],
            total_bytes=100000000,
            title="TEST",
        )

        assert result is True


class TestRunCheckedWithProgress:
    """Tests for run_checked_with_progress function."""

    @patch("rpi_usb_cloner.storage.clone.command_runners.display_lines")
    @patch("rpi_usb_cloner.storage.clone.command_runners.parse_progress_from_output")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.run")
    def test_successful_command(self, mock_run, mock_parse, mock_display):
        """Test successful command with progress parsing."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="output",
            stderr="12345 bytes\n50%\n",
        )

        result = run_checked_with_progress(["dd", "if=/dev/zero"], total_bytes=100000)

        assert result.returncode == 0
        mock_parse.assert_called_once()

    @patch("rpi_usb_cloner.storage.clone.command_runners.display_lines")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.run")
    def test_command_failure(self, mock_run, mock_display):
        """Test command failure handling."""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Error: permission denied",
        )

        with pytest.raises(RuntimeError, match="permission denied"):
            run_checked_with_progress(["dd", "if=/dev/zero"])

    @patch("rpi_usb_cloner.storage.clone.command_runners.display_lines")
    @patch("rpi_usb_cloner.storage.clone.command_runners.parse_progress_from_output")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.run")
    def test_with_stdin_stdout(self, mock_run, mock_parse, mock_display):
        """Test command with stdin and stdout redirection."""
        stdin_mock = Mock()
        stdout_mock = Mock()

        mock_run.return_value = Mock(
            returncode=0,
            stdout="",
            stderr="",
        )

        run_checked_with_progress(
            ["cat"],
            stdin_source=stdin_mock,
            stdout_target=stdout_mock,
        )

        mock_run.assert_called_once()
        assert mock_run.call_args[1]["stdin"] == stdin_mock
        assert mock_run.call_args[1]["stdout"] == stdout_mock


class TestRunCheckedWithStreamingProgress:
    """Tests for run_checked_with_streaming_progress function."""

    @patch("rpi_usb_cloner.storage.clone.command_runners.display_lines")
    @patch("rpi_usb_cloner.storage.clone.command_runners.select")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clone.command_runners.time.time")
    def test_successful_command(self, mock_time, mock_popen, mock_select, mock_display):
        """Test successful command with streaming progress."""
        process = Mock()
        process.returncode = 0
        process.poll.side_effect = [None, 0]
        process.stderr.readline.side_effect = ["10485760 bytes\n", ""]
        process.stderr.read.return_value = ""
        process.stdout = None
        mock_popen.return_value = process

        mock_select.select.side_effect = [([process.stderr], [], []), ([], [], [])]
        mock_time.side_effect = [0, 1.0, 2.0]

        result = run_checked_with_streaming_progress(
            ["dd", "if=/dev/zero"],
            total_bytes=100000000,
        )

        assert result.returncode == 0

    @patch("rpi_usb_cloner.storage.clone.command_runners.select")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.Popen")
    def test_command_failure(self, mock_popen, mock_select):
        """Test command failure handling."""
        process = Mock()
        process.returncode = 1
        process.poll.return_value = 1
        # Create a proper mock stderr that can be closed
        mock_stderr = Mock()
        mock_stderr.readline.return_value = ""
        mock_stderr.read.return_value = "disk full"
        mock_stderr.close = Mock()
        process.stderr = mock_stderr
        process.stdout = None
        mock_popen.return_value = process

        mock_select.select.return_value = ([], [], [])

        with pytest.raises(RuntimeError, match="disk full"):
            run_checked_with_streaming_progress(["dd", "if=/dev/zero"])

    @patch("rpi_usb_cloner.storage.clone.command_runners.select")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clone.command_runners.time.time")
    def test_progress_callback(self, mock_time, mock_popen, mock_select):
        """Test progress callback functionality."""
        callback = Mock()

        process = Mock()
        process.returncode = 0
        process.poll.side_effect = [None, 0]
        process.stderr.readline.side_effect = ["10485760 bytes\n", ""]
        process.stderr.read.return_value = ""
        process.stdout = None
        mock_popen.return_value = process

        mock_select.select.side_effect = [([process.stderr], [], []), ([], [], [])]
        mock_time.side_effect = [0, 1.0, 2.0]

        run_checked_with_streaming_progress(
            ["dd", "if=/dev/zero"],
            total_bytes=100000000,
            progress_callback=callback,
        )

        # Callback should be called with progress updates
        assert callback.call_count > 0
        # Check that ratio is provided
        calls_with_ratio = [call for call in callback.call_args_list if call[0][1] is not None]
        assert len(calls_with_ratio) > 0

    @patch("rpi_usb_cloner.storage.clone.command_runners.select")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clone.command_runners.time.time")
    def test_ratio_computation_from_bytes(self, mock_time, mock_popen, mock_select):
        """Test ratio computation from bytes copied."""
        callback = Mock()

        process = Mock()
        process.returncode = 0
        process.poll.side_effect = [None, 0]
        process.stderr.readline.side_effect = ["50000000 bytes\n", ""]
        process.stderr.read.return_value = ""
        process.stdout = None
        mock_popen.return_value = process

        mock_select.select.side_effect = [([process.stderr], [], []), ([], [], [])]
        mock_time.side_effect = [0, 1.0, 2.0]

        run_checked_with_streaming_progress(
            ["dd", "if=/dev/zero"],
            total_bytes=100000000,
            progress_callback=callback,
        )

        # Find the call with ratio from bytes
        calls_with_ratio = [call for call in callback.call_args_list if call[0][1] is not None]
        # Ratio should be 0.5 (50MB / 100MB)
        assert any(abs(call[0][1] - 0.5) < 0.01 for call in calls_with_ratio if call[0][1])

    @patch("rpi_usb_cloner.storage.clone.command_runners.select")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clone.command_runners.time.time")
    def test_ratio_computation_from_percent(self, mock_time, mock_popen, mock_select):
        """Test ratio computation from percentage."""
        callback = Mock()

        process = Mock()
        process.returncode = 0
        process.poll.side_effect = [None, 0]
        process.stderr.readline.side_effect = ["75.5% complete\n", ""]
        process.stderr.read.return_value = ""
        process.stdout = None
        mock_popen.return_value = process

        mock_select.select.side_effect = [([process.stderr], [], []), ([], [], [])]
        mock_time.side_effect = [0, 1.0, 2.0]

        run_checked_with_streaming_progress(
            ["dd", "if=/dev/zero"],
            progress_callback=callback,
        )

        # Find the call with ratio from percentage
        calls_with_ratio = [call for call in callback.call_args_list if call[0][1] is not None]
        # Ratio should be 0.755 (75.5%)
        assert any(abs(call[0][1] - 0.755) < 0.01 for call in calls_with_ratio if call[0][1])

    @patch("rpi_usb_cloner.storage.clone.command_runners.select")
    @patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.Popen")
    @patch("rpi_usb_cloner.storage.clone.command_runners.time.time")
    def test_ratio_clamping(self, mock_time, mock_popen, mock_select):
        """Test that ratio is clamped to [0, 1] range."""
        callback = Mock()

        process = Mock()
        process.returncode = 0
        process.poll.side_effect = [None, None, 0]
        # Simulating edge cases that could produce out-of-range ratios
        process.stderr.readline.side_effect = [
            "150000000 bytes\n",  # More than total_bytes
            "-10% complete\n",  # Negative percentage
            "",
        ]
        process.stderr.read.return_value = ""
        process.stdout = None
        mock_popen.return_value = process

        mock_select.select.side_effect = [
            ([process.stderr], [], []),
            ([process.stderr], [], []),
            ([], [], []),
        ]
        mock_time.side_effect = [0, 1.0, 2.0, 3.0]

        run_checked_with_streaming_progress(
            ["dd", "if=/dev/zero"],
            total_bytes=100000000,
            progress_callback=callback,
        )

        # All ratios should be in [0, 1] range
        for call_args in callback.call_args_list:
            if call_args[0][1] is not None:
                ratio = call_args[0][1]
                assert 0.0 <= ratio <= 1.0


class TestConfigureProgressLogger:
    """Tests for progress logger configuration."""

    def test_configure_logger(self):
        """Test configuring the progress logger."""
        logger = Mock()
        configure_progress_logger(logger)

        # Use run_checked_command which uses _log_debug internally
        with patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            run_checked_command(["echo", "test"])

        # Logger should have been called
        assert logger.call_count > 0

    def test_logger_none(self):
        """Test that None logger doesn't raise errors."""
        configure_progress_logger(None)

        # Should not raise any errors
        with patch("rpi_usb_cloner.storage.clone.command_runners.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            run_checked_command(["echo", "test"])
