"""Tests for drive listing and selection service."""

from pathlib import Path
from unittest.mock import patch

from rpi_usb_cloner.services.drives import (
    DriveSnapshot,
    _collect_mountpoints,
    _get_repo_device_names,
    _is_repo_on_mount,
    get_active_drive_label,
    invalidate_repo_cache,
    list_media_drive_labels,
    list_media_drive_names,
    list_usb_disk_labels,
    list_usb_disk_names,
    refresh_drives,
    select_active_drive,
)


class TestCollectMountpoints:
    """Tests for _collect_mountpoints function."""

    def test_collect_single_mountpoint(self):
        """Test collecting mountpoint from device."""
        device = {"name": "sda", "mountpoint": "/mnt/usb"}

        with patch(
            "rpi_usb_cloner.services.drives.storage_devices.get_children"
        ) as mock_children:
            mock_children.return_value = []
            mountpoints = _collect_mountpoints(device)

        assert mountpoints == {"/mnt/usb"}

    def test_collect_no_mountpoint(self):
        """Test device with no mountpoint."""
        device = {"name": "sda"}

        with patch(
            "rpi_usb_cloner.services.drives.storage_devices.get_children"
        ) as mock_children:
            mock_children.return_value = []
            mountpoints = _collect_mountpoints(device)

        assert mountpoints == set()

    def test_collect_with_partitions(self):
        """Test collecting mountpoints from device and partitions."""
        device = {
            "name": "sda",
            "mountpoint": None,
        }
        partitions = [
            {"name": "sda1", "mountpoint": "/mnt/part1"},
            {"name": "sda2", "mountpoint": "/mnt/part2"},
        ]

        with patch(
            "rpi_usb_cloner.services.drives.storage_devices.get_children"
        ) as mock_children:
            mock_children.side_effect = [partitions, [], []]
            mountpoints = _collect_mountpoints(device)

        assert mountpoints == {"/mnt/part1", "/mnt/part2"}

    def test_collect_nested_structure(self):
        """Test collecting mountpoints from nested device structure."""
        device = {"name": "sda", "mountpoint": "/mnt/device"}
        partition1 = {"name": "sda1", "mountpoint": "/mnt/part1"}
        partition2 = {"name": "sda2", "mountpoint": None}
        subpartition = {"name": "sda2p1", "mountpoint": "/mnt/subpart"}

        with patch(
            "rpi_usb_cloner.services.drives.storage_devices.get_children"
        ) as mock_children:
            mock_children.side_effect = [
                [partition1, partition2],  # children of device
                [],  # children of partition1
                [subpartition],  # children of partition2
                [],  # children of subpartition
            ]
            mountpoints = _collect_mountpoints(device)

        assert mountpoints == {"/mnt/device", "/mnt/part1", "/mnt/subpart"}


class TestIsRepoOnMount:
    """Tests for _is_repo_on_mount function."""

    def test_exact_match(self):
        """Test exact path match."""
        assert _is_repo_on_mount(Path("/mnt/usb"), Path("/mnt/usb")) is True

    def test_repo_in_mount(self):
        """Test repo is subdirectory of mount."""
        assert _is_repo_on_mount(Path("/mnt/usb/images"), Path("/mnt/usb")) is True
        assert _is_repo_on_mount(Path("/mnt/usb/a/b/c"), Path("/mnt/usb")) is True

    def test_mount_not_parent_of_repo(self):
        """Test mount is not parent of repo."""
        assert _is_repo_on_mount(Path("/mnt/usb"), Path("/mnt/other")) is False
        assert _is_repo_on_mount(Path("/mnt/usb1"), Path("/mnt/usb")) is False

    def test_different_paths(self):
        """Test completely different paths."""
        assert _is_repo_on_mount(Path("/home/user"), Path("/mnt/usb")) is False


class TestGetRepoDeviceNames:
    """Tests for _get_repo_device_names function."""

    @patch("rpi_usb_cloner.services.drives.find_image_repos")
    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    @patch("rpi_usb_cloner.services.drives._collect_mountpoints")
    def test_no_repos(self, mock_collect, mock_list_usb, mock_find_repos):
        """Test when no repos are found."""
        invalidate_repo_cache()  # Clear cache before test
        mock_find_repos.return_value = []

        result = _get_repo_device_names()

        assert result == set()
        mock_list_usb.assert_not_called()

    @patch("rpi_usb_cloner.services.drives.find_image_repos")
    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    @patch("rpi_usb_cloner.services.drives._collect_mountpoints")
    def test_repo_on_device(self, mock_collect, mock_list_usb, mock_find_repos):
        """Test identifying device containing repo."""
        from rpi_usb_cloner.domain import ImageRepo

        invalidate_repo_cache()  # Clear cache before test
        mock_find_repos.return_value = [
            ImageRepo(path=Path("/mnt/usb/clonezilla"), drive_name="sda")
        ]
        mock_list_usb.return_value = [
            {"name": "sda", "size": 8000000000},
            {"name": "sdb", "size": 16000000000},
        ]
        mock_collect.side_effect = [
            {"/mnt/usb"},  # sda is mounted at /mnt/usb
            {"/mnt/other"},  # sdb is mounted at /mnt/other
        ]

        result = _get_repo_device_names()

        assert result == {"sda"}

    @patch("rpi_usb_cloner.services.drives.find_image_repos")
    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    @patch("rpi_usb_cloner.services.drives._collect_mountpoints")
    def test_multiple_repo_devices(self, mock_collect, mock_list_usb, mock_find_repos):
        """Test multiple devices containing repos."""
        from rpi_usb_cloner.domain import ImageRepo

        invalidate_repo_cache()  # Clear cache before test
        mock_find_repos.return_value = [
            ImageRepo(path=Path("/mnt/usb1/repo1"), drive_name="sda"),
            ImageRepo(path=Path("/mnt/usb2/repo2"), drive_name="sdb"),
        ]
        mock_list_usb.return_value = [
            {"name": "sda"},
            {"name": "sdb"},
            {"name": "sdc"},
        ]
        mock_collect.side_effect = [
            {"/mnt/usb1"},
            {"/mnt/usb2"},
            {"/mnt/usb3"},
        ]

        result = _get_repo_device_names()

        assert result == {"sda", "sdb"}

    @patch("rpi_usb_cloner.services.drives.find_image_repos")
    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    @patch("rpi_usb_cloner.services.drives._collect_mountpoints")
    def test_device_without_name(self, mock_collect, mock_list_usb, mock_find_repos):
        """Test device without name is skipped."""
        from rpi_usb_cloner.domain import ImageRepo

        invalidate_repo_cache()  # Clear cache before test
        mock_find_repos.return_value = [
            ImageRepo(path=Path("/mnt/usb/repo"), drive_name=None)
        ]
        mock_list_usb.return_value = [
            {"size": 8000000000},  # No name
            {"name": "sdb"},
        ]
        mock_collect.side_effect = [{"/mnt/usb"}, {"/mnt/other"}]

        result = _get_repo_device_names()

        # Device without name should be skipped
        assert "sdb" not in result or result == set()


class TestListMediaDriveNames:
    """Tests for list_media_drive_names function."""

    @patch("rpi_usb_cloner.services.drives._get_repo_device_names")
    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    def test_list_all_drives(self, mock_list_usb, mock_get_repos):
        """Test listing all non-repo drives."""
        mock_get_repos.return_value = set()
        mock_list_usb.return_value = [
            {"name": "sda", "size": 8000000000},
            {"name": "sdb", "size": 16000000000},
        ]

        result = list_media_drive_names()

        assert result == ["sda", "sdb"]

    @patch("rpi_usb_cloner.services.drives._get_repo_device_names")
    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    def test_exclude_repo_drives(self, mock_list_usb, mock_get_repos):
        """Test excluding repo drives from list."""
        mock_get_repos.return_value = {"sdb"}
        mock_list_usb.return_value = [
            {"name": "sda", "size": 8000000000},
            {"name": "sdb", "size": 16000000000},
            {"name": "sdc", "size": 32000000000},
        ]

        result = list_media_drive_names()

        assert result == ["sda", "sdc"]
        assert "sdb" not in result


class TestListMediaDriveLabels:
    """Tests for list_media_drive_labels function."""

    @patch("rpi_usb_cloner.services.drives._get_repo_device_names")
    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    def test_list_drive_labels(self, mock_list_usb, mock_get_repos):
        """Test listing drive labels with size."""
        mock_get_repos.return_value = set()
        mock_list_usb.return_value = [
            {"name": "sda", "size": 8000000000},
            {"name": "sdb", "size": 16000000000},
        ]

        result = list_media_drive_labels()

        assert "sda 7.5GB" in result
        assert "sdb 14.9GB" in result

    @patch("rpi_usb_cloner.services.drives._get_repo_device_names")
    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    def test_exclude_repo_from_labels(self, mock_list_usb, mock_get_repos):
        """Test excluding repo drives from labels."""
        mock_get_repos.return_value = {"sdb"}
        mock_list_usb.return_value = [
            {"name": "sda", "size": 8000000000},
            {"name": "sdb", "size": 16000000000},
        ]

        result = list_media_drive_labels()

        assert len(result) == 1
        assert "sda" in result[0]


class TestListUsbDiskNames:
    """Tests for list_usb_disk_names function."""

    @patch("rpi_usb_cloner.services.drives._get_repo_device_names")
    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    def test_list_usb_names(self, mock_list_usb, mock_get_repos):
        """Test listing USB disk names."""
        mock_get_repos.return_value = set()
        mock_list_usb.return_value = [
            {"name": "sda"},
            {"name": "sdb"},
        ]

        result = list_usb_disk_names()

        assert result == ["sda", "sdb"]

    @patch("rpi_usb_cloner.services.drives._get_repo_device_names")
    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    def test_exclude_repo_from_usb_names(self, mock_list_usb, mock_get_repos):
        """Test excluding repo drives from USB names."""
        mock_get_repos.return_value = {"sdb"}
        mock_list_usb.return_value = [
            {"name": "sda"},
            {"name": "sdb"},
            {"name": "sdc"},
        ]

        result = list_usb_disk_names()

        assert result == ["sda", "sdc"]


class TestListUsbDiskLabels:
    """Tests for list_usb_disk_labels function."""

    @patch("rpi_usb_cloner.services.drives._get_repo_device_names")
    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    @patch("rpi_usb_cloner.services.drives.format_device_label")
    def test_list_usb_labels(self, mock_format, mock_list_usb, mock_get_repos):
        """Test listing USB disk labels."""
        mock_get_repos.return_value = set()
        mock_list_usb.return_value = [
            {"name": "sda"},
            {"name": "sdb"},
        ]
        mock_format.side_effect = ["sda 8GB", "sdb 16GB"]

        result = list_usb_disk_labels()

        assert result == ["sda 8GB", "sdb 16GB"]


class TestRefreshDrives:
    """Tests for refresh_drives function."""

    @patch("rpi_usb_cloner.services.drives.list_media_drive_names")
    def test_refresh_with_active_drive(self, mock_list):
        """Test refresh with active drive still present."""
        mock_list.return_value = ["sda", "sdb", "sdc"]

        snapshot = refresh_drives("sdb")

        assert snapshot.discovered == ["sda", "sdb", "sdc"]
        assert snapshot.active == "sdb"

    @patch("rpi_usb_cloner.services.drives.list_media_drive_names")
    def test_refresh_active_drive_removed(self, mock_list):
        """Test refresh when active drive is no longer present."""
        mock_list.return_value = ["sda", "sdc"]

        snapshot = refresh_drives("sdb")

        assert snapshot.discovered == ["sda", "sdc"]
        assert snapshot.active is None

    @patch("rpi_usb_cloner.services.drives.list_media_drive_names")
    def test_refresh_no_active_drive(self, mock_list):
        """Test refresh with no active drive."""
        mock_list.return_value = ["sda", "sdb"]

        snapshot = refresh_drives(None)

        assert snapshot.discovered == ["sda", "sdb"]
        assert snapshot.active is None


class TestSelectActiveDrive:
    """Tests for select_active_drive function."""

    def test_select_valid_index(self):
        """Test selecting drive at valid index."""
        drives = ["sda", "sdb", "sdc"]
        assert select_active_drive(drives, 0) == "sda"
        assert select_active_drive(drives, 1) == "sdb"
        assert select_active_drive(drives, 2) == "sdc"

    def test_select_negative_index(self):
        """Test selecting with negative index returns first drive."""
        drives = ["sda", "sdb", "sdc"]
        assert select_active_drive(drives, -1) == "sda"
        assert select_active_drive(drives, -5) == "sda"

    def test_select_index_too_large(self):
        """Test selecting with index beyond list returns last drive."""
        drives = ["sda", "sdb", "sdc"]
        assert select_active_drive(drives, 5) == "sdc"
        assert select_active_drive(drives, 100) == "sdc"

    def test_select_empty_list(self):
        """Test selecting from empty list returns None."""
        assert select_active_drive([], 0) is None
        assert select_active_drive([], 5) is None

    def test_select_single_drive(self):
        """Test selecting from single-drive list."""
        drives = ["sda"]
        assert select_active_drive(drives, 0) == "sda"
        assert select_active_drive(drives, 5) == "sda"
        assert select_active_drive(drives, -1) == "sda"


class TestGetActiveDriveLabel:
    """Tests for get_active_drive_label function."""

    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    def test_get_label_for_existing_drive(self, mock_list_usb):
        """Test getting label for existing drive."""
        mock_list_usb.return_value = [
            {"name": "sda", "size": 8000000000},
            {"name": "sdb", "size": 16000000000},
        ]

        result = get_active_drive_label("sdb")

        assert result == "sdb 14.90GB"

    def test_get_label_for_none(self):
        """Test getting label for None returns None."""
        result = get_active_drive_label(None)

        assert result is None

    @patch("rpi_usb_cloner.services.drives.list_usb_disks")
    def test_get_label_for_nonexistent_drive(self, mock_list_usb):
        """Test getting label for drive not in media devices."""
        mock_list_usb.return_value = [{"name": "sda", "size": 8000000000}]

        result = get_active_drive_label("sdb")

        assert result == "sdb"  # Returns the drive name itself


class TestDriveSnapshot:
    """Tests for DriveSnapshot dataclass."""

    def test_create_snapshot(self):
        """Test creating a drive snapshot."""
        snapshot = DriveSnapshot(discovered=["sda", "sdb"], active="sda")

        assert snapshot.discovered == ["sda", "sdb"]
        assert snapshot.active == "sda"

    def test_snapshot_with_none_active(self):
        """Test snapshot with no active drive."""
        snapshot = DriveSnapshot(discovered=["sda"], active=None)

        assert snapshot.discovered == ["sda"]
        assert snapshot.active is None

    def test_snapshot_equality(self):
        """Test snapshot equality."""
        snapshot1 = DriveSnapshot(discovered=["sda", "sdb"], active="sda")
        snapshot2 = DriveSnapshot(discovered=["sda", "sdb"], active="sda")
        snapshot3 = DriveSnapshot(discovered=["sda"], active="sda")

        assert snapshot1 == snapshot2
        assert snapshot1 != snapshot3
