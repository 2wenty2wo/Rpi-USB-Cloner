# Changelog

> **Purpose**: Historical record of improvements and bug fixes for the Raspberry Pi USB Cloner.

---

## 2026-01-29: Status Bar, Toggle Icons & Menu Icon Preview

### Status Bar System
- New `ui/status_bar.py` module for system tray-like status indicators
- Displays WiFi, Bluetooth, Web Server status, and drive counts (U#/R#)
- Uses 7px icons for WiFi (`7px-wifi.png`), Bluetooth (`7px-bluetooth.png`), and Web Server (`7px-pointer.png`)
- Master toggle and individual icon toggles in Settings -> Display -> Status Bar
- `StatusIndicator` dataclass with priority-based ordering (lower priority = rightmost)
- New settings: `status_bar_enabled`, `status_bar_wifi_enabled`, `status_bar_bluetooth_enabled`, `status_bar_web_enabled`, `status_bar_drives_enabled`

### Toggle Switch Icons
- New `ui/toggle.py` module providing visual ON/OFF toggle switches
- 12x5 pixel toggle images (`toggle-on.png`, `toggle-off.png`)
- `format_toggle_label()` adds markers like `"SCREENSAVER {{TOGGLE:ON}}"`
- Renderer detects markers and replaces them with toggle images
- Used across settings menus for boolean options (screensaver, web server, screenshots, etc.)

### Menu Icon Preview
- New setting `menu_icon_preview_enabled` to show enlarged (24px) icons
- When enabled, displays the selected menu item's icon in the empty right side of the display
- Toggle available in Settings -> Advanced -> Develop

### New Menu Structure
- Settings -> Display -> Status Bar submenu with individual toggles
- Improved menu item labels with inline toggle graphics

### New Tests
- `tests/test_status_bar.py` - Comprehensive status bar tests
- `tests/test_toggle.py` - Toggle icon tests

---

## 2026-01-29: Screensaver Refactor & Menu Reorganization

### Naming Consistency
- Renamed all `sleep`-related variables to `screensaver` equivalents for clarity
- Updated timeout references and settings handling across multiple modules
- `app/state.py`, `main.py`, `menu_builders.py`, `ui_actions.py` all use consistent naming

### Settings Menu Reorganization
- **New Structure**: SETTINGS -> CONNECTIVITY, DISPLAY, SYSTEM, ADVANCED
- **CONNECTIVITY**: WiFi settings, Web Server toggle
- **DISPLAY**: Screensaver settings (enable/disable, timeout, mode, GIF selection)
- **SYSTEM**: System Info, Update, About, Power submenu
- **ADVANCED**: Developer tools (screens demo, icons demo, transitions)
- Replaced flat settings list with organized submenus

### Idle Menu Animation
- Added animated menu selector when idle (visual feedback during inactivity)
- `menu_activity_time` tracking in main loop
- Configurable animation render tick

### Transition Settings
- Refactored to use constants from `ui/constants.py` for default values
- `DEFAULT_SCROLL_REFRESH_INTERVAL` for backward compatibility
- Improved maintainability across modules

### Device Labels
- Now uses child partition labels for more descriptive device names
- Phase 1 of Human-Readable Device Labels complete

### Bug Fixes
- Fixed screensaver "Select GIF" showing when mode is "Random" (now only shows when "Selected")
- Fixed idle animation render tick timing
- Fixed idle menu animation refresh

---

## 2026-01-28: Format Safety & Device Lock Improvements

### Format Safety Hardening
- Comprehensive format safety checks added
- Proper partition unmounting before format operations
- udev rule approach for preventing automount interference
- Exclusive device lock (`fcntl.flock`) during critical operations
- Handles mkfs spawn failures gracefully

### Files Modified
- `storage/format.py` - Simplified to ~280 lines with robust safety
- Multiple test fixes for format safety validation

### Web UI Device Lock (CRITICAL)

**Problem**: Disk operations (format, erase, clone) failed with "device busy" errors when the web UI was running.

**Root Cause**: The web UI has two WebSocket handlers that scan USB filesystems every 2 seconds:
- `handle_devices_ws` -> calls `find_image_repos()` -> `flag_path.exists()` on mounted USB
- `handle_images_ws` -> calls `list_clonezilla_images()` -> `glob("*.iso")`, `glob("*.bin")` on USB

These filesystem operations keep devices "in use" from the kernel's perspective.

**Solution**: Added `storage/device_lock.py` module with a `device_operation()` context manager:
```python
from rpi_usb_cloner.storage.device_lock import device_operation, is_operation_active

with device_operation("sdb"):
    # Perform format/erase/clone - web UI scanning is paused
    ...
```

**Files Modified**:
- `storage/device_lock.py` (NEW) - Thread-safe lock module
- `storage/format.py` - Wraps `format_device()` with lock
- `storage/clone/erase.py` - Wraps `erase_device()` with lock
- `storage/clone/operations.py` - Wraps `clone_device()` and `clone_device_smart()` with lock
- `web/server.py` - Modified handlers to check `is_operation_active()` and use cached data

> **Important**: When adding new filesystem scanning to the web UI, always check `is_operation_active()` first.

---

## 2026-01-26: Web UI & Image Repository Enhancements

### New Features
- **Image Sizes in Repo List**: Images now display their sizes in the repository listing
- **Free Space Badge**: Improved badge contrast for better readability
- **Repository Usage Charts**: Added ApexCharts integration for visualizing repo storage usage
- **Image Repo Divider**: Added visual divider after chart legend for cleaner UI
- **Domain Models**: Introduced type-safe domain objects (`Drive`, `DiskImage`, `ImageRepo`, `CloneJob`)

### Architecture
- New `domain/models.py` with dataclasses for type-safe operations
- New `storage/image_repo.py` for centralized image repository management
- New `storage/imageusb/` module for ImageUSB .BIN file support
- `CloneJob.validate()` now enforces source != destination check

### Bug Fixes
- Fixed image size refresh in WebSocket to avoid blocking main thread
- Removed duplicate chart labels from image repo display

---

## 2026-01-25: Logging System - Callback-Free Migration

### Infrastructure Changes
- **100% LoggerFactory Coverage**: All modules now use `LoggerFactory` directly (no callbacks)
- **Removed Callback Infrastructure**: Eliminated `configure_progress_logger()` and `configure_display_helpers()` functions
- **Cleaned Compatibility Layer**: Removed obsolete exports from `storage/clone/__init__.py` and `storage/clone.py`

### Modules Migrated
- `storage/clone/progress.py` - Progress monitoring now uses LoggerFactory
- `storage/clone/command_runners.py` - Command execution logging migrated
- `ui/display.py` - Display module uses `LoggerFactory.for_menu()`
- `storage/mount.py` - Mount utilities use `LoggerFactory.for_system()`

### Impact
- ~170+ logging calls converted from callbacks/print to loguru
- All application logging now appears in Web UI
- LOGGING_IMPROVEMENTS.md updated to version 2.1.0

---

## 2026-01-24: UI Enhancements & Test Coverage

### New Features
- **Menu Transitions**: Added slide transitions for menu lists with configurable transition speed settings
- **CREATE REPO DRIVE**: New menu option to mark drives as image repositories (creates flag file)
- **Font Optimization**: Removed unused font files to reduce repository size
- **Menu Reorganization**: Refactored menu structure for better organization (Option A implementation)

### Test Coverage
- Added comprehensive action handler tests (+38 tests)
- Coverage increased by +7.47% for action modules
- Total test files: 32
- See `TEST_COVERAGE_ANALYSIS.md` for detailed coverage report

### Bug Fixes
- Fixed multiple partition mounting for repository detection
- Corrected CLONE menu label rendering (plain text and Lucide icons)
- Resolved mypy type checking issues
- Fixed ruff lint violations
- Improved menu transition footer display

---

## 2026-01-23: Unmount Error Handling

### Previous Issue
`unmount_device()` silently swallowed exceptions, which could lead to data corruption.

### Resolution
The function has been significantly improved with:
- `raise_on_failure` parameter for explicit error handling
- Returns `bool` to indicate success/failure
- Raises `UnmountFailedError` when `raise_on_failure=True`
- New `unmount_device_with_retry()` function with retry logic and lazy unmount support
- Proper logging of failed mountpoints
- Error handler integration for UI notifications

### New Signature
```python
def unmount_device(device: dict, raise_on_failure: bool = False) -> bool:
    """Returns True if successful, False otherwise. Raises UnmountFailedError if raise_on_failure=True."""

def unmount_device_with_retry(device: dict, log_debug: Optional[Callable] = None) -> tuple[bool, bool]:
    """Returns (success, used_lazy_unmount) with automatic retry logic."""
```
