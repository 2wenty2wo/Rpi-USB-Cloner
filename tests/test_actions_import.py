"""
Test that action modules can be imported (verifies no circular imports).

This test is critical - it ensures the circular import issue is resolved.
"""



class TestActionsImport:
    """Test that all actions modules can be imported without circular import errors."""

    def test_can_import_drive_actions(self):
        """Test that drive_actions module can be imported."""
        from rpi_usb_cloner.actions import drive_actions

        assert drive_actions is not None
        assert hasattr(drive_actions, "copy_drive")
        assert hasattr(drive_actions, "erase_drive")
        assert hasattr(drive_actions, "format_drive")
        assert hasattr(drive_actions, "unmount_drive")

    def test_can_import_image_actions(self):
        """Test that image_actions module can be imported."""
        from rpi_usb_cloner.actions import image_actions

        assert image_actions is not None
        assert hasattr(image_actions, "backup_image")
        assert hasattr(image_actions, "write_image")

    def test_can_import_settings_actions(self):
        """Test that settings actions can be imported."""
        from rpi_usb_cloner.actions.settings import (
            system_power,
            system_utils,
            ui_actions,
            update_manager,
        )

        assert system_power is not None
        assert system_utils is not None
        assert update_manager is not None
        assert ui_actions is not None

    def test_ui_constants_available(self):
        """Test that UI constants module provides expected constants."""
        from rpi_usb_cloner.ui import constants

        assert hasattr(constants, "BUTTON_POLL_DELAY")
        assert hasattr(constants, "INITIAL_REPEAT_DELAY")
        assert hasattr(constants, "REPEAT_INTERVAL")
        assert hasattr(constants, "DEFAULT_SCROLL_CYCLE_SECONDS")
        assert hasattr(constants, "DEFAULT_SCROLL_REFRESH_INTERVAL")

        # Verify values are reasonable
        assert 0 < constants.BUTTON_POLL_DELAY < 1
        assert 0 < constants.INITIAL_REPEAT_DELAY < 1
        assert 0 < constants.REPEAT_INTERVAL < 1

    def test_ui_screens_can_import_constants(self):
        """Test that UI screens can import from constants without circular import."""
        from rpi_usb_cloner.ui.screens import confirmation, info, status

        assert status is not None
        assert info is not None
        assert confirmation is not None
