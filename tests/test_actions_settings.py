"""Tests for settings action handlers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rpi_usb_cloner.config import settings


# =============================================================================
# System Utils Tests (Pure logic, no UI dependencies)
# =============================================================================


def test_validate_command_args_rejects_empty_list():
    """Test command validation rejects empty argument list."""
    from rpi_usb_cloner.actions.settings.system_utils import validate_command_args
    with pytest.raises(ValueError, match="Command args must be"):
        validate_command_args([])


def test_validate_command_args_rejects_non_string_args():
    """Test command validation rejects non-string arguments."""
    from rpi_usb_cloner.actions.settings.system_utils import validate_command_args
    with pytest.raises(ValueError, match="Command args must be"):
        validate_command_args(["git", 123, "pull"])


def test_validate_command_args_accepts_valid_args():
    """Test command validation accepts valid argument list."""
    from rpi_usb_cloner.actions.settings.system_utils import validate_command_args
    # Should not raise
    validate_command_args(["git", "status"])


def test_format_command_output_formats_stdout_stderr():
    """Test formatting command output for display."""
    from rpi_usb_cloner.actions.settings.system_utils import format_command_output
    stdout = "Line 1\nLine 2"
    stderr = "Error 1"
    lines = format_command_output(stdout, stderr)
    assert "Line 1" in lines
    assert "Line 2" in lines
    assert "Error 1" in lines


def test_format_command_output_handles_empty_output():
    """Test formatting empty command output."""
    from rpi_usb_cloner.actions.settings.system_utils import format_command_output
    lines = format_command_output("", "")
    assert lines == ["No output"]


def test_is_git_repo_detects_git_directory(tmp_path):
    """Test git repo detection."""
    from rpi_usb_cloner.actions.settings.system_utils import is_git_repo
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    assert is_git_repo(tmp_path) is True


def test_is_git_repo_rejects_non_git_directory(tmp_path):
    """Test non-git directory detection."""
    from rpi_usb_cloner.actions.settings.system_utils import is_git_repo
    assert is_git_repo(tmp_path) is False


def test_is_dubious_ownership_error_detects_error():
    """Test detection of git dubious ownership error."""
    from rpi_usb_cloner.actions.settings.system_utils import is_dubious_ownership_error
    stderr = "fatal: detected dubious ownership in repository"
    assert is_dubious_ownership_error(stderr) is True


def test_is_dubious_ownership_error_rejects_other_errors():
    """Test that non-dubious errors return False."""
    from rpi_usb_cloner.actions.settings.system_utils import is_dubious_ownership_error
    stderr = "fatal: unable to access"
    assert is_dubious_ownership_error(stderr) is False


def test_parse_git_progress_ratio_parses_receiving_objects():
    """Test parsing git progress for receiving objects."""
    from rpi_usb_cloner.actions.settings.system_utils import parse_git_progress_ratio
    line = "Receiving objects:  50% (100/200)"
    ratio = parse_git_progress_ratio(line)
    # Stage 0 (receiving) at 50% = (0 + 0.5) / 3 = 0.166...
    assert ratio is not None
    assert 0.16 <= ratio <= 0.17


def test_parse_git_progress_ratio_parses_resolving_deltas():
    """Test parsing git progress for resolving deltas."""
    from rpi_usb_cloner.actions.settings.system_utils import parse_git_progress_ratio
    line = "Resolving deltas:  75% (150/200)"
    ratio = parse_git_progress_ratio(line)
    # Stage 1 (resolving) at 75% = (1 + 0.75) / 3 = 0.583...
    assert ratio is not None
    assert 0.58 <= ratio <= 0.59


def test_parse_git_progress_ratio_returns_none_for_invalid_line():
    """Test parsing invalid git progress line returns None."""
    from rpi_usb_cloner.actions.settings.system_utils import parse_git_progress_ratio
    line = "Some other output"
    ratio = parse_git_progress_ratio(line)
    assert ratio is None


def test_get_app_version_from_git(monkeypatch):
    """Test getting app version from git."""
    from rpi_usb_cloner.actions.settings import system_utils
    # Mock the git command to return a version
    mock_result = subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout="v1.0.0"
    )
    monkeypatch.setattr(system_utils, "run_command", lambda *args, **kwargs: mock_result)
    
    version = system_utils.get_app_version()
    assert version == "v1.0.0"


def test_get_app_version_returns_unknown_when_no_version(monkeypatch):
    """Test getting app version returns 'unknown' when all methods fail."""
    from rpi_usb_cloner.actions.settings import system_utils
    # Mock all version methods to fail
    mock_fail = subprocess.CompletedProcess(
        args=["git"], returncode=1, stdout=""
    )
    monkeypatch.setattr(system_utils, "run_command", lambda *args, **kwargs: mock_fail)
    
    version = system_utils.get_app_version()
    assert version == "unknown"


# =============================================================================
# Update Manager Helper Tests (Pure logic)
# =============================================================================


def test_extract_error_hint_extracts_from_stderr():
    """Test extracting error hint from stderr output."""
    from rpi_usb_cloner.actions.settings.update_manager import _extract_error_hint
    stderr = "fatal: unable to access 'https://github.com/...': Could not resolve host"
    hint = _extract_error_hint(stderr)
    assert "unable to access" in hint.lower()


def test_extract_error_hint_handles_empty_stderr():
    """Test extracting error hint with empty stderr falls back to empty string."""
    from rpi_usb_cloner.actions.settings.update_manager import _extract_error_hint
    hint = _extract_error_hint("")
    assert hint == ""


def test_extract_error_hint_strips_error_prefixes():
    """Test that error prefixes are stripped from hint."""
    from rpi_usb_cloner.actions.settings.update_manager import _extract_error_hint
    stderr = "Error: Something went wrong"
    hint = _extract_error_hint(stderr)
    assert not hint.startswith("Error:")
    assert "Something went wrong" in hint


def test_truncate_oled_line_truncates_long_text():
    """Test long lines are truncated for OLED display."""
    from rpi_usb_cloner.actions.settings.update_manager import _truncate_oled_line
    long_text = "A" * 50
    truncated = _truncate_oled_line(long_text, max_length=21)
    assert len(truncated) <= 21
    assert truncated.endswith("…")


def test_truncate_oled_line_keeps_short_text():
    """Test short lines are not truncated."""
    from rpi_usb_cloner.actions.settings.update_manager import _truncate_oled_line
    short_text = "Short text"
    result = _truncate_oled_line(short_text, max_length=21)
    assert result == short_text


# =============================================================================
# System Power Helper Tests (Pure logic)
# =============================================================================


def test_build_power_action_prompt_formats_correctly():
    """Test power action prompt formatting."""
    from rpi_usb_cloner.actions.settings.system_power import build_power_action_prompt
    prompt = build_power_action_prompt("RESTART SYSTEM")
    assert "restart system" in prompt.lower()
    assert "are you sure" in prompt.lower()


def test_confirm_power_action_uses_prompt_builder():
    """Test confirm_power_action uses the prompt builder."""
    from rpi_usb_cloner.actions.settings.system_power import confirm_power_action
    confirm_callback = Mock(return_value=True)
    result = confirm_power_action(
        "POWER", "REBOOT", confirm_callback=confirm_callback
    )
    assert result is True
    confirm_callback.assert_called_once()
    call_args = confirm_callback.call_args[0]
    assert call_args[0] == "POWER"
    assert "reboot" in call_args[1].lower()


# =============================================================================
# UI Actions Tests (Pure validation logic)
# =============================================================================


def test_ui_settings_persist_to_config(monkeypatch, temp_settings_file):
    """UI settings should persist to the settings config file."""
    from rpi_usb_cloner.actions.settings.ui_actions import (
        apply_restore_partition_mode,
        apply_transition_settings,
    )
    monkeypatch.setattr(settings, "SETTINGS_PATH", temp_settings_file)
    settings.settings_store.values = {}
    settings.load_settings()

    apply_restore_partition_mode("k1")
    apply_transition_settings(4, 0.01)

    data = json.loads(temp_settings_file.read_text())
    assert data["restore_partition_mode"] == "k1"
    assert data["transition_frame_count"] == 4
    assert data["transition_frame_delay"] == 0.01


@pytest.mark.parametrize("mode", ["k0", "k", "k1", "k2"])
def test_valid_restore_partition_modes_accepted(mode):
    """All valid restore partition modes should be accepted."""
    from rpi_usb_cloner.actions.settings.ui_actions import validate_restore_partition_mode
    result = validate_restore_partition_mode(mode)
    assert result == mode


def test_invalid_restore_partition_mode_rejected():
    """Invalid restore partition inputs should raise clear errors."""
    from rpi_usb_cloner.actions.settings.ui_actions import validate_restore_partition_mode
    with pytest.raises(ValueError, match="Invalid restore partition mode"):
        validate_restore_partition_mode("invalid")


@pytest.mark.parametrize("frames,delay", [(2, 0.0), (3, 0.005), (4, 0.01)])
def test_valid_transition_settings_accepted(frames, delay):
    """Valid transition settings should be accepted."""
    from rpi_usb_cloner.actions.settings.ui_actions import validate_transition_settings
    # Should not raise
    validate_transition_settings(frames, delay)


def test_invalid_transition_settings_rejected():
    """Invalid transition inputs should raise clear errors."""
    from rpi_usb_cloner.actions.settings.ui_actions import validate_transition_settings
    with pytest.raises(ValueError, match="Invalid transition settings"):
        validate_transition_settings(99, 0.2)


# =============================================================================
# Original Integration Tests (kept for compatibility)
# =============================================================================


def test_updates_require_confirmation(monkeypatch):
    """Ensure update flow stops when confirmation is declined."""
    from rpi_usb_cloner.actions.settings import update_manager
    monkeypatch.setattr(update_manager, "is_git_repo", lambda _: True)
    monkeypatch.setattr(update_manager, "has_dirty_working_tree", lambda _: False)
    confirm_action = Mock(return_value=False)
    monkeypatch.setattr(update_manager, "confirm_action", confirm_action)
    run_git_pull = Mock()
    monkeypatch.setattr(update_manager, "run_git_pull", run_git_pull)
    monkeypatch.setattr(update_manager.screens, "wait_for_paginated_input", Mock())

    update_manager.run_update_flow("UPDATE")

    confirm_action.assert_called_once()
    run_git_pull.assert_not_called()


def test_restart_requires_confirmation(monkeypatch):
    """Restart should not execute without confirmation."""
    from rpi_usb_cloner.actions.settings import system_power
    monkeypatch.setattr(
        system_power, "confirm_power_action", lambda *args, **kwargs: False
    )
    reboot_mock = Mock()
    monkeypatch.setattr(system_power, "reboot_system", reboot_mock)

    system_power.restart_system()

    reboot_mock.assert_not_called()


def test_shutdown_requires_confirmation(monkeypatch):
    """Shutdown should not execute without confirmation."""
    from rpi_usb_cloner.actions.settings import system_power
    monkeypatch.setattr(
        system_power, "confirm_power_action", lambda *args, **kwargs: False
    )
    poweroff_mock = Mock()
    monkeypatch.setattr(system_power, "poweroff_system", poweroff_mock)

    system_power.shutdown_system()

    poweroff_mock.assert_not_called()
