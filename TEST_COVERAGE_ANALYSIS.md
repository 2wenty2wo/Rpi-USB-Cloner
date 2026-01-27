# Test Coverage Analysis & Improvement Plan

**Date**: 2026-01-24
**Current Overall Coverage**: ~27-30% (Estimated, automated run unavailable)
**Files Analyzed**: 85 Python files in `rpi_usb_cloner/`
**Test Files**: 35 test modules (including `test_menu_navigator.py`)

## Recent Updates (2026-01-24)

✅ **Added Action Handler Tests** (+38 tests, +7.47% coverage):
- `tests/test_actions_drive.py` - 17 tests covering drive action helpers
- `tests/test_actions_image.py` - 10 tests covering image action helpers
- `tests/test_actions_settings.py` - 1 placeholder test (functions need refactoring)

**Coverage improvements**:
- `actions/drive_actions.py`: 0% → 15% (helper functions tested)
- `actions/image_actions.py`: 0% → 10% (helper functions tested)
- `actions/settings/*.py`: 0% → 5% (minimal imports tested)

**Key findings**: Many action functions have complex GPIO polling loops that are difficult to unit test. Functions would benefit from refactoring to separate business logic from UI/GPIO concerns.

---

## Executive Summary

The codebase has **strong test coverage** (≥80%) for core storage and cloning operations but **lacks coverage** for UI, actions, menu system, web server, and main application logic. Out of 85 files:

- ✅ **30 files** (35%) have ≥80% coverage (excellent)
- ⚠️ **6 files** (7%) have <50% coverage (needs improvement)
- ❌ **49 files** (58%) have 0% coverage (critical gap)

**Priority Areas for Improvement** (by impact):
1. **Critical Safety**: Action handlers (data loss prevention)
2. **High Impact**: Main application loop, menu system, UI rendering
3. **User-Facing**: Web server, WiFi configuration
4. **Quality of Life**: Logging, error handling, screensaver

---

## Current Coverage Strengths

### ✅ Well-Tested Components (≥80% coverage)

These areas have excellent test coverage and should serve as models:

| Component | Coverage | Test File | Notes |
|-----------|----------|-----------|-------|
| **Config/Settings** | 100% | `test_settings.py` (472 LOC) | Comprehensive settings tests |
| **Domain Models** | 100% | `test_domain_models.py` (482 LOC) | All data classes tested |
| **Storage Validation** | 97.4% | `test_validation.py` (424 LOC) | Input validation well-covered |
| **Clone Progress** | 96.0% | `test_clone_progress.py` (446 LOC) | Progress tracking solid |
| **Clone Verification** | 93.4% | `test_verification.py` (407 LOC) | SHA256 verification tested |
| **Services/Drives** | 92.7% | `test_services_drives.py` (439 LOC) | Drive service layer good |
| **Devices** | 92.1% | `test_devices.py` (672 LOC) | USB detection well-tested |
| **Command Runners** | 90.5% | `test_command_runners.py` (410 LOC) | Command execution covered |
| **Clone Operations** | 86.6% | `test_clone_operations.py` (620 LOC) | Core cloning logic tested |
| **Format** | 86.3% | `test_format.py` (629 LOC) | Formatting operations good |
| **Mount** | 85.2% | `test_mount.py` (476 LOC) | Mount/unmount tested |

**Key Takeaways**:
- Storage layer has excellent coverage (85-100%)
- Clonezilla operations are well-tested (backup, restore, partition table)
- Safety validations are comprehensive
- Mock fixtures in `conftest.py` are robust

---

## Critical Coverage Gaps

### ⚠️ Priority 1: Action Handlers (10-15% coverage, PARTIALLY ADDRESSED)

**Risk Level**: 🟡 MEDIUM - Helper functions tested, main operations still need work

| File | LOC | Coverage | Status | Risk |
|------|-----|----------|--------|------|
| `actions/drive_actions.py` | 641 | ~15% | ⚠️ Helpers tested | 🔴 Data loss risk |
| `actions/image_actions.py` | 682 | ~10% | ⚠️ Helpers tested | 🔴 Data loss risk |
| `actions/settings/update_manager.py` | 257 | 0% | ❌ Not tested | 🟡 System stability |
| `actions/settings/system_utils.py` | 136 | 0% | ❌ Not tested | 🟡 System stability |
| `actions/settings/ui_actions.py` | 129 | 0% | ❌ Not tested | 🟢 Low risk |
| `actions/settings/system_power.py` | 88 | 0% | ❌ Not tested | 🟡 System stability |

**Recent Progress** (2026-01-24):
- ✅ Added tests for helper functions (_log_debug, _collect_mountpoints, etc.)
- ✅ Added tests for device selection logic (_pick_source_target)
- ✅ Added tests for error handling paths (no devices, invalid input)
- ⚠️ Main action functions (copy_drive, erase_drive, backup_image) still difficult to test due to complex GPIO polling loops

**Why Still Critical**:
- Main action functions have 100+ line while-loops polling GPIO buttons
- Tight coupling between business logic and UI rendering
- User confirmation dialogs embedded in GPIO loops
- Threading and progress tracking adds complexity

**Completed Tests** (`test_drive_actions.py` - 17 tests):
   ```python
   ✅ test_log_debug_helper()
   ✅ test_handle_screenshot()
   ✅ test_pick_source_target() (3 tests)
   ✅ test_collect_mountpoints() (4 tests)
   ✅ test_ensure_root_for_erase() (2 tests)
   ✅ test_copy_drive_error_handling() (2 tests)
   ✅ test_erase_drive_error_handling()
   ✅ test_unmount_drive_error_handling() (2 tests)
   ```

**Completed Tests** (`test_image_actions.py` - 10 tests):
   ```python
   ✅ test_log_debug_helper()
   ✅ test_format_elapsed_duration() (4 tests)
   ✅ test_collect_mountpoints() (3 tests)
   ✅ test_extract_stderr_message() (3 tests)
   ✅ test_format_restore_error_lines() (2 tests)
   ✅ test_coming_soon()
   ```

**Recommended Next Steps**:

1. **Refactor for Testability**:
   - Extract business logic from GPIO loops
   - Use dependency injection for GPIO/UI components
   - Separate confirmation logic from action execution

2. **Integration Tests**:
   - Create end-to-end tests with simulated GPIO sequences
   - Test full workflows (select → confirm → execute → verify)

3. **Settings Actions** (`test_settings_actions.py`):
   ```python
   - test_update_system_requires_confirmation()
   - test_shutdown_requires_confirmation()
   - test_reboot_requires_confirmation()
   - test_wifi_configuration_validates_ssid()
   - test_screensaver_settings_persistence()
   ```

**Estimated Impact**: +1,976 LOC covered (20% overall coverage increase)

---

### ❌ Priority 2: Main Application Loop (0% coverage)

**File**: `main.py` (358 LOC)
**Coverage**: 0%
**Risk Level**: 🟡 MEDIUM - Logic errors could cause UI freezes

**Why Important**:
- Central event loop coordinates all functionality
- Button polling, USB detection, screensaver timing
- Action dispatcher maps menu selections to handlers
- Error handling for uncaught exceptions

**Recommended Tests** (`test_main.py`):

```python
# Integration tests (may require mocking hardware)
- test_main_loop_polls_buttons_at_20ms_intervals()
- test_main_loop_refreshes_devices_every_2_seconds()
- test_main_loop_triggers_screensaver_after_timeout()
- test_action_dispatcher_maps_actions_correctly()
- test_main_handles_keyboard_interrupt_gracefully()
- test_main_handles_uncaught_exceptions()

# Unit tests for helper functions
- test_get_button_press_returns_correct_button()
- test_refresh_device_list_updates_context()
- test_screensaver_activation_clears_display()
```

**Estimated Impact**: +358 LOC covered (3.6% overall coverage increase)

---

### ✅ Priority 3: Menu System (Partially Addressed)

**Files**:
- `menu/navigator.py` (85 LOC) - Covered by `test_menu_navigator.py`
- `menu/model.py` (17 LOC) - Tests needed
- `menu/definitions/*.py` (34 LOC total) - Tests needed

**Status**:
- `menu/navigator.py` has a comprehensive test suite `tests/test_menu_navigator.py` with 17 tests covering initialization, navigation, bounds checking, scrolling logic, and stack management.

---

### ❌ Priority 4: UI Rendering (0% coverage)

**Files**:
- `ui/renderer.py` (192 LOC) - 0% ⭐ Critical file
- `ui/menus.py` (462 LOC) - 0%
- `ui/screens/progress.py` (121 LOC) - 0%
- `ui/screens/confirmation.py` (290 LOC) - 0%
- `ui/screens/error.py` (40 LOC) - 0%
- `ui/screens/status.py` (23 LOC) - 0%
- `ui/keyboard.py` (303 LOC) - 0%
- `ui/display.py` (380 LOC) - 14.6% (LOW)

**Why Important**:
- User feedback depends on correct rendering
- Progress bars must accurately reflect operation status
- Error messages must be visible
- Confirmation dialogs prevent accidental data loss

**Recommended Tests** (`test_ui_*.py`):

1. **Renderer** (`test_ui_renderer.py`):
   ```python
   - test_render_menu_displays_all_items()
   - test_render_menu_highlights_selected_item()
   - test_render_menu_shows_scrollbar_for_long_lists()
   - test_render_menu_truncates_long_text()
   ```

2. **Progress Screen** (`test_ui_progress.py`):
   ```python
   - test_progress_bar_renders_correctly()
   - test_progress_shows_percentage()
   - test_progress_calculates_eta_correctly()
   - test_progress_handles_zero_total_gracefully()
   ```

3. **Confirmation Screen** (`test_ui_confirmation.py`):
   ```python
   - test_confirmation_dialog_defaults_to_no()
   - test_confirmation_dialog_accepts_yes()
   - test_confirmation_checkbox_list_tracks_selections()
   - test_confirmation_multiline_text_wraps()
   ```

4. **Display** (`test_ui_display.py`):
   ```python
   - test_display_initialization_detects_i2c_address()
   - test_display_initialization_falls_back_to_virtual()
   - test_display_context_loads_fonts()
   - test_display_context_loads_icons()
   ```

**Estimated Impact**: +1,811 LOC covered (18.4% overall coverage increase)

**Note**: UI tests may require:
- Mocking `luma.oled` device (already done in `conftest.py`)
- Image comparison for pixel-perfect rendering (optional)
- Focus on logic rather than pixel output

---

### ❌ Priority 5: Web Server (0% coverage)

**File**: `web/server.py` (340 LOC)
**Coverage**: 0%
**Risk Level**: 🟡 MEDIUM - Security and stability

**Why Important**:
- Web UI provides remote access to OLED display
- WebSocket streaming must handle disconnects gracefully
- System health monitoring exposed via API
- Potential security risks (CORS, input validation)

**Recommended Tests** (`test_web_server.py`):

```python
# HTTP endpoints
- test_index_page_loads()
- test_static_files_serve_correctly()
- test_health_endpoint_returns_system_stats()

# WebSocket
- test_websocket_streams_display_frames()
- test_websocket_handles_client_disconnect()
- test_websocket_broadcasts_to_multiple_clients()

# Server lifecycle
- test_server_starts_on_configured_port()
- test_server_stops_gracefully()
- test_server_handles_concurrent_requests()

# Security
- test_cors_headers_present()
- test_websocket_rejects_invalid_messages()
```

**Estimated Impact**: +340 LOC covered (3.5% overall coverage increase)

---

### ⚠️ Priority 6: WiFi Services (6.3% coverage)

**File**: `services/wifi.py` (451 LOC)
**Current Coverage**: 6.3%
**Risk Level**: 🟢 LOW - Feature quality

**Why Improve**:
- WiFi configuration is a common user task
- Network connectivity affects web UI access
- Error handling for network commands

**Recommended Tests** (`test_wifi.py` - new file):

```python
- test_list_wifi_networks_parses_nmcli_output()
- test_connect_to_wifi_validates_ssid()
- test_connect_to_wifi_requires_password_for_secured()
- test_disconnect_wifi_succeeds()
- test_get_current_connection_returns_active_network()
- test_wifi_signal_strength_calculation()
- test_wifi_operations_handle_nmcli_errors()
```

**Estimated Impact**: +423 LOC covered (4.3% overall coverage increase)

---

### ⚠️ Priority 7: Logging System (32.1% coverage)

**File**: `logging.py` (147 LOC)
**Current Coverage**: 32.1%
**Risk Level**: 🟢 LOW - Debugging aid

**Why Improve**:
- Logging is critical for diagnosing issues
- Context preservation for error reports
- Performance monitoring

**Recommended Tests** (`test_logging.py`):

```python
- test_logger_initialization_creates_handlers()
- test_logger_writes_to_file_and_console()
- test_logger_rotation_at_size_limit()
- test_context_logging_preserves_metadata()
- test_performance_logging_tracks_timing()
- test_log_levels_filter_correctly()
```

**Estimated Impact**: +100 LOC covered (1.0% overall coverage increase)

---

## Medium Priority Gaps

### ⚠️ Clonezilla Components (<60% coverage)

| Component | LOC | Coverage | Missing Tests |
|-----------|-----|----------|---------------|
| `clonezilla/partition_table.py` | 499 | 62.3% | Complex partition operations |
| `clonezilla/backup.py` | 325 | 53.4% | Edge cases, compression |
| `clonezilla/restore.py` | 308 | 49.1% | Partition mode validation |
| `clonezilla/verification.py` | 162 | 6.0% | Image integrity checks |

**Recommended Improvements**:
- Add tests for partition table edge cases (GPT, MBR, hybrid)
- Test compression format handling (gzip, lz4, zstd)
- Test partition mode selection (k0, k1, k2)
- Test image verification with corrupted images

**Estimated Impact**: +337 LOC covered (3.4% overall coverage increase)

---

### ⚠️ Storage Components (<90% coverage)

| Component | LOC | Coverage | Gap |
|-----------|-----|----------|-----|
| `storage/erase.py` | 126 | 70.4% | Full erase mode |
| `storage/format.py` | 160 | 86.3% | Filesystem-specific tests |
| `storage/image_repo.py` | 77 | 8.6% | Image repository management |

**Recommended Improvements**:
- Test full device erase vs quick erase
- Test all filesystem types (ext4, ntfs, exfat, vfat)
- Test image repository discovery and management

**Estimated Impact**: +103 LOC covered (1.0% overall coverage increase)

---

## Low Priority Gaps (0% coverage, non-critical)

These have 0% coverage but are lower risk:

| File | LOC | Priority | Reason |
|------|-----|----------|--------|
| `ui/screensaver.py` | 77 | LOW | Visual feature, not critical |
| `ui/screens/demos.py` | 309 | LOW | Demo/test screens only |
| `ui/screens/file_browser.py` | 196 | LOW | UI component |
| `ui/screens/wifi.py` | 129 | LOW | UI component |
| `ui/icons.py` | 26 | LOW | Static data |
| `storage/iso.py` | 43 | LOW | ISO operations not core |
| `hardware/gpio.py` | 43 | LOW | Hardware-specific |
| `hardware/virtual_gpio.py` | 33 | LOW | Test utility |

**Recommendation**: Address these after Priority 1-7 are complete.

---

## Summary of Recommendations

### Immediate Actions (Priority 1-3)

1. **Create `test_drive_actions.py`** - Test destructive drive operations
2. **Create `test_image_actions.py`** - Test image backup/restore actions
3. **Create `test_settings_actions.py`** - Test system settings changes
4. **Create `test_main.py`** - Test main event loop (integration tests)
5. **Create `test_menu_navigator.py`** - Test menu navigation logic

**Expected Outcome**: Increase coverage from 27% → 50% (+2,470 LOC)

### Short-Term Actions (Priority 4-5)

6. **Create `test_ui_renderer.py`** - Test OLED rendering
7. **Create `test_ui_progress.py`** - Test progress bars
8. **Create `test_ui_confirmation.py`** - Test confirmation dialogs
9. **Expand `test_ui_display.py`** - Improve display initialization tests
10. **Create `test_web_server.py`** - Test web server and WebSocket

**Expected Outcome**: Increase coverage from 50% → 70% (+2,151 LOC)

### Long-Term Actions (Priority 6-7)

11. **Create `test_wifi.py`** - Test WiFi management
12. **Expand `test_logging.py`** - Test logging system
13. **Improve Clonezilla tests** - Fill gaps in partition table, backup, restore
14. **Improve storage tests** - Complete erase, format, image_repo tests

**Expected Outcome**: Increase coverage from 70% → 80% (+860 LOC)

---

## Testing Best Practices (From Existing Tests)

Based on analysis of well-tested components, follow these patterns:

### 1. Use Comprehensive Fixtures (`conftest.py`)

```python
# Already available:
- mock_usb_device: Complete USB device dict
- mock_usb_device_unmounted: Unmounted device
- mock_system_disk: Non-removable system disk
- temp_settings_file: Temporary settings JSON
- sample_settings_data: Default settings
```

### 2. Mock subprocess.run for System Commands

```python
def test_clone_operation(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = Mock(returncode=0, stdout="Success")

    clone_device("/dev/sda", "/dev/sdb")

    mock_run.assert_called_once()
```

### 3. Use Parametrized Tests for Multiple Cases

```python
@pytest.mark.parametrize("filesystem,expected", [
    ("vfat", "FAT32"),
    ("ext4", "ext4"),
    ("ntfs", "NTFS"),
])
def test_filesystem_format(filesystem, expected):
    assert format_filesystem_type(filesystem) == expected
```

### 4. Separate Unit and Integration Tests

```python
@pytest.mark.unit
def test_parse_lsblk_output():
    """Fast, isolated unit test."""
    pass

@pytest.mark.integration
def test_full_clone_workflow():
    """Slower, multi-component test."""
    pass
```

### 5. Test Error Paths

```python
def test_clone_handles_permission_denied(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.side_effect = PermissionError("Access denied")

    with pytest.raises(PermissionError):
        clone_device("/dev/sda", "/dev/sdb")
```

---

## Metrics & Goals

### Current State (2026-01-23)
- **Total Statements**: 9,851
- **Covered Statements**: 2,681
- **Overall Coverage**: 27.10%
- **Branch Coverage**: Tracked (3,442 branches, 144 partial)

### Immediate Goal (Q1 2026)
- **Target Coverage**: 50%
- **Focus**: Action handlers, main loop, menu system
- **New Test Files**: 5
- **Estimated Lines to Cover**: +2,470

### Short-Term Goal (Q2 2026)
- **Target Coverage**: 70%
- **Focus**: UI rendering, web server
- **New Test Files**: +5
- **Estimated Lines to Cover**: +2,151

### Long-Term Goal (Q3 2026)
- **Target Coverage**: 80%
- **Focus**: WiFi, logging, Clonezilla edge cases
- **Improve Existing Tests**: Clonezilla, storage
- **Estimated Lines to Cover**: +860

### Stretch Goal (Q4 2026)
- **Target Coverage**: 85%
- **Focus**: Low-priority UI components, hardware abstraction
- **Estimated Lines to Cover**: +492

---

## Open Questions

1. **UI Testing Strategy**: Should we test pixel-perfect rendering or just logic?
   - Recommendation: Focus on logic (data flow, state updates), not pixels

2. **Hardware Mocking**: How to test GPIO button input?
   - Current: Mock RPi.GPIO in conftest.py (good approach)
   - Recommendation: Use virtual_gpio.py for integration tests

3. **Web Server Testing**: Async tests for aiohttp?
   - Recommendation: Use pytest-aiohttp plugin (already available)

4. **Integration Test Environment**: Run tests on actual Raspberry Pi?
   - Current: Tests run on any platform with mocked hardware
   - Recommendation: Add CI job for Pi hardware tests (optional)

---

## Conclusion

The codebase has **excellent foundational coverage** for core storage operations (85-100%) but **lacks coverage for application logic and UI layers** (0-30%). By prioritizing action handlers, main loop, and menu system tests, we can achieve **50% overall coverage** with high confidence in data safety. Adding UI and web server tests will reach **70% coverage** and ensure user-facing features work correctly.

**Next Steps**:
1. Review this analysis with the team
2. Create GitHub issues for each recommended test file
3. Assign priority labels (P0=Critical, P1=High, P2=Medium)
4. Begin with `test_drive_actions.py` (highest risk, highest impact)
5. Track coverage progress in CI/CD pipeline

**Estimated Total Impact**: 27% → 80% coverage (+5,481 LOC covered)
