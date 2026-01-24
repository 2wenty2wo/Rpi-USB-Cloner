"""
Tests for rpi_usb_cloner.config.settings module.

This test suite covers:
- Settings loading and saving
- Default settings initialization
- Settings persistence to JSON file
- Type conversion helpers (get_bool, set_bool)
- Error handling for corrupted settings files
- Environment variable override for settings path
"""

import json
from pathlib import Path

from rpi_usb_cloner.config import settings


class TestLoadSettings:
    """Tests for load_settings() function."""

    def test_load_defaults_when_no_file(self, tmp_path, monkeypatch):
        """Test that default settings are loaded when file doesn't exist."""
        settings_file = tmp_path / "nonexistent" / "settings.json"
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", settings_file
        )

        # Reset and reload
        settings.settings_store.values = {}
        settings.load_settings()

        # Should have default values
        assert settings.settings_store.values["screensaver_enabled"] is False
        assert "restore_partition_mode" in settings.settings_store.values

    def test_load_from_existing_file(
        self, temp_settings_file, sample_settings_data, monkeypatch
    ):
        """Test loading settings from existing file."""
        # Write sample settings
        temp_settings_file.write_text(json.dumps(sample_settings_data))
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        # Reset and reload
        settings.settings_store.values = {}
        settings.load_settings()

        # Should have loaded values
        assert settings.settings_store.values["verify_hash"] is True
        assert settings.settings_store.values["clone_mode"] == "smart"

    def test_load_merges_with_defaults(self, temp_settings_file, monkeypatch):
        """Test that loaded settings merge with defaults."""
        # Write partial settings (missing some defaults)
        partial_settings = {"verify_hash": True}
        temp_settings_file.write_text(json.dumps(partial_settings))
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        settings.settings_store.values = {}
        settings.load_settings()

        # Should have both loaded and default values
        assert settings.settings_store.values["verify_hash"] is True
        assert "screensaver_enabled" in settings.settings_store.values

    def test_load_handles_corrupted_json(self, temp_settings_file, monkeypatch):
        """Test handling of corrupted JSON file."""
        # Write invalid JSON
        temp_settings_file.write_text("{invalid json")
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        settings.settings_store.values = {}
        settings.load_settings()

        # Should fall back to defaults without crashing
        assert "screensaver_enabled" in settings.settings_store.values

    def test_load_handles_non_dict_json(self, temp_settings_file, monkeypatch):
        """Test handling of JSON that's not a dict."""
        # Write valid JSON but not a dict
        temp_settings_file.write_text("[]")
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        settings.settings_store.values = {}
        settings.load_settings()

        # Should ignore the array and use defaults
        assert "screensaver_enabled" in settings.settings_store.values

    def test_load_handles_read_permission_error(self, temp_settings_file, monkeypatch):
        """Test handling of file read permission errors."""
        temp_settings_file.write_text("{}")
        temp_settings_file.chmod(0o000)  # No read permission
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        settings.settings_store.values = {}
        settings.load_settings()

        # Should fall back to defaults
        assert "screensaver_enabled" in settings.settings_store.values

        # Cleanup
        temp_settings_file.chmod(0o644)


class TestSaveSettings:
    """Tests for save_settings() function."""

    def test_save_creates_directory(self, tmp_path, monkeypatch):
        """Test that save_settings creates parent directory if needed."""
        settings_file = tmp_path / "new_dir" / "settings.json"
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", settings_file
        )

        settings.settings_store.values = {"test": "value"}
        settings.save_settings()

        assert settings_file.exists()
        assert settings_file.parent.exists()

    def test_save_writes_json(self, temp_settings_file, monkeypatch):
        """Test that settings are written as JSON."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        settings.settings_store.values = {"key1": "value1", "key2": 123}
        settings.save_settings()

        # Read back and verify
        data = json.loads(temp_settings_file.read_text())
        assert data["key1"] == "value1"
        assert data["key2"] == 123

    def test_save_formats_json_nicely(self, temp_settings_file, monkeypatch):
        """Test that JSON is formatted with indentation and sorted keys."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        settings.settings_store.values = {"zebra": 1, "apple": 2}
        settings.save_settings()

        content = temp_settings_file.read_text()

        # Check for indentation
        assert "  " in content  # 2-space indent

        # Check for sorted keys (apple before zebra)
        apple_pos = content.index("apple")
        zebra_pos = content.index("zebra")
        assert apple_pos < zebra_pos

    def test_save_overwrites_existing(self, temp_settings_file, monkeypatch):
        """Test that save overwrites existing file."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        # Write initial data
        temp_settings_file.write_text(json.dumps({"old": "data"}))

        # Save new data
        settings.settings_store.values = {"new": "data"}
        settings.save_settings()

        # Verify overwrite
        data = json.loads(temp_settings_file.read_text())
        assert "new" in data
        assert "old" not in data


class TestGetSetting:
    """Tests for get_setting() function."""

    def test_get_existing_setting(self):
        """Test retrieving an existing setting."""
        settings.settings_store.values = {"test_key": "test_value"}

        result = settings.get_setting("test_key")

        assert result == "test_value"

    def test_get_nonexistent_setting_returns_none(self):
        """Test retrieving non-existent setting returns None."""
        settings.settings_store.values = {}

        result = settings.get_setting("nonexistent")

        assert result is None

    def test_get_with_default(self):
        """Test retrieving non-existent setting with default."""
        settings.settings_store.values = {}

        result = settings.get_setting("nonexistent", default="default_value")

        assert result == "default_value"

    def test_get_returns_various_types(self):
        """Test that get_setting preserves data types."""
        settings.settings_store.values = {
            "string": "value",
            "int": 42,
            "bool": True,
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
        }

        assert settings.get_setting("string") == "value"
        assert settings.get_setting("int") == 42
        assert settings.get_setting("bool") is True
        assert settings.get_setting("list") == [1, 2, 3]
        assert settings.get_setting("dict") == {"nested": "value"}


class TestSetSetting:
    """Tests for set_setting() function."""

    def test_set_new_setting(self, temp_settings_file, monkeypatch):
        """Test setting a new value."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )
        settings.settings_store.values = {}

        settings.set_setting("new_key", "new_value")

        assert settings.settings_store.values["new_key"] == "new_value"

    def test_set_overwrites_existing(self, temp_settings_file, monkeypatch):
        """Test overwriting an existing value."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )
        settings.settings_store.values = {"existing": "old"}

        settings.set_setting("existing", "new")

        assert settings.settings_store.values["existing"] == "new"

    def test_set_automatically_saves(self, temp_settings_file, monkeypatch):
        """Test that set_setting automatically saves to disk."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )
        settings.settings_store.values = {}

        settings.set_setting("auto_save_test", "value")

        # Verify it was written to disk
        data = json.loads(temp_settings_file.read_text())
        assert data["auto_save_test"] == "value"

    def test_set_accepts_various_types(self, temp_settings_file, monkeypatch):
        """Test that set_setting accepts various data types."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        settings.set_setting("string", "value")
        settings.set_setting("int", 42)
        settings.set_setting("bool", False)
        settings.set_setting("list", [1, 2])
        settings.set_setting("dict", {"key": "val"})

        assert settings.settings_store.values["string"] == "value"
        assert settings.settings_store.values["int"] == 42
        assert settings.settings_store.values["bool"] is False


class TestGetBool:
    """Tests for get_bool() helper function."""

    def test_get_true_bool(self):
        """Test getting a true boolean value."""
        settings.settings_store.values = {"test": True}

        result = settings.get_bool("test")

        assert result is True

    def test_get_false_bool(self):
        """Test getting a false boolean value."""
        settings.settings_store.values = {"test": False}

        result = settings.get_bool("test")

        assert result is False

    def test_get_nonexistent_returns_default_false(self):
        """Test that non-existent key returns False by default."""
        settings.settings_store.values = {}

        result = settings.get_bool("nonexistent")

        assert result is False

    def test_get_with_custom_default(self):
        """Test getting with custom default."""
        settings.settings_store.values = {}

        result = settings.get_bool("nonexistent", default=True)

        assert result is True

    def test_converts_truthy_values(self):
        """Test that truthy values are converted to True."""
        settings.settings_store.values = {
            "int": 1,
            "string": "yes",
            "list": [1],
        }

        assert settings.get_bool("int") is True
        assert settings.get_bool("string") is True
        assert settings.get_bool("list") is True

    def test_converts_falsy_values(self):
        """Test that falsy values are converted to False."""
        settings.settings_store.values = {
            "zero": 0,
            "empty_string": "",
            "none": None,
            "empty_list": [],
        }

        assert settings.get_bool("zero") is False
        assert settings.get_bool("empty_string") is False
        assert settings.get_bool("none") is False
        assert settings.get_bool("empty_list") is False


class TestSetBool:
    """Tests for set_bool() helper function."""

    def test_set_true(self, temp_settings_file, monkeypatch):
        """Test setting a boolean to True."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )
        settings.settings_store.values = {}

        settings.set_bool("test", True)

        assert settings.settings_store.values["test"] is True

    def test_set_false(self, temp_settings_file, monkeypatch):
        """Test setting a boolean to False."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )
        settings.settings_store.values = {}

        settings.set_bool("test", False)

        assert settings.settings_store.values["test"] is False

    def test_converts_truthy_to_true(self, temp_settings_file, monkeypatch):
        """Test that truthy values are converted to True."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        settings.set_bool("test", 1)
        assert settings.settings_store.values["test"] is True

        settings.set_bool("test", "yes")
        assert settings.settings_store.values["test"] is True

    def test_converts_falsy_to_false(self, temp_settings_file, monkeypatch):
        """Test that falsy values are converted to False."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        settings.set_bool("test", 0)
        assert settings.settings_store.values["test"] is False

        settings.set_bool("test", "")
        assert settings.settings_store.values["test"] is False

    def test_automatically_saves(self, temp_settings_file, monkeypatch):
        """Test that set_bool automatically saves to disk."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )
        settings.settings_store.values = {}

        settings.set_bool("auto_save", True)

        # Verify it was written to disk
        data = json.loads(temp_settings_file.read_text())
        assert data["auto_save"] is True


class TestDefaultSettings:
    """Tests for DEFAULT_SETTINGS constant."""

    def test_has_required_keys(self):
        """Test that DEFAULT_SETTINGS contains expected keys."""
        assert "screensaver_enabled" in settings.DEFAULT_SETTINGS
        assert "screensaver_mode" in settings.DEFAULT_SETTINGS
        assert "restore_partition_mode" in settings.DEFAULT_SETTINGS

    def test_has_correct_types(self):
        """Test that default values have correct types."""
        assert isinstance(settings.DEFAULT_SETTINGS["screensaver_enabled"], bool)
        assert isinstance(settings.DEFAULT_SETTINGS["screensaver_mode"], str)


class TestSettingsPath:
    """Tests for SETTINGS_PATH configuration."""

    def test_default_path(self, monkeypatch):
        """Test default settings path."""
        # Remove env var if present
        monkeypatch.delenv("RPI_USB_CLONER_SETTINGS_PATH", raising=False)

        # Reimport to get fresh path
        import importlib

        importlib.reload(settings)

        expected = Path.home() / ".config" / "rpi-usb-cloner" / "settings.json"
        assert expected == settings.SETTINGS_PATH

    def test_env_var_override(self, monkeypatch, tmp_path):
        """Test that environment variable can override settings path."""
        custom_path = tmp_path / "custom_settings.json"
        monkeypatch.setenv("RPI_USB_CLONER_SETTINGS_PATH", str(custom_path))

        # Reimport to pick up env var
        import importlib

        importlib.reload(settings)

        assert custom_path == settings.SETTINGS_PATH


class TestSettingsStore:
    """Tests for SettingsStore dataclass."""

    def test_default_empty_values(self):
        """Test that new SettingsStore has empty values dict."""
        store = settings.SettingsStore()
        assert store.values == {}

    def test_can_store_values(self):
        """Test that SettingsStore can hold values."""
        store = settings.SettingsStore()
        store.values["key"] = "value"
        assert store.values["key"] == "value"


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_save_and_load_roundtrip(self, temp_settings_file, monkeypatch):
        """Test that settings can be saved and loaded back correctly."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        # Set some values
        test_data = {
            "string_val": "test",
            "int_val": 42,
            "bool_val": True,
            "nested": {"key": "value"},
        }

        settings.settings_store.values = test_data.copy()
        settings.save_settings()

        # Clear and reload
        settings.settings_store.values = {}
        settings.load_settings()

        # Verify all values survived the round trip
        for key, value in test_data.items():
            assert settings.settings_store.values[key] == value

    def test_partial_update_preserves_defaults(self, temp_settings_file, monkeypatch):
        """Test that updating one setting preserves others."""
        monkeypatch.setattr(
            "rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file
        )

        # Load defaults
        settings.load_settings()
        initial_screensaver = settings.get_setting("screensaver_enabled")

        # Update one setting
        settings.set_setting("custom_setting", "custom_value")

        # Reload
        settings.load_settings()

        # Verify both exist
        assert settings.get_setting("screensaver_enabled") == initial_screensaver
        assert settings.get_setting("custom_setting") == "custom_value"
