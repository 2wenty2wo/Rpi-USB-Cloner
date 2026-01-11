"""Tests for device erasure operations."""
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from rpi_usb_cloner.storage.clone.erase import erase_device


class TestEraseDevice:
    """Tests for erase_device function."""

    @pytest.fixture
    def mock_target_device(self):
        """Create a mock target device."""
        return {
            "name": "sdb",
            "size": 32000000000,  # 32GB
        }

    @pytest.fixture
    def setup_mocks(self):
        """Setup common mocks for erase tests."""
        with patch("rpi_usb_cloner.storage.clone.erase.shutil.which") as mock_which, \
             patch("rpi_usb_cloner.storage.clone.erase.unmount_device") as mock_unmount, \
             patch("rpi_usb_cloner.storage.clone.erase.run_checked_with_streaming_progress") as mock_run, \
             patch("rpi_usb_cloner.storage.clone.erase.display_lines") as mock_display:
            yield {
                "which": mock_which,
                "unmount": mock_unmount,
                "run": mock_run,
                "display": mock_display,
            }

    def test_erase_secure_mode(self, mock_target_device, setup_mocks):
        """Test secure erase mode using shred."""
        mocks = setup_mocks
        mocks["which"].return_value = "/usr/bin/shred"
        mocks["run"].return_value = Mock()

        result = erase_device(mock_target_device, "secure")

        assert result is True
        mocks["unmount"].assert_called_once_with(mock_target_device)
        mocks["run"].assert_called_once()
        # Verify shred command
        call_args = mocks["run"].call_args
        assert call_args[0][0][0] == "/usr/bin/shred"
        assert "-v" in call_args[0][0]
        assert "-n" in call_args[0][0]
        assert "1" in call_args[0][0]
        assert "-z" in call_args[0][0]
        assert "/dev/sdb" in call_args[0][0]

    def test_erase_secure_mode_no_shred(self, mock_target_device, setup_mocks):
        """Test secure erase fails gracefully when shred is not available."""
        mocks = setup_mocks
        mocks["which"].return_value = None

        result = erase_device(mock_target_device, "secure")

        assert result is False
        # Should display error
        error_calls = [c for c in mocks["display"].call_args_list if "ERROR" in str(c)]
        assert len(error_calls) > 0

    def test_erase_discard_mode(self, mock_target_device, setup_mocks):
        """Test discard/TRIM mode for SSDs."""
        mocks = setup_mocks
        mocks["which"].return_value = "/usr/bin/blkdiscard"
        mocks["run"].return_value = Mock()

        result = erase_device(mock_target_device, "discard")

        assert result is True
        # Verify blkdiscard command
        call_args = mocks["run"].call_args
        assert call_args[0][0][0] == "/usr/bin/blkdiscard"
        assert "/dev/sdb" in call_args[0][0]

    def test_erase_discard_mode_no_blkdiscard(self, mock_target_device, setup_mocks):
        """Test discard mode fails when blkdiscard is not available."""
        mocks = setup_mocks
        mocks["which"].return_value = None

        result = erase_device(mock_target_device, "discard")

        assert result is False

    def test_erase_zero_mode(self, mock_target_device, setup_mocks):
        """Test zero fill mode."""
        mocks = setup_mocks
        mocks["which"].return_value = "/usr/bin/dd"
        mocks["run"].return_value = Mock()

        result = erase_device(mock_target_device, "zero")

        assert result is True
        # Verify dd command
        call_args = mocks["run"].call_args
        assert call_args[0][0][0] == "/usr/bin/dd"
        assert "if=/dev/zero" in call_args[0][0]
        assert "of=/dev/sdb" in call_args[0][0]
        assert "bs=4M" in call_args[0][0]
        assert "status=progress" in call_args[0][0]

    def test_erase_zero_mode_no_dd(self, mock_target_device, setup_mocks):
        """Test zero mode fails when dd is not available."""
        mocks = setup_mocks
        mocks["which"].return_value = None

        result = erase_device(mock_target_device, "zero")

        assert result is False

    def test_erase_quick_mode(self, mock_target_device, setup_mocks):
        """Test quick erase mode (wipefs + zero start/end)."""
        mocks = setup_mocks

        def which_side_effect(cmd):
            if cmd == "wipefs":
                return "/usr/bin/wipefs"
            if cmd == "dd":
                return "/usr/bin/dd"
            return None

        mocks["which"].side_effect = which_side_effect
        mocks["run"].return_value = Mock()

        result = erase_device(mock_target_device, "quick")

        assert result is True
        # Should call run 3 times: wipefs, dd start, dd end
        assert mocks["run"].call_count == 3

        # Verify wipefs was called
        wipefs_call = mocks["run"].call_args_list[0]
        assert "wipefs" in wipefs_call[0][0][0]
        assert "-a" in wipefs_call[0][0]

        # Verify dd was called for start
        dd_start_call = mocks["run"].call_args_list[1]
        assert "dd" in dd_start_call[0][0][0]
        assert "if=/dev/zero" in dd_start_call[0][0]

    def test_erase_quick_mode_small_disk(self, setup_mocks):
        """Test quick erase on small disk (doesn't need end wipe)."""
        small_device = {
            "name": "sdc",
            "size": 10 * 1024 * 1024,  # 10MB
        }
        mocks = setup_mocks

        def which_side_effect(cmd):
            if cmd == "wipefs":
                return "/usr/bin/wipefs"
            if cmd == "dd":
                return "/usr/bin/dd"
            return None

        mocks["which"].side_effect = which_side_effect
        mocks["run"].return_value = Mock()

        with patch("rpi_usb_cloner.storage.clone.erase.app_state") as mock_state:
            mock_state.QUICK_WIPE_MIB = 100  # 100MB wipe size

            result = erase_device(small_device, "quick")

        assert result is True
        # Should only call run 2 times: wipefs, dd start (no end needed)
        assert mocks["run"].call_count == 2

    def test_erase_quick_mode_no_wipefs(self, mock_target_device, setup_mocks):
        """Test quick mode fails when wipefs is not available."""
        mocks = setup_mocks
        mocks["which"].return_value = None

        result = erase_device(mock_target_device, "quick")

        assert result is False

    def test_erase_unknown_mode(self, mock_target_device, setup_mocks):
        """Test unknown erase mode."""
        mocks = setup_mocks

        result = erase_device(mock_target_device, "unknown_mode")

        assert result is False
        # Should display error
        error_calls = [c for c in mocks["display"].call_args_list if "ERROR" in str(c) or "unknown" in str(c)]
        assert len(error_calls) > 0

    def test_erase_none_mode_defaults_to_quick(self, mock_target_device, setup_mocks):
        """Test None mode defaults to quick erase."""
        mocks = setup_mocks

        def which_side_effect(cmd):
            if cmd == "wipefs":
                return "/usr/bin/wipefs"
            if cmd == "dd":
                return "/usr/bin/dd"
            return None

        mocks["which"].side_effect = which_side_effect
        mocks["run"].return_value = Mock()

        result = erase_device(mock_target_device, None)

        assert result is True
        # Should behave like quick mode
        assert mocks["run"].call_count == 3

    def test_erase_empty_mode_defaults_to_quick(self, mock_target_device, setup_mocks):
        """Test empty string mode defaults to quick erase."""
        mocks = setup_mocks

        def which_side_effect(cmd):
            if cmd == "wipefs":
                return "/usr/bin/wipefs"
            if cmd == "dd":
                return "/usr/bin/dd"
            return None

        mocks["which"].side_effect = which_side_effect
        mocks["run"].return_value = Mock()

        result = erase_device(mock_target_device, "")

        assert result is True

    def test_erase_with_progress_callback(self, mock_target_device, setup_mocks):
        """Test erase with custom progress callback."""
        mocks = setup_mocks
        mocks["which"].return_value = "/usr/bin/blkdiscard"
        mocks["run"].return_value = Mock()

        callback = Mock()
        result = erase_device(mock_target_device, "discard", progress_callback=callback)

        assert result is True
        # Verify callback was passed to run command
        call_args = mocks["run"].call_args
        assert call_args[1]["progress_callback"] == callback

    def test_erase_command_failure(self, mock_target_device, setup_mocks):
        """Test handling of command execution failure."""
        mocks = setup_mocks
        mocks["which"].return_value = "/usr/bin/shred"
        mocks["run"].side_effect = Exception("Command failed")

        result = erase_device(mock_target_device, "secure")

        assert result is False

    def test_erase_case_insensitive_mode(self, mock_target_device, setup_mocks):
        """Test that mode is case-insensitive."""
        mocks = setup_mocks
        mocks["which"].return_value = "/usr/bin/blkdiscard"
        mocks["run"].return_value = Mock()

        # Test uppercase
        result = erase_device(mock_target_device, "DISCARD")
        assert result is True

        mocks["run"].reset_mock()

        # Test mixed case
        result = erase_device(mock_target_device, "DiScArD")
        assert result is True

    def test_erase_unmounts_device(self, mock_target_device, setup_mocks):
        """Test that device is unmounted before erasing."""
        mocks = setup_mocks
        mocks["which"].return_value = "/usr/bin/blkdiscard"
        mocks["run"].return_value = Mock()

        erase_device(mock_target_device, "discard")

        # Unmount should be called before any operations
        mocks["unmount"].assert_called_once_with(mock_target_device)

    def test_erase_quick_mode_wipefs_failure(self, mock_target_device, setup_mocks):
        """Test quick mode fails if wipefs fails."""
        mocks = setup_mocks

        def which_side_effect(cmd):
            if cmd == "wipefs":
                return "/usr/bin/wipefs"
            if cmd == "dd":
                return "/usr/bin/dd"
            return None

        mocks["which"].side_effect = which_side_effect

        # Make wipefs fail
        def run_side_effect(*args, **kwargs):
            if "wipefs" in args[0][0]:
                raise Exception("wipefs failed")
            return Mock()

        mocks["run"].side_effect = run_side_effect

        result = erase_device(mock_target_device, "quick")

        assert result is False
        # Should only call wipefs, not dd
        assert mocks["run"].call_count == 1

    @patch("rpi_usb_cloner.storage.clone.erase.app_state")
    def test_erase_quick_mode_wipe_size(self, mock_state, mock_target_device, setup_mocks):
        """Test quick mode respects QUICK_WIPE_MIB setting."""
        mock_state.QUICK_WIPE_MIB = 50  # 50MB
        mocks = setup_mocks

        def which_side_effect(cmd):
            if cmd == "wipefs":
                return "/usr/bin/wipefs"
            if cmd == "dd":
                return "/usr/bin/dd"
            return None

        mocks["which"].side_effect = which_side_effect
        mocks["run"].return_value = Mock()

        erase_device(mock_target_device, "quick")

        # Check dd commands have count=50
        dd_calls = [c for c in mocks["run"].call_args_list if "dd" in c[0][0][0]]
        for dd_call in dd_calls:
            assert "count=50" in dd_call[0][0]
