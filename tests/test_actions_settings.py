"""Tests for settings action handlers."""

from __future__ import annotations

import importlib
import json
import sys
import types
from unittest.mock import Mock

import pytest

from rpi_usb_cloner.config import settings


def _stub_ui_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    modules = [
        "rpi_usb_cloner.ui.display",
        "rpi_usb_cloner.ui.keyboard",
        "rpi_usb_cloner.ui.menus",
        "rpi_usb_cloner.ui.screens",
        "rpi_usb_cloner.ui.screensaver",
        "rpi_usb_cloner.web.server",
    ]
    for name in modules:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))

    menu_module = types.ModuleType("rpi_usb_cloner.menu")
    menu_module.__path__ = []
    monkeypatch.setitem(sys.modules, "rpi_usb_cloner.menu", menu_module)

    menu_model = types.ModuleType("rpi_usb_cloner.menu.model")
    menu_model.get_screen_icon = lambda _screen_id: None
    monkeypatch.setitem(sys.modules, "rpi_usb_cloner.menu.model", menu_model)


def _import_settings_modules(monkeypatch: pytest.MonkeyPatch):
    _stub_ui_modules(monkeypatch)
    system_power = importlib.import_module(
        "rpi_usb_cloner.actions.settings.system_power"
    )
    ui_actions = importlib.import_module("rpi_usb_cloner.actions.settings.ui_actions")
    update_manager = importlib.import_module(
        "rpi_usb_cloner.actions.settings.update_manager"
    )
    return system_power, ui_actions, update_manager


def test_updates_require_confirmation(monkeypatch):
    """Ensure update flow stops when confirmation is declined."""
    _, _, update_manager = _import_settings_modules(monkeypatch)
    monkeypatch.setattr(update_manager, "is_git_repo", lambda _: True)
    monkeypatch.setattr(update_manager, "has_dirty_working_tree", lambda _: False)
    confirm_action = Mock(return_value=False)
    monkeypatch.setattr(update_manager, "confirm_action", confirm_action)
    run_git_pull = Mock()
    monkeypatch.setattr(update_manager, "run_git_pull", run_git_pull)

    update_manager.run_update_flow("UPDATE")

    confirm_action.assert_called_once()
    run_git_pull.assert_not_called()


def test_restart_requires_confirmation(monkeypatch):
    """Restart should not execute without confirmation."""
    system_power, _, _ = _import_settings_modules(monkeypatch)
    monkeypatch.setattr(
        system_power, "confirm_power_action", lambda *args, **kwargs: False
    )
    reboot_mock = Mock()
    monkeypatch.setattr(system_power, "reboot_system", reboot_mock)

    system_power.restart_system()

    reboot_mock.assert_not_called()


def test_shutdown_requires_confirmation(monkeypatch):
    """Shutdown should not execute without confirmation."""
    system_power, _, _ = _import_settings_modules(monkeypatch)
    monkeypatch.setattr(
        system_power, "confirm_power_action", lambda *args, **kwargs: False
    )
    poweroff_mock = Mock()
    monkeypatch.setattr(system_power, "poweroff_system", poweroff_mock)

    system_power.shutdown_system()

    poweroff_mock.assert_not_called()


def test_ui_settings_persist_to_config(monkeypatch, temp_settings_file):
    """UI settings should persist to the settings config file."""
    _, ui_actions, _ = _import_settings_modules(monkeypatch)
    monkeypatch.setattr(settings, "SETTINGS_PATH", temp_settings_file)
    settings.settings_store.values = {}
    settings.load_settings()

    ui_actions.apply_restore_partition_mode("k1")
    ui_actions.apply_transition_settings(4, 0.01)

    data = json.loads(temp_settings_file.read_text())
    assert data["restore_partition_mode"] == "k1"
    assert data["transition_frame_count"] == 4
    assert data["transition_frame_delay"] == 0.01


def test_invalid_restore_partition_mode_rejected(monkeypatch):
    """Invalid restore partition inputs should raise clear errors."""
    _, ui_actions, _ = _import_settings_modules(monkeypatch)
    with pytest.raises(ValueError, match="Invalid restore partition mode"):
        ui_actions.validate_restore_partition_mode("invalid")


def test_invalid_transition_settings_rejected(monkeypatch):
    """Invalid transition inputs should raise clear errors."""
    _, ui_actions, _ = _import_settings_modules(monkeypatch)
    with pytest.raises(ValueError, match="Invalid transition settings"):
        ui_actions.validate_transition_settings(99, 0.2)
