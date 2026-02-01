# Test Coverage Analysis & Improvement Plan

**Date**: 2026-02-01
**Current Overall Coverage**: ~51.6% (pytest --cov=rpi_usb_cloner)
**Files Analyzed**: 93 Python files in `rpi_usb_cloner/`
**Test Files**: 68 test modules
**Test Results**: ~1,721 passed, 52 skipped (POSIX-only), 0 failed

## Recent Updates (2026-02-01) - Coverage Improvements - Round 3

✅ **Added Clonezilla Verification Tests** (+29 tests):
- `tests/test_clonezilla_verification_extra.py` - Comprehensive verification tests
  - `get_verify_hash_timeout()` - settings handling edge cases (6 tests)
  - `compute_image_sha256()` - compressed images, gzip, zstd, timeouts (11 tests)
  - `compute_partition_sha256()` - partition hash computation (9 tests)
  - `verify_restored_image()` - edge cases and error handling (10 tests)
  - Coverage: `storage/clonezilla/verification.py` 42.80% → 91.60% (+48.8%)

✅ **Added UI Transitions Tests** (+16 tests):
- `tests/test_ui_transitions.py` - Slide transition animation tests
  - `render_slide_transition()` - blocking mode with timing (2 tests)
  - `generate_slide_transition()` - generator-based transitions (14 tests)
  - Coverage: `ui/transitions.py` 12.07% → 100.00% (+87.93%)

**New Test Modules Added**:
- `tests/test_clonezilla_verification_extra.py` (29 tests)
- `tests/test_ui_transitions.py` (16 tests)

## Recent Updates (2026-02-01) - Coverage Improvements - Round 2

✅ **Added UI Logs Screen Tests** (+7 tests):
- `tests/test_ui_screens_logs.py` - Logs screen rendering tests
  - `show_logs()` - log buffer handling, pagination, button navigation
  - Coverage: `ui/screens/logs.py` 12% → 30%

✅ **Added UI Info Screen Tests** (+16 tests):
- `tests/test_ui_screens_info.py` - Info and paginated screen tests
  - `render_info_screen()` - basic rendering, icons, custom pages
  - `render_key_value_screen()` - key-value display
  - `wait_for_paginated_input()` - button navigation
  - `wait_for_scrollable_key_value_input()` - scrolling navigation
  - Coverage: `ui/screens/info.py` 4% → 40%

✅ **Added File Browser Tests** (+12 tests):
- `tests/test_ui_screens_file_browser.py` - File browser screen tests
  - `FileItem` class - file/directory representation
  - `_get_line_height()` - font height calculation
  - `_get_available_locations()` - USB and repo discovery
  - `_list_directory()` - directory listing with filtering
  - `_render_browser_screen()` - screen rendering
  - `show_file_browser()` - navigation and interaction
  - Coverage: `ui/screens/file_browser.py` 7% → 55%

✅ **Added ImageUSB Detection Tests** (+18 tests):
- `tests/test_imageusb_detection.py` - ImageUSB file validation tests
  - `is_imageusb_file()` - signature detection
  - `validate_imageusb_file()` - full validation
  - `get_imageusb_metadata()` - metadata extraction
  - Coverage: `storage/imageusb/detection.py` 81% → 89%

✅ **Added Menu Settings Actions Tests** (+32 tests):
- `tests/test_menu_actions_settings.py` - Settings menu action tests
  - `_run_operation()` - operation flag management
  - All 32 settings action wrappers tested
  - Coverage: `menu/actions/settings.py` 47% → 100%

## Previous Updates (2026-02-01) - Coverage Improvements - Round 1

✅ **Added ISO Image Tests** (+13 tests):
- `tests/test_iso.py` - ISO image writing tests
  - `restore_iso_image()` - root checks, file validation, device size checks
  - `_get_blockdev_size_bytes()` - device size retrieval
  - `_get_device_size_bytes()` - size calculation with fallbacks
  - Coverage: `storage/iso.py` 16% → 37%

✅ **Added ImageUSB Restore Tests** (+15 tests):
- `tests/test_imageusb_restore.py` - ImageUSB .BIN restoration tests
  - `restore_imageusb_file()` - validation, permission checks, device checks
  - `restore_imageusb_file_simple()` - simple API wrapper
  - Error handling for various failure modes
  - Coverage: New comprehensive test coverage for ImageUSB restore

✅ **Added WiFi Service Tests** (+22 tests):
- `tests/test_wifi_extra.py` - Additional WiFi service tests
  - `_format_command()` - command formatting with redactions
  - `_nmcli_unescape()` - nmcli output parsing
  - `_is_valid_ssid()` - SSID validation
  - `_split_nmcli_line()` - line splitting with escapes
  - `list_wifi_interfaces()` - interface detection
  - `get_ip_address()` - IP address retrieval
  - Coverage: `services/wifi.py` 63% → 75%

✅ **Added Image Repository Tests** (+23 tests):
- `tests/test_image_repo_more.py` - Extended image repo tests
  - `_iter_partitions()` - partition iteration
  - `_resolve_mountpoint()` - mountpoint resolution
  - `find_image_repos()` - repository discovery
  - `list_clonezilla_images()` - image listing
  - `_sum_tree_bytes()` - directory size calculation
  - `get_repo_usage()` - repository usage statistics
  - Coverage: `storage/image_repo.py` 70% → 77%

✅ **Added UI Screen Tests** (+11 tests):
- `tests/test_ui_screens_error.py` - Error screen rendering tests
- `tests/test_ui_screens_status.py` - Status screen rendering tests
  - `render_error_screen()` - error display
  - `render_status_screen()` - status display
  - `show_coming_soon()` - coming soon screen
  - `wait_for_ack()` - button acknowledgment
  - Coverage: `ui/screens/status.py` 28% → 100%

## Recent Updates (2026-02-01) - App Module Coverage

✅ **Added App Module Tests** (+83 tests):
- `tests/test_app_context.py` - AppContext and LogEntry tests (20 tests)
  - LogEntry creation, serialization, data isolation
  - AppContext state management, log buffering
  - Coverage: `app/context.py` 64% → ~95%
  
- `tests/test_app_drive_info.py` - Drive info display tests (14 tests)
  - `get_device_status_line()` with various device states
  - `render_drive_info()` screen rendering
  - Coverage: `app/drive_info.py` 6% → ~90%
  
- `tests/test_app_menu_builders.py` - Menu builder tests (21 tests)
  - `build_device_items()`, `build_connectivity_items()`
  - `build_display_items()`, `build_screensaver_items()`
  - `build_develop_items()`, `build_status_bar_items()`
  - Coverage: `app/menu_builders.py` 16% → ~85%

✅ **Enhanced Services Tests** (+21 tests):
- `tests/test_services_drives_extra.py` - Additional drive service tests
  - `USBSnapshot` dataclass, `get_usb_snapshot()`
  - `list_media_drives()`, `list_raw_usb_disk_names()`
  - `list_usb_disks_filtered()`, repo cache behavior
  - Coverage: `services/drives.py` 72% → ~85%

✅ **Added Image Repo Tests** (+7 tests):
- `tests/test_image_repo_extra.py` - Image repository tests
  - `_is_temp_clonezilla_path()` temp file detection
  - `get_image_size_bytes()` edge cases
  - Coverage: `storage/image_repo.py` 70% → ~75%

## Recent Updates (2026-02-01) - Platform Fixes

✅ **Fixed Platform-Specific Tests**:
- Fixed **24 tests** that were failing on Windows due to POSIX-specific functions or platform differences
- Added `@pytest.mark.skipif()` decorators for tests requiring:
  - `os.geteuid()` - root permission checks (14 tests)
  - `os.statvfs()` - filesystem space checks (7 tests)
  - Symlink creation (1 test on Windows without admin)
  - Path separator issues (2 tests)
- All tests now pass on Linux; Windows shows expected skips for POSIX features

✅ **Test Count Update**:
- **1,449 tests passed**, 29 skipped (platform-specific), 0 failed
- Test inventory: **50 test modules** (7 new modules added)
- Overall coverage: **45.20%** (+1.28% improvement from previous 43.92%)

✅ **New Test Modules Added**:
- `tests/test_status_bar.py` - Status bar UI tests (93.55% coverage)
- `tests/test_toggle.py` - Toggle switch UI tests (93.18% coverage)
- `tests/test_transfer.py` - Transfer operations tests
- `tests/test_peer_transfer_client.py` - HTTP transfer client tests
- `tests/test_peer_transfer_server.py` - HTTP transfer server tests
- `tests/test_discovery.py` - mDNS peer discovery tests
- `tests/test_wifi_direct.py` - WiFi Direct P2P tests

✅ **Test inventory highlights** (current module names):
- **App Module Tests** (new):
  - `tests/test_app_context.py` - AppContext and LogEntry dataclass tests
  - `tests/test_app_drive_info.py` - Drive info display tests
  - `tests/test_app_menu_builders.py` - Dynamic menu builder tests
- `tests/test_actions_drive.py`, `tests/test_actions_image.py`,
  `tests/test_actions_settings.py`, `tests/test_actions_import.py`
- `tests/test_clone.py`, `tests/test_clone_models.py`,
  `tests/test_clone_operations.py`, `tests/test_clone_progress.py`,
  `tests/test_clone_safety.py`
- `tests/test_clonezilla_backup.py`, `tests/test_clonezilla_restore.py`,
  `tests/test_clonezilla_verification.py`, `tests/test_clonezilla_models.py`,
  `tests/test_clonezilla_file_utils.py`, `tests/test_clonezilla_partition_table.py`,
  `tests/test_clonezilla_image_discovery.py`
- `tests/test_domain_models.py`, `tests/test_devices.py`, `tests/test_logging.py`
- `tests/test_services_drives.py`, `tests/test_services_drives_extra.py`
- `tests/test_transfer.py`, `tests/test_transfer_services.py`
- `tests/test_discovery.py`, `tests/test_peer_transfer_client.py`, 
  `tests/test_peer_transfer_server.py`, `tests/test_wifi_direct.py`
- `tests/test_status_bar.py`, `tests/test_toggle.py`
- `tests/test_ui_renderer.py`, `tests/test_ui_progress.py`,
  `tests/test_ui_confirmation.py`, `tests/test_ui_display.py`,
  `tests/test_ui_keyboard.py`
- `tests/test_web_server.py`, `tests/test_main.py`, `tests/test_menu_navigator.py`,
  `tests/test_system_health.py`

✅ **New coverage improvements**:
- Added targeted helper tests for action handler selection/validation logic
- Added logging setup/context filtering tests (`tests/test_logging.py`)
- Added Wi-Fi nmcli parsing and error handling tests (`tests/test_wifi.py`)
- Added comprehensive Image Transfer service tests (106 tests, 5 modules)

✅ **Completed tests** (Image Transfer feature - 2026-01-31):
- `services/transfer.py` - 95.3% coverage (`test_transfer_services.py`)
- `services/discovery.py` - 79.1% coverage (`test_discovery.py`)
- `services/peer_transfer_server.py` - 60.5% coverage (`test_peer_transfer_server.py`)
- `services/peer_transfer_client.py` - 47.6% coverage (`test_peer_transfer_client.py`)
- `services/wifi_direct.py` - 71.7% coverage (`test_wifi_direct.py`)

⏳ **Pending tests**:
- `actions/network_transfer_actions.py` - Network transfer UI
- `actions/wifi_direct_actions.py` - WiFi Direct UI


## Recent Updates (2026-01-24)

✅ **Added Action Handler Tests** (+38 tests, +7.47% coverage):
- `tests/test_actions_drive.py` - 17 tests covering drive action helpers
- `tests/test_actions_image.py` - 10 tests covering image action helpers
- `tests/test_actions_settings.py` - 34 tests covering settings action helpers

**Coverage improvements**:
- `actions/drive_actions.py`: 0% → 20.16% (helper functions tested)
- `actions/image_actions.py`: 0% → 8.94% (helper functions tested)
- `actions/settings/system_utils.py`: 14.81% → 44.97% (+30%)
- `actions/settings/system_power.py`: 24.11% → 28.57% (+4%)
- `actions/settings/update_manager.py`: 9.58% → 17.15% (+7%)

**Key findings**: Many action functions have complex GPIO polling loops that are difficult to unit test. Functions would benefit from refactoring to separate business logic from UI/GPIO concerns.

---

## Executive Summary

The codebase has **strong test coverage** (≥80%) for core storage and cloning operations but **lacks coverage** for UI, actions, menu system, web server, and main application logic. Out of 93 files:

- ✅ **48 files** (52%) have ≥80% coverage (excellent)
- ⚠️ **35 files** (38%) have <50% coverage (needs improvement)
- ❌ **2 files** (2%) have 0% coverage (critical gap)

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
| **Domain Models** | 99.0% | `test_domain_models.py` (482 LOC) | All data classes tested |
| **Storage Validation** | 97.4% | `test_validation.py` (424 LOC) | Input validation well-covered |
| **Clone Progress** | 95.8% | `test_clone_progress.py` (446 LOC) | Progress tracking solid |
| **Clone Verification** | 92.4% | `test_verification.py` (407 LOC) | SHA256 verification tested |
| **Services/Drives** | 88.3% | `test_services_drives.py` (439 LOC) | Drive service layer good |
| **Devices** | 91.8% | `test_devices.py` (672 LOC) | USB detection well-tested |
| **Command Runners** | 90.5% | `test_command_runners.py` (410 LOC) | Command execution covered |
| **Clone Operations** | 83.8% | `test_clone_operations.py` (620 LOC) | Core cloning logic tested |
| **Format** | 84.5% | `test_format.py` (629 LOC) | Formatting operations good |
| **Mount** | 86.6% | `test_mount.py` (476 LOC) | Mount/unmount tested |

**Key Takeaways**:
- Storage layer has excellent coverage (83-100%)
- Clonezilla utilities have mixed coverage (partition table ~62%, restore ~49%)
- Safety validations are comprehensive
- Mock fixtures in `conftest.py` are robust

---

## Critical Coverage Gaps

### ⚠️ Priority 1: Action Handlers (5-20% coverage, PARTIALLY ADDRESSED)

**Risk Level**: 🟡 MEDIUM - Helper functions tested, main operations still need work

| File | LOC | Coverage | Status | Risk |
|------|-----|----------|--------|------|
| `actions/drive_actions.py` | 745 | 22.43% | ⚠️ Helpers tested | 🔴 Data loss risk |
| `actions/image_actions.py` | 819 | 11.20% | ⚠️ Helpers tested | 🔴 Data loss risk |
| `actions/settings/update_manager.py` | 328 | 5.20% | ❌ Not tested | 🟡 System stability |
| `actions/settings/system_utils.py` | 137 | 14.75% | ❌ Not tested | 🟡 System stability |
| `actions/settings/ui_actions.py` | 153 | 15.64% | ❌ Not tested | 🟢 Low risk |
| `actions/settings/system_power.py` | 90 | 16.36% | ❌ Not tested | 🟡 System stability |

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

**Completed Tests** (`test_actions_drive.py` - 17 tests):
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

**Completed Tests** (`test_actions_image.py` - 10 tests):
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

3. **Settings Actions** (`test_actions_settings.py`) - 34 tests:
   ```python
   # System Utils (pure logic)
   - test_validate_command_args_* (3 tests)
   - test_format_command_output_* (2 tests)
   - test_is_git_repo_* (2 tests)
   - test_is_dubious_ownership_error_* (2 tests)
   - test_parse_git_progress_ratio_* (3 tests)
   - test_get_app_version_* (3 tests)
   
   # Update Manager (pure logic)
   - test_extract_error_hint_* (3 tests)
   - test_truncate_oled_line_* (2 tests)
   
   # System Power (pure logic)
   - test_build_power_action_prompt_* (1 test)
   - test_confirm_power_action_* (1 test)
   
   # UI Actions (pure logic)
   - test_ui_settings_persist_to_config (1 test)
   - test_valid_restore_partition_modes_accepted (4 parametrized tests)
   - test_invalid_restore_partition_mode_rejected (1 test)
   - test_valid_transition_settings_accepted (3 parametrized tests)
   - test_invalid_transition_settings_rejected (1 test)
   
   # Integration Tests
   - test_updates_require_confirmation (1 test)
   - test_restart_requires_confirmation (1 test)
   - test_shutdown_requires_confirmation (1 test)
   ```

**Estimated Impact**: +1,976 LOC covered (~18% overall coverage increase)

---

### ⚠️ Priority 2: Main Application Loop (6.49% coverage)

**File**: `main.py` (391 LOC)
**Coverage**: 6.49%
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

### ✅ Priority 3: Menu System (Covered for navigation/model)

**Files**:
- `menu/navigator.py` (96 LOC) - Covered by `test_menu_navigator.py` (84.13%)
- `menu/model.py` (17 LOC) - Covered at 94.12%
- `menu/definitions/*.py` (33 LOC total) - 100% coverage

**Status**:
- `menu/navigator.py` has a comprehensive test suite `tests/test_menu_navigator.py` with 17 tests covering initialization, navigation, bounds checking, scrolling logic, and stack management.

---

### ✅ Priority 4: UI Rendering (tests added; coverage improving)

**Files**:
- `ui/renderer.py` (220 LOC) - 73.81% ⭐ Critical file
- `ui/menus.py` (532 LOC) - 8.67%
- `ui/screens/progress.py` (121 LOC) - 70.81%
- `ui/screens/confirmation.py` (282 LOC) - 13.24%
- `ui/screens/error.py` (41 LOC) - 6.12%
- `ui/screens/status.py` (24 LOC) - 28.12%
- `ui/keyboard.py` (298 LOC) - 6.76%
- `ui/display.py` (533 LOC) - 15.34% (LOW)

**Why Important**:
- User feedback depends on correct rendering
- Progress bars must accurately reflect operation status
- Error messages must be visible
- Confirmation dialogs prevent accidental data loss

**Added Tests** (`test_ui_*.py`):

1. **Renderer** (`test_ui_renderer.py`) ✅:
   ```python
   - test_render_menu_displays_all_items()
   - test_render_menu_highlights_selected_item()
   - test_render_menu_shows_scrollbar_for_long_lists()
   - test_render_menu_truncates_long_text()
   ```

2. **Progress Screen** (`test_ui_progress.py`) ✅:
   ```python
   - test_progress_bar_renders_correctly()
   - test_progress_shows_percentage()
   - test_progress_calculates_eta_correctly()
   - test_progress_handles_zero_total_gracefully()
   ```

3. **Confirmation Screen** (`test_ui_confirmation.py`) ✅:
   ```python
   - test_confirmation_dialog_defaults_to_no()
   - test_confirmation_dialog_accepts_yes()
   - test_confirmation_checkbox_list_tracks_selections()
   - test_confirmation_multiline_text_wraps()
   ```

4. **Display** (`test_ui_display.py`) (still recommended):
   ```python
   - test_display_initialization_detects_i2c_address()
   - test_display_initialization_falls_back_to_virtual()
   - test_display_context_loads_fonts()
   - test_display_context_loads_icons()
   ```

**Estimated Impact**: Reflected in latest coverage run (overall 43.92%)

**Note**: UI tests may require:
- Mocking `luma.oled` device (already done in `conftest.py`)
- Image comparison for pixel-perfect rendering (optional)
- Focus on logic rather than pixel output

---

### ✅ Priority 5: Web Server (tests added; coverage improving)

**File**: `web/server.py` (402 LOC)
**Coverage**: 28.26% (after new async tests)
**Risk Level**: 🟡 MEDIUM - Security and stability

**Why Important**:
- Web UI provides remote access to OLED display
- WebSocket streaming must handle disconnects gracefully
- System health monitoring exposed via API
- Potential security risks (CORS, input validation)

**Added Tests** (`test_web_server.py`) ✅:

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

**Estimated Impact**: Reflected in latest coverage run (overall 43.92%)

---

### ⚠️ Priority 6: WiFi Services (6.66% coverage)

**File**: `services/wifi.py` (451 LOC)
**Current Coverage**: 6.66%
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

### ⚠️ Priority 7: Logging System (39.44% coverage)

**File**: `logging.py` (144 LOC)
**Current Coverage**: 39.44%
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
| `clonezilla/partition_table.py` | 497 | 62.12% | Complex partition operations |
| `clonezilla/backup.py` | 321 | 53.47% | Edge cases, compression |
| `clonezilla/restore.py` | 313 | 49.46% | Partition mode validation |
| `clonezilla/verification.py` | 162 | 6.00% | Image integrity checks |

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
| `storage/erase.py` | 127 | 70.52% | Full erase mode |
| `storage/format.py` | 172 | 84.45% | Filesystem-specific tests |
| `storage/image_repo.py` | 164 | 86.67% | Image repository management |

**Recommended Improvements**:
- Test full device erase vs quick erase
- Test all filesystem types (ext4, ntfs, exfat, vfat)
- Test image repository discovery and management

**Estimated Impact**: +103 LOC covered (1.0% overall coverage increase)

---

## Low Priority Gaps (low coverage, non-critical)

These have low coverage but are lower risk:

| File | LOC | Priority | Reason |
|------|-----|----------|--------|
| `ui/screensaver.py` | 77 | LOW | Visual feature, not critical (16.51%) |
| `ui/screens/demos.py` | 309 | LOW | Demo/test screens only (2.95%) |
| `ui/screens/file_browser.py` | 190 | LOW | UI component (7.14%) |
| `ui/screens/wifi.py` | 128 | LOW | UI component (6.71%) |
| `storage/iso.py` | 44 | LOW | ISO operations not core (16.13%) |
| `hardware/gpio.py` | 43 | LOW | Hardware-specific (33.96%) |
| `hardware/virtual_gpio.py` | 33 | LOW | Test utility (34.15%) |

**Recommendation**: Address these after Priority 1-7 are complete.

---

## Summary of Recommendations

### Immediate Actions (Priority 1-3)

1. ✅ **Created `test_actions_drive.py`** - Test destructive drive operations
2. ✅ **Created `test_actions_image.py`** - Test image backup/restore actions
3. ✅ **Created `test_actions_settings.py`** - Test system settings changes
4. ✅ **Created `test_main.py`** - Test main event loop (integration tests)
5. ✅ **Created `test_menu_navigator.py`** - Test menu navigation logic

**Expected Outcome**: Coverage confirmed at 43.92% overall after `pytest --cov`

### Short-Term Actions (Priority 4-5)

6. ✅ **Created `test_ui_renderer.py`** - Test OLED rendering
7. ✅ **Created `test_ui_progress.py`** - Test progress bars
8. ✅ **Created `test_ui_confirmation.py`** - Test confirmation dialogs
9. 🔜 **Expand `test_ui_display.py`** - Improve display initialization tests
10. ✅ **Created `test_web_server.py`** - Test web server and WebSocket

**Expected Outcome**: Coverage confirmed at 43.92% overall after `pytest --cov`

### Long-Term Actions (Priority 6-7)

11. **Create `test_wifi.py`** - Test WiFi management
12. **Expand `test_logging.py`** - Test logging system
13. **Improve Clonezilla tests** - Fill gaps in partition table, backup, restore
14. **Improve storage tests** - Complete erase, format, image_repo tests

**Expected Outcome**: Progress toward the 50% coverage target (Q1 2026).

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

### Current State (2026-02-01)
- **Total Statements**: 13,016
- **Covered Statements**: ~6,700
- **Overall Coverage**: ~51.6% (+1.7% from new tests in Round 3)
- **Branch Coverage**: Tracked (4,318 branches, ~2,400 covered, 426 partial)
- **Test Files**: 68 modules
- **Tests**: 1,721 passed, 52 skipped (POSIX-only), 0 failed

### Coverage Breakdown by Module

| Module | Coverage | Status |
|--------|----------|--------|
| **Excellent (≥90%)** | | |
| Config/Settings | 100% | ✅ |
| Domain Models | 99.0% | ✅ |
| Storage Validation | 97.4% | ✅ |
| Web/System Health | 98.5% | ✅ |
| UI/Status Bar | 93.6% | ✅ |
| UI/Toggle | 93.2% | ✅ |
| Clone Progress | 95.8% | ✅ |
| Clone Verification | 92.4% | ✅ |
| **Clonezilla/Verification** | 91.6% | ✅ **IMPROVED** |
| **Menu/Actions/Settings** | 100% | ✅ |
| **ImageUSB/Detection** | 89% | ✅ |
| **App/Context** | ~95% | ✅ |
| **Good (70-89%)** | | |
| Clone Operations | 83.8% | ✅ |
| Storage/Format | 83.1% | ✅ |
| Storage/Mount | 80.0% | ✅ |
| **Services/Drives** | ~85% | ✅ |
| **App/Menu Builders** | ~85% | ✅ |
| **App/Drive Info** | ~90% | ✅ |
| **Storage/Image_Repo** | ~77% | ✅ |
| Services/WiFi | ~75% | ✅ |
| Clonezilla/Partition Table | 68.3% | ⚠️ |
| **UI/File_Browser** | ~69% | ⚠️ |
| **UI/Progress** | ~71% | ✅ |
| **Needs Improvement (<50%)** | | |
| Actions/* | 3-22% | ❌ |
| **UI/Info** | ~41% | ⚠️ |
| **UI/Logs** | ~89% | ✅ |
| **UI/Transitions** | 100% | ✅ **IMPROVED** |
| UI/Menus | 8.5% | ❌ |
| UI/Display | 18.0% | ❌ |
| Web/Server | 26.5% | ❌ |
| Main Loop | 0.0% | ❌ |

### Immediate Goal (Q1 2026)
- **Target Coverage**: 55%
- **Focus**: Fix remaining failing tests, improve action handlers
- **New Test Files**: 3-5
- **Estimated Lines to Cover**: +1,200
- **Key Tasks**:
  - ✅ Circular import in actions modules resolved
  - Add tests for `services/wifi.py` (currently 62.6%)
  - Add tests for `storage/image_repo.py` (currently 70.0%)

### Short-Term Goal (Q2 2026)
- **Target Coverage**: 65%
- **Focus**: UI rendering, web server, Clonezilla improvements
- **New Test Files**: +5
- **Estimated Lines to Cover**: +2,500
- **Key Tasks**:
  - Improve `ui/display.py` (currently 17.9%)
  - Improve `web/server.py` (currently 26.5%)
  - Improve `clonezilla/restore.py` (currently 42.6%)

### Long-Term Goal (Q3 2026)
- **Target Coverage**: 75%
- **Focus**: Main loop, action handlers, logging
- **Improve Existing Tests**: Clonezilla, storage, actions
- **Estimated Lines to Cover**: +1,500
- **Key Tasks**:
  - Add tests for `main.py` (currently 0.0%)
  - Improve `actions/*` modules (currently 3-22%)
  - Improve `logging.py` (currently 37.2%)

### Stretch Goal (Q4 2026)
- **Target Coverage**: 80%
- **Focus**: Low-priority UI components, hardware abstraction
- **Estimated Lines to Cover**: +600

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

The codebase has **excellent foundational coverage** for core storage operations (83-100%) but **lacks coverage for application logic and UI layers** (6-30%). Recent fixes have improved cross-platform compatibility, with all tests now passing on Linux and appropriate skips for Windows POSIX limitations.

### Key Achievements (2026-02-01)

✅ **24 platform-specific test failures fixed** (from 27 failed → 3 failed)
✅ **50 test modules** covering all major components
✅ **45.20% overall coverage** (+1.28% from previous 43.92%)
✅ **Core storage operations** at 83-100% coverage
✅ **1,281 tests passing** on Linux (target platform)

### Remaining Challenges

✅ **Circular import** in `actions/image_actions.py` resolved - all tests passing
⚠️ **Action handlers** at 3-22% coverage (needs refactoring for testability)
⚠️ **Main application loop** at 0% coverage (integration testing needed)
⚠️ **UI components** mostly below 20% coverage

### Next Steps

1. ✅ **Immediate**: Fix circular import in `actions/image_actions.py` (resolved - all tests passing)
2. **Q1 2026**: Add tests for action handlers and improve coverage to 55%
3. **Q2 2026**: Add UI rendering tests and improve coverage to 65%
4. **Ongoing**: Track coverage in CI/CD pipeline, maintain >80% for core storage

**Estimated Total Impact**: 45.20% → 80% coverage (+4,500 LOC covered)
