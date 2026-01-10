"""Unit tests for mount.py security fixes.

Tests verify that command injection vulnerabilities have been fixed
and that input validation is working correctly.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from rpi_usb_cloner.storage import mount


class TestGetPartitionSecurity:
    """Test get_partition() input validation and security."""

    def test_rejects_non_dev_path(self):
        """Ensure get_partition rejects paths not starting with /dev/"""
        with pytest.raises(ValueError, match="Invalid device path"):
            mount.get_partition("/etc/passwd")

    def test_rejects_command_injection_semicolon(self):
        """Ensure get_partition rejects semicolon (command chaining)"""
        with pytest.raises(ValueError, match="invalid characters"):
            mount.get_partition("/dev/sda; rm -rf /")

    def test_rejects_command_injection_ampersand(self):
        """Ensure get_partition rejects ampersand (background commands)"""
        with pytest.raises(ValueError, match="invalid characters"):
            mount.get_partition("/dev/sda && malicious")

    def test_rejects_command_injection_pipe(self):
        """Ensure get_partition rejects pipe (command piping)"""
        with pytest.raises(ValueError, match="invalid characters"):
            mount.get_partition("/dev/sda | cat /etc/shadow")

    def test_rejects_command_injection_dollar(self):
        """Ensure get_partition rejects dollar sign (variable expansion)"""
        with pytest.raises(ValueError, match="invalid characters"):
            mount.get_partition("/dev/sda$malicious")

    def test_rejects_command_injection_backtick(self):
        """Ensure get_partition rejects backticks (command substitution)"""
        with pytest.raises(ValueError, match="invalid characters"):
            mount.get_partition("/dev/sda`whoami`")

    def test_rejects_newline_characters(self):
        """Ensure get_partition rejects newline characters"""
        with pytest.raises(ValueError, match="invalid characters"):
            mount.get_partition("/dev/sda\nrm -rf /")

    @patch("subprocess.run")
    def test_uses_subprocess_not_system(self, mock_run):
        """Verify subprocess.run is used instead of os.system"""
        mock_run.return_value = MagicMock(stdout="/dev/sda1 boot\n/dev/sda1  *  2048  1000000", returncode=0)

        try:
            mount.get_partition("/dev/sda")
        except RuntimeError:
            pass  # May fail due to parsing, but that's OK for this test

        # Verify subprocess.run was called with argument list
        mock_run.assert_called()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["fdisk", "-l", "/dev/sda"]

    @patch("subprocess.run")
    def test_handles_fdisk_failure(self, mock_run):
        """Ensure fdisk failures raise RuntimeError with context"""
        mock_run.side_effect = subprocess.CalledProcessError(1, "fdisk", stderr="fdisk: cannot open /dev/invalid")

        with pytest.raises(RuntimeError, match="fdisk failed"):
            mount.get_partition("/dev/invalid")


class TestMountPartitionSecurity:
    """Test mount_partition() input validation and security."""

    def test_rejects_non_dev_partition(self):
        """Ensure mount_partition rejects non-/dev/ paths"""
        with pytest.raises(ValueError, match="Invalid partition path"):
            mount.mount_partition("/etc/passwd", "test")

    def test_rejects_partition_with_semicolon(self):
        """Ensure mount_partition rejects semicolon in partition path"""
        with pytest.raises(ValueError, match="invalid characters"):
            mount.mount_partition("/dev/sda1; rm -rf /", "test")

    def test_rejects_partition_with_spaces(self):
        """Ensure mount_partition rejects spaces in partition path"""
        with pytest.raises(ValueError, match="invalid characters"):
            mount.mount_partition("/dev/sda1 /tmp/evil", "test")

    @patch("os.path.ismount", return_value=False)
    @patch("subprocess.run")
    def test_sanitizes_name_path_traversal(self, mock_run, mock_ismount):
        """Ensure mount_partition sanitizes path traversal in name"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Path traversal should be sanitized to just 'etc'
        mount.mount_partition("/dev/sda1", "../../../etc")

        # Verify the sanitized path was used
        mount_call = mock_run.call_args_list[1][0][0]
        assert mount_call == ["mount", "/dev/sda1", "/media/etc"]

    def test_sanitizes_name_parent_directory(self):
        """Ensure mount_partition strips parent directories from name"""
        with patch("os.path.ismount", return_value=False):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                # This should extract only 'test' from the path
                mount.mount_partition("/dev/sda1", "/some/path/test")

                # Verify mkdir was called with sanitized path
                calls = [str(call) for call in mock_run.call_args_list]
                # Check that the path doesn't contain parent directories
                mkdir_call = mock_run.call_args_list[0][0][0]
                assert mkdir_call[0] == "mkdir"
                assert "/media/test" in mkdir_call[2]

    def test_rejects_dot_name(self):
        """Ensure mount_partition rejects '.' as name"""
        with pytest.raises(ValueError, match="Invalid mount name"):
            mount.mount_partition("/dev/sda1", ".")

    def test_rejects_dotdot_name(self):
        """Ensure mount_partition rejects '..' as name"""
        with pytest.raises(ValueError, match="Invalid mount name"):
            mount.mount_partition("/dev/sda1", "..")

    @patch("os.path.ismount", return_value=False)
    @patch("subprocess.run")
    def test_sanitizes_name_with_slash(self, mock_run, mock_ismount):
        """Ensure mount_partition sanitizes names containing slash"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Name with slash should be sanitized to just final component 'path'
        mount.mount_partition("/dev/sda1", "test/path")

        # Verify the sanitized path was used
        mount_call = mock_run.call_args_list[1][0][0]
        assert mount_call == ["mount", "/dev/sda1", "/media/path"]

    @patch("os.path.ismount", return_value=False)
    @patch("subprocess.run")
    def test_uses_subprocess_with_argument_list(self, mock_run, mock_ismount):
        """Verify subprocess.run is used with argument list (not shell string)"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        mount.mount_partition("/dev/sda1", "test")

        # Verify both mkdir and mount calls use argument lists
        assert mock_run.call_count == 2

        # First call: mkdir
        mkdir_call = mock_run.call_args_list[0][0][0]
        assert mkdir_call == ["mkdir", "-p", "/media/test"]

        # Second call: mount
        mount_call = mock_run.call_args_list[1][0][0]
        assert mount_call == ["mount", "/dev/sda1", "/media/test"]

    @patch("os.path.ismount", return_value=False)
    @patch("subprocess.run")
    def test_handles_mount_failure(self, mock_run, mock_ismount):
        """Ensure mount failures raise RuntimeError with context"""
        mock_run.side_effect = subprocess.CalledProcessError(32, "mount", stderr="mount: /dev/sda1: permission denied")

        with pytest.raises(RuntimeError, match="Failed to mount"):
            mount.mount_partition("/dev/sda1", "test")


class TestUnmountPartitionSecurity:
    """Test unmount_partition() input validation and security."""

    @patch("os.path.ismount", return_value=True)
    @patch("subprocess.run")
    def test_sanitizes_name_path_traversal(self, mock_run, mock_ismount):
        """Ensure unmount_partition sanitizes path traversal"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Path traversal should be sanitized to just 'etc'
        mount.unmount_partition("../../../etc")

        # Verify the sanitized path was used
        umount_call = mock_run.call_args[0][0]
        assert umount_call == ["umount", "/media/etc"]

    def test_rejects_dot_name(self):
        """Ensure unmount_partition rejects '.' as name"""
        with pytest.raises(ValueError, match="Invalid mount name"):
            mount.unmount_partition(".")

    def test_rejects_dotdot_name(self):
        """Ensure unmount_partition rejects '..' as name"""
        with pytest.raises(ValueError, match="Invalid mount name"):
            mount.unmount_partition("..")

    @patch("os.path.ismount", return_value=True)
    @patch("subprocess.run")
    def test_sanitizes_name_with_slash(self, mock_run, mock_ismount):
        """Ensure unmount_partition sanitizes names with slash"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Name with slash should be sanitized to final component 'path'
        mount.unmount_partition("test/path")

        # Verify the sanitized path was used
        umount_call = mock_run.call_args[0][0]
        assert umount_call == ["umount", "/media/path"]

    def test_extracts_final_name_component(self):
        """Ensure unmount_partition strips parent paths"""
        with patch("os.path.ismount", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                # Should extract only 'test' from the path
                mount.unmount_partition("/some/path/test")

                # Verify umount was called with sanitized path
                umount_call = mock_run.call_args[0][0]
                assert umount_call == ["umount", "/media/test"]

    @patch("os.path.ismount", return_value=True)
    @patch("subprocess.run")
    def test_uses_subprocess_with_argument_list(self, mock_run, mock_ismount):
        """Verify subprocess.run is used with argument list"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        mount.unmount_partition("test")

        # Verify umount uses argument list
        umount_call = mock_run.call_args[0][0]
        assert umount_call == ["umount", "/media/test"]

    @patch("os.path.ismount", return_value=True)
    @patch("subprocess.run")
    def test_handles_unmount_failure(self, mock_run, mock_ismount):
        """Ensure unmount failures raise RuntimeError with context"""
        mock_run.side_effect = subprocess.CalledProcessError(1, "umount", stderr="umount: /media/test: target is busy")

        with pytest.raises(RuntimeError, match="Failed to unmount"):
            mount.unmount_partition("test")


class TestMountWrapperSecurity:
    """Test mount() wrapper function validation."""

    @patch("rpi_usb_cloner.storage.mount.get_partition")
    @patch("rpi_usb_cloner.storage.mount.mount_partition")
    def test_mount_calls_get_partition_and_mount_partition(self, mock_mount_part, mock_get_part):
        """Ensure mount() calls get_partition and mount_partition"""
        mock_get_part.return_value = "/dev/sda1"

        mount.mount("/dev/sda", "test")

        mock_get_part.assert_called_once_with("/dev/sda")
        mock_mount_part.assert_called_once_with("/dev/sda1", "test")

    @patch("rpi_usb_cloner.storage.mount.get_partition")
    def test_mount_propagates_validation_errors(self, mock_get_part):
        """Ensure mount() propagates validation errors from get_partition"""
        mock_get_part.side_effect = ValueError("Invalid device path")

        with pytest.raises(ValueError, match="Invalid device path"):
            mount.mount("/invalid", "test")


class TestUnmountWrapperSecurity:
    """Test unmount() wrapper function validation."""

    @patch("rpi_usb_cloner.storage.mount.unmount_partition")
    def test_unmount_calls_unmount_partition(self, mock_unmount_part):
        """Ensure unmount() calls unmount_partition"""
        mount.unmount("/dev/sda", "test")

        mock_unmount_part.assert_called_once_with("test")

    @patch("rpi_usb_cloner.storage.mount.unmount_partition")
    def test_unmount_propagates_validation_errors(self, mock_unmount_part):
        """Ensure unmount() propagates validation errors"""
        mock_unmount_part.side_effect = ValueError("Invalid mount name")

        with pytest.raises(ValueError, match="Invalid mount name"):
            mount.unmount("/dev/sda", "../etc")


class TestSecurityRegression:
    """Regression tests to ensure command injection is permanently fixed."""

    def test_no_os_system_usage(self):
        """Verify os.system is not used in any function implementations"""
        import inspect

        # Check each function individually to avoid false positives from docstrings
        for name, obj in inspect.getmembers(mount):
            if inspect.isfunction(obj) and obj.__module__ == mount.__name__:
                source = inspect.getsource(obj)
                # Skip docstrings by looking for actual os.system calls
                if "os.system(" in source and '"""' not in source.split("os.system(")[0]:
                    assert False, f"os.system() call found in function {name} - regression detected!"

    def test_no_shell_true_in_subprocess(self):
        """Verify subprocess is never called with shell=True"""
        import inspect

        source = inspect.getsource(mount)

        # shell=True should not appear
        assert "shell=True" not in source, "shell=True found in mount.py - security risk!"

    @patch("subprocess.run")
    def test_all_subprocess_calls_use_lists(self, mock_run):
        """Verify all subprocess calls use argument lists not strings"""
        mock_run.return_value = MagicMock(returncode=0, stdout="test", stderr="")

        # Try various operations
        with patch("os.path.ismount", return_value=False):
            try:
                mount.mount_partition("/dev/sda1", "test")
            except:
                pass

        # Check that all calls used lists, not strings
        for call in mock_run.call_args_list:
            cmd = call[0][0]
            assert isinstance(cmd, list), f"subprocess.run called with string, not list: {cmd}"
