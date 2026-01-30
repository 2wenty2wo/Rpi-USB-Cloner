"""Tests for main application module."""

from contextlib import suppress
from datetime import datetime, timedelta
from types import SimpleNamespace

from rpi_usb_cloner import main


# ==============================================================================
# Helper Function Tests
# ==============================================================================


class TestMainHelpers:
    """Test helper functions in main.py."""

    def test_get_device_name_from_dict(self):
        """Test extracting name from device dict."""
        device = {"name": "sda", "size": 100}
        assert main.get_device_name_from_dict(device) == "sda"
        assert main.get_device_name_from_dict({}) == ""

    def test_get_size_from_dict(self):
        """Test extracting size from device dict."""
        device = {"name": "sda", "size": 123456}
        assert main.get_size_from_dict(device) == 123456
        assert main.get_size_from_dict({}) == 0

    def test_get_vendor_from_dict(self):
        """Test extracting vendor from device dict."""
        device = {"vendor": "SanDisk", "model": "Cruzer"}
        assert main.get_vendor_from_dict(device) == "SanDisk"
        assert main.get_vendor_from_dict({}) == ""

    def test_get_model_from_dict(self):
        """Test extracting model from device dict."""
        device = {"vendor": "SanDisk", "model": "Cruzer"}
        assert main.get_model_from_dict(device) == "Cruzer"
        assert main.get_model_from_dict({}) == ""


# ==============================================================================
# Main Loop Integration Tests
# ==============================================================================


class FakeLogger:
    def debug(self, *_args, **_kwargs):
        pass

    def info(self, *_args, **_kwargs):
        pass

    def critical(self, *_args, **_kwargs):
        pass

    def log(self, *_args, **_kwargs):
        pass


class FakeImage:
    def copy(self):
        return self

    def paste(self, _image):
        pass


class FakeDisplayDevice:
    def display(self, _image):
        pass

    def clear(self):
        pass


class FakeDraw:
    def rectangle(self, *_args, **_kwargs):
        pass

    def text(self, *_args, **_kwargs):
        pass


class FakeDisplayContext:
    def __init__(self):
        self.width = 128
        self.height = 64
        self.image = FakeImage()
        self.disp = FakeDisplayDevice()
        self.draw = FakeDraw()
        self.x = 0
        self.top = 0
        self.fontinsert = None


class FakeLock:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeDateTime:
    now_value = datetime(2024, 1, 1, 0, 0, 0)

    @classmethod
    def now(cls):
        return cls.now_value


class FakeTime:
    def __init__(self, start=0.0, gpio=None, max_sleeps=1, time_step_multiplier=1.0):
        self.current = start
        self.sleep_calls = []
        self.sleep_count = 0
        self.gpio = gpio
        self.max_sleeps = max_sleeps
        self.time_step_multiplier = time_step_multiplier

    def time(self):
        return self.current

    def monotonic(self):
        return self.current

    def sleep(self, duration):
        self.sleep_calls.append(duration)
        self.current += duration * self.time_step_multiplier
        if self.gpio is not None:
            self.gpio.advance()
        self.sleep_count += 1
        if self.sleep_count >= self.max_sleeps:
            raise KeyboardInterrupt


class FakeGPIO:
    PIN_U = "U"
    PIN_D = "D"
    PIN_L = "L"
    PIN_R = "R"
    PIN_A = "A"
    PIN_B = "B"
    PIN_C = "C"
    PINS = [PIN_U, PIN_D, PIN_L, PIN_R, PIN_A, PIN_B, PIN_C]

    def __init__(self, states_sequence):
        self.states_sequence = states_sequence
        self.index = 0

    def setup_gpio(self):
        pass

    def cleanup(self):
        pass

    def is_pressed(self, pin):
        state = self.states_sequence[min(self.index, len(self.states_sequence) - 1)]
        return state.get(pin, False)

    def advance(self):
        if self.index < len(self.states_sequence) - 1:
            self.index += 1


class FakeMenuNavigator:
    next_action = None
    last_instance = None

    def __init__(self, *args, **kwargs):
        FakeMenuNavigator.last_instance = self
        self._action = FakeMenuNavigator.next_action
        self._screen = SimpleNamespace(
            screen_id=main.definitions.MAIN_MENU.screen_id,
            title="Main",
            status_line=None,
        )
        self._state = SimpleNamespace(selected_index=0, scroll_offset=0)
        self.activate_calls = 0
        self.move_calls = []
        self.back_calls = 0
        self.set_selection_calls = []
        self.visible_rows = None

    def current_screen(self):
        return self._screen

    def current_items(self):
        return [SimpleNamespace(label="Item", submenu=None)]

    def current_state(self):
        return self._state

    def move_selection(self, direction, visible_rows):
        self.move_calls.append((direction, visible_rows))

    def activate(self, _visible_rows):
        self.activate_calls += 1
        return self._action

    def back(self):
        self.back_calls += 1

    def set_selection(self, screen_id, index, visible_rows):
        self.set_selection_calls.append((screen_id, index, visible_rows))
        self._state.selected_index = index

    def consume_last_navigation_action(self):
        return None

    def sync_visible_rows(self, visible_rows):
        self.visible_rows = visible_rows


def build_fake_state(lcdstart):
    class FakeState:
        def __init__(self):
            self.index = 0
            self.usb_list_index = 0
            self.run_once = 0
            self.lcdstart = lcdstart
            self.last_usb_check = 0.0
            self.last_seen_devices = []
            self.last_seen_raw_devices = []
            self.last_seen_mount_snapshot = []

    return FakeState


def setup_main_mocks(
    monkeypatch,
    *,
    fake_time,
    fake_gpio,
    settings=None,
    drives_list=None,
    raw_list=None,
    mounts=None,
):
    settings = settings or {}
    drives_list = drives_list or []
    raw_list = raw_list or []
    mounts = mounts or []
    context = FakeDisplayContext()

    monkeypatch.setattr(main, "setup_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "get_logger", lambda *args, **kwargs: FakeLogger())
    monkeypatch.setattr(
        main.menu_actions, "set_action_context", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(main, "gpio", fake_gpio)
    monkeypatch.setattr(main, "time", fake_time)
    monkeypatch.setattr(main, "datetime", FakeDateTime)

    monkeypatch.setattr(main.display, "init_display", lambda: context)
    monkeypatch.setattr(main.display, "set_display_context", lambda _context: None)
    monkeypatch.setattr(main.display, "get_display_context", lambda: context)
    monkeypatch.setattr(main.display, "clear_display", lambda: None)
    monkeypatch.setattr(main.display, "mark_display_dirty", lambda: None)
    monkeypatch.setattr(main.display, "capture_screenshot", lambda: None)
    monkeypatch.setattr(main.display, "_display_lock", FakeLock())

    monkeypatch.setattr(main.renderer, "calculate_visible_rows", lambda **kwargs: 3)
    monkeypatch.setattr(main.renderer, "render_menu_screen", lambda **kwargs: None)
    monkeypatch.setattr(
        main.renderer, "render_menu_image", lambda **kwargs: context.image
    )
    monkeypatch.setattr(
        main.renderer, "calculate_footer_bounds", lambda **kwargs: (0, 0)
    )
    monkeypatch.setattr(
        main.transitions, "render_slide_transition", lambda **kwargs: None
    )

    def fake_get_setting(key, default=None):
        return settings.get(key, default)

    def fake_get_bool(key, default=False):
        return settings.get(key, default)

    monkeypatch.setattr(main.settings_store, "get_setting", fake_get_setting)
    monkeypatch.setattr(main.settings_store, "get_bool", fake_get_bool)
    monkeypatch.setattr(
        main.settings_store, "set_setting", lambda *args, **kwargs: None
    )

    monkeypatch.setattr(main.web_server, "start_server", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        main.devices, "configure_device_helpers", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(main, "configure_format_helpers", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        main.wifi, "configure_wifi_helpers", lambda *args, **kwargs: None
    )

    drive_calls = {"media": 0, "raw": 0, "invalidate": 0}

    if (
        isinstance(drives_list, list)
        and drives_list
        and isinstance(drives_list[0], list)
    ):
        drive_sequence = iter(drives_list)
        last_drive_snapshot = drives_list[0]  # Start with first element
    else:
        drive_sequence = None
        last_drive_snapshot = drives_list

    def list_media_drive_names():
        drive_calls["media"] += 1
        nonlocal last_drive_snapshot
        if drive_sequence is not None:
            with suppress(StopIteration):
                last_drive_snapshot = next(drive_sequence)
        return list(last_drive_snapshot)

    def list_raw_usb_disk_names():
        drive_calls["raw"] += 1
        return list(raw_list)

    def invalidate_repo_cache():
        drive_calls["invalidate"] += 1

    # Mock the batched USB snapshot function (replaces separate list_* functions)
    def get_usb_snapshot():
        drive_calls["media"] += 1
        drive_calls["raw"] += 1
        nonlocal last_drive_snapshot
        if drive_sequence is not None:
            with suppress(StopIteration):
                last_drive_snapshot = next(drive_sequence)
        # Extract mountpoints from mounts data
        mount_list = []
        for m in mounts:
            if isinstance(m, dict) and m.get("mountpoint"):
                mount_list.append((m.get("name", ""), m.get("mountpoint", "")))
        return main.drives.USBSnapshot(
            raw_devices=list(raw_list),
            media_devices=list(last_drive_snapshot),
            mountpoints=mount_list,
        )

    monkeypatch.setattr(main.drives, "get_usb_snapshot", get_usb_snapshot)
    # Also mock list_media_drive_names for initialization (before batched snapshot kicks in)
    monkeypatch.setattr(
        main.drives, "list_media_drive_names", lambda: list(last_drive_snapshot)
    )
    monkeypatch.setattr(main.drives, "invalidate_repo_cache", invalidate_repo_cache)
    monkeypatch.setattr(
        main.drives,
        "select_active_drive",
        lambda current_drives, index: current_drives[index] if current_drives else None,
    )
    monkeypatch.setattr(main.drives, "get_active_drive_label", lambda active: active)

    monkeypatch.setattr(main.navigator, "MenuNavigator", FakeMenuNavigator)
    return drive_calls


class TestMainLoopIntegration:
    def test_button_polling_cadence(self, monkeypatch):
        fake_gpio = FakeGPIO([{}])
        fake_time = FakeTime(start=0.0, gpio=fake_gpio, max_sleeps=3)
        setup_main_mocks(
            monkeypatch,
            fake_time=fake_time,
            fake_gpio=fake_gpio,
            settings={"screensaver_enabled": False, "web_server_enabled": False},
        )
        monkeypatch.setattr(
            main.app_state, "AppState", build_fake_state(FakeDateTime.now())
        )
        monkeypatch.setattr(main.app_state, "USB_REFRESH_INTERVAL", 99.0)

        main.main([])

        assert fake_time.sleep_calls == [0.02, 0.02, 0.02]

    def test_usb_refresh_interval_triggers(self, monkeypatch):
        fake_gpio = FakeGPIO([{}])
        # Need max_sleeps=3 for two USB refresh cycles (batched function counts as one call)
        fake_time = FakeTime(
            start=0.0, gpio=fake_gpio, max_sleeps=3, time_step_multiplier=100.0
        )
        drive_calls = setup_main_mocks(
            monkeypatch,
            fake_time=fake_time,
            fake_gpio=fake_gpio,
            settings={"screensaver_enabled": False, "web_server_enabled": False},
            drives_list=[["sda"], ["sda", "sdb"]],
            raw_list=["sda"],
            mounts=[{"name": "sda", "mountpoint": "/media/usb"}],
        )
        monkeypatch.setattr(
            main.app_state, "AppState", build_fake_state(FakeDateTime.now())
        )
        monkeypatch.setattr(main.app_state, "USB_REFRESH_INTERVAL", 2.0)

        main.main([])

        assert drive_calls["media"] >= 2
        assert drive_calls["raw"] >= 2
        assert drive_calls["invalidate"] >= 1

    def test_screensaver_activation(self, monkeypatch):
        fake_gpio = FakeGPIO([{}])
        fake_time = FakeTime(start=0.0, gpio=fake_gpio, max_sleeps=2)
        setup_main_mocks(
            monkeypatch,
            fake_time=fake_time,
            fake_gpio=fake_gpio,
            settings={
                "screensaver_enabled": True,
                "screensaver_mode": "random",
                "web_server_enabled": False,
            },
        )
        monkeypatch.setattr(
            main.app_state,
            "AppState",
            build_fake_state(FakeDateTime.now() - timedelta(seconds=5)),
        )
        monkeypatch.setattr(main.app_state, "screensaver_enabled", True)
        monkeypatch.setattr(main.app_state, "SCREENSAVER_TIMEOUT", 0.1)
        screensaver_calls = []

        def fake_screensaver(*_args, **_kwargs):
            screensaver_calls.append(True)
            return True

        monkeypatch.setattr(main.screensaver, "play_screensaver", fake_screensaver)

        main.main([])

        assert screensaver_calls

    def test_action_dispatch_mapping(self, monkeypatch):
        def run_press_test(sequence):
            fake_gpio = FakeGPIO(sequence)
            fake_time = FakeTime(start=0.0, gpio=fake_gpio, max_sleeps=3)
            setup_main_mocks(
                monkeypatch,
                fake_time=fake_time,
                fake_gpio=fake_gpio,
                settings={"screensaver_enabled": False, "web_server_enabled": False},
            )
            monkeypatch.setattr(
                main.app_state, "AppState", build_fake_state(FakeDateTime.now())
            )
            monkeypatch.setattr(main.app_state, "USB_REFRESH_INTERVAL", 99.0)

            action_calls = []

            def fake_action():
                action_calls.append("called")

            FakeMenuNavigator.next_action = fake_action

            main.main([])

            assert action_calls == ["called"]

        run_press_test([{"R": False}, {"R": True}, {"R": False}])
        run_press_test([{"B": False}, {"B": True}, {"B": False}])
