# CLAUDE.md - AI Assistant Guide

> **Purpose**: Essential guidance for AI assistants working on the Raspberry Pi USB Cloner codebase.

**Project**: Raspberry Pi USB Cloner | **Language**: Python 3.8+ | **License**: MIT

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| `docs/UI_STYLE_GUIDE.md` | OLED display layout conventions, screen patterns |
| `docs/COMMON_TASKS.md` | Step-by-step tutorials for adding menus, screens, settings |
| `docs/CHANGELOG.md` | Historical improvements and bug fixes |
| `docs/TESTING.md` | Comprehensive testing guide |
| `docs/LOGGING_IMPROVEMENTS.md` | Logging architecture |

---

## 1. Project Overview

### What It Does
A hardware-based USB cloning solution for Raspberry Pi Zero/Zero 2 with:
- **OLED Display UI**: 128x64 pixel display with 7-button navigation
- **Web UI**: Real-time display streaming via WebSocket (port 8000)
- **Cloning Modes**: Smart (partclone), Exact (dd), Verify (with SHA256)
- **Clonezilla Integration**: Create and restore Clonezilla-compatible images

### Entry Point
```
/home/user/Rpi-USB-Cloner/rpi-usb-cloner.py
    -> rpi_usb_cloner/main.py (main event loop with GPIO polling, USB detection, display rendering)
```

### Running the Application
```bash
sudo -E python3 rpi-usb-cloner.py          # Standard mode
sudo -E python3 rpi-usb-cloner.py --debug  # Debug mode
```

---

## 2. Architecture & Design Patterns

### A. Event-Driven Polling Loop
**Location**: `rpi_usb_cloner/main.py:main()`

```python
while True:
    # 1. Poll GPIO buttons (20ms intervals)
    # 2. Detect USB device changes (2s intervals)
    # 3. Manage screensaver (idle timeout)
    # 4. Render display updates
    # 5. Dispatch actions
```

### B. State Management
Three state containers:

| Container | Location | Purpose |
|-----------|----------|---------|
| **AppContext** | `app/context.py` | Runtime state (current screen, active drive, log buffer) |
| **AppState** | `app/state.py` | Configuration values and timing intervals |
| **MenuNavigator** | `menu/navigator.py` | Menu position via stack, navigation handling |

### C. Service Layer Pattern
**Location**: `services/`

Always use service layer functions instead of direct device operations:
- `services/drives.py` - Drive listing, selection, labels
- `services/wifi.py` - WiFi management

### D. Device Lock Pattern (CRITICAL)
**Location**: `storage/device_lock.py`

Web UI filesystem scanning can cause "device busy" errors during disk operations.

```python
from rpi_usb_cloner.storage.device_lock import device_operation, is_operation_active

# In disk operation code:
with device_operation("sdb"):
    # Web UI scanning is paused during this block
    ...

# In web UI polling code:
if is_operation_active():
    # Skip filesystem scanning, use cached data
    ...
```

> **Important**: When adding new filesystem scanning to the web UI, always check `is_operation_active()` first.

---

## 3. Directory Structure

```
Rpi-USB-Cloner/
├── rpi-usb-cloner.py              # Entry point script
├── rpi_usb_cloner/                # Main package
│   ├── main.py                    # Main event loop ⭐
│   ├── logging.py                 # Loguru logging factory
│   ├── app/                       # Application state (context.py ⭐, state.py)
│   ├── menu/                      # Menu system (navigator.py ⭐, model.py, definitions/)
│   ├── domain/                    # Domain models (models.py ⭐)
│   ├── actions/                   # Action handlers
│   ├── ui/                        # OLED display UI (renderer.py ⭐, screens/, status_bar.py)
│   ├── storage/                   # Storage operations ⭐
│   │   ├── devices.py             # USB device detection
│   │   ├── device_lock.py         # Device operation locking
│   │   ├── clone/                 # Cloning operations
│   │   └── clonezilla/            # Clonezilla integration
│   ├── services/                  # Service layer (drives.py, wifi.py)
│   ├── hardware/                  # GPIO abstraction
│   ├── web/                       # Web UI server (server.py ⭐)
│   └── config/                    # Settings persistence (settings.py ⭐)
├── tests/                         # Test suite (55 test files)
├── docs/                          # Documentation
└── pyproject.toml                 # Project config
```

**⭐ = Critical files to understand first**

---

## 4. Key Conventions

### Code Style
- **Python**: 3.8+ | **Line Length**: 88 chars (Black) | **Type Hints**: Preferred
- **ALWAYS run before committing**: `black . && ruff check --fix . && mypy rpi_usb_cloner`

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Files | `snake_case.py` | `clone_operations.py` |
| Classes | `PascalCase` | `MenuNavigator` |
| Functions | `snake_case()` | `list_usb_disks()` |
| Constants | `UPPER_SNAKE_CASE` | `SETTINGS_PATH` |
| Tests | `test_*.py`, `Test*`, `test_*` | `test_devices.py` |

### Import Order
```python
# 1. Standard library
# 2. Third-party
# 3. First-party (rpi_usb_cloner)
# 4. Local folder (relative imports)
```

### Error Handling
1. **Catch specific exceptions**, not bare `except:`
2. **Display errors to user** via OLED screen (`ui/screens/error.py`)
3. **Log errors** for debugging
4. **Silent failures are dangerous** - always notify user

```python
from rpi_usb_cloner.ui.screens.error import render_error_screen

try:
    result = subprocess.run(["dd", ...], check=True)
except subprocess.CalledProcessError as e:
    render_error_screen(context, "Clone Failed", str(e), exception=e)
    raise
```

### Settings API
**Location**: `config/settings.py` | **Default**: `~/.config/rpi-usb-cloner/settings.json`

```python
from rpi_usb_cloner.config.settings import get_setting, set_setting, get_bool, set_bool, save_settings

screensaver_enabled = get_bool("screensaver_enabled", default=False)
set_setting("screensaver_timeout", 300)
save_settings()
```

### Logging
**Framework**: loguru | **Log Directory**: `~/.local/state/rpi-usb-cloner/logs/`

```python
from rpi_usb_cloner.logging import LoggerFactory, operation_context

log = LoggerFactory.for_clone(job_id="clone-abc123")
log = LoggerFactory.for_usb()
log = LoggerFactory.for_web(connection_id="ws-123")

with operation_context("clone", source="/dev/sda") as log:
    log.info("Progress", percent=50)  # Auto-logs duration on exit
```

---

## 5. Testing

```bash
pytest                              # All tests with coverage
pytest -v --cov-report=term-missing # Verbose with missing lines
pytest tests/test_devices.py        # Specific file
pytest -k "unmount"                 # Pattern match
pytest -m "not slow"                # Skip slow tests
```

**Markers**: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`, `@pytest.mark.hardware`

See `docs/TESTING.md` for comprehensive guide.

---

## 6. Known Issues

### Current Issues

**UI/UX**:
- Keyboard character selection doesn't show on web UI (only OLED)
- Text scrolling speed varies based on text length

**Validation**:
- USB hotplug race conditions: Device may be unplugged between detection and operation

### Performance Notes
- **Button polling**: 20ms | **USB detection**: 2s intervals
- **OLED refresh**: Throttle updates to prevent flickering
- **I2C baud rate**: Set to 1MHz for faster OLED updates (`dtparam=i2c_baudrate=1000000`)

---

## 7. Critical Safety Rules

### ALWAYS Do

1. **Validate device paths** before operations
   ```python
   if not device.startswith("/dev/"):
       raise ValueError("Invalid device path")
   ```

2. **Check source != destination** for clone operations
   ```python
   if source == destination:
       raise ValueError("Cannot clone to same device")
   ```

3. **Verify device is removable** before operations
   ```python
   if device_info["rm"] != "1":
       raise ValueError("Device is not removable")
   ```

4. **Check mount points** before operations
   ```python
   if device_info["mountpoint"] in ["/", "/boot", "/boot/firmware"]:
       raise ValueError("Cannot operate on system partition")
   ```

5. **Show errors to user** on OLED display
6. **Log all operations** for audit trail

### NEVER Do

1. **Never skip error handling** on device operations - no silent failures
2. **Never operate on non-removable devices** (e.g., `/dev/mmcblk0` is the SD card!)
3. **Never assume unmount succeeded** - check return value or use `raise_on_failure=True`
4. **Never perform destructive operations without confirmation**
5. **Never commit without running tests**

---

## 8. Essential Files

| File | Description |
|------|-------------|
| `rpi_usb_cloner/main.py` | Main event loop, entry point |
| `rpi_usb_cloner/app/context.py` | AppContext (runtime state) |
| `rpi_usb_cloner/domain/models.py` | Domain objects (Drive, DiskImage, CloneJob) |
| `rpi_usb_cloner/menu/navigator.py` | Menu navigation logic |
| `rpi_usb_cloner/storage/devices.py` | USB device detection |
| `rpi_usb_cloner/storage/device_lock.py` | Device operation locking |
| `rpi_usb_cloner/storage/clone/operations.py` | Clone operations |
| `rpi_usb_cloner/ui/renderer.py` | OLED rendering |
| `rpi_usb_cloner/web/server.py` | Web server |
| `rpi_usb_cloner/config/settings.py` | Settings management |

---

## 9. Quick Command Reference

```bash
# Development
black . && ruff check --fix . && mypy rpi_usb_cloner  # Format, lint, type check
pytest                                                  # Run tests
pre-commit run --all-files                             # Run all hooks

# Application (on Pi)
sudo -E python3 rpi-usb-cloner.py --debug              # Run with debug logging

# Systemd service
sudo systemctl status rpi-usb-cloner.service
sudo journalctl -u rpi-usb-cloner.service -f           # View logs
```
