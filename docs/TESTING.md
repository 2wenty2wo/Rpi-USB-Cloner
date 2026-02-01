# Testing Guide for Rpi-USB-Cloner

This document provides comprehensive instructions for running and writing tests for the Raspberry Pi USB Cloner project.

## Table of Contents

- [Quick Start](#quick-start)
- [Test Infrastructure](#test-infrastructure)
- [Running Tests](#running-tests)
- [Coverage Reports](#coverage-reports)
- [Test Organization](#test-organization)
- [Writing Tests](#writing-tests)
- [CI/CD Integration](#cicd-integration)

## Quick Start

### Install Test Dependencies

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Or install with optional dev dependencies
pip install -e .[dev]
```

### Run All Tests

```bash
# Run all tests with coverage
pytest

# Run with verbose output
pytest -v

# Run with detailed output and coverage report
pytest -v --cov-report=term-missing
```

### View Coverage Report

```bash
# Run tests and generate HTML coverage report
pytest --cov-report=html

# Open the report in your browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Test Infrastructure

### Configuration Files

- **`pyproject.toml`** - Main project configuration with pytest settings
- **`requirements-dev.txt`** - Development and testing dependencies
- **`tests/conftest.py`** - Shared fixtures and test configuration
- **`.coveragerc`** (implicit in pyproject.toml) - Coverage configuration

### Testing Stack

- **pytest** (>=7.4.0) - Test framework
- **pytest-cov** (>=4.1.0) - Coverage plugin
- **pytest-aiohttp** - aiohttp test client fixtures (e.g., `aiohttp_client`)
- **pytest-asyncio** (>=0.23.8) - Async test support/markers
- **pytest-mock** (>=3.12.0) - Mocking helpers
- **pytest-timeout** (>=2.2.0) - Test timeout management
- **coverage[toml]** (>=7.3.0) - Code coverage measurement

## Running Tests

### Run Specific Test Files

```bash
# Run device tests only
pytest tests/test_devices.py

# Run image repository tests
pytest tests/test_image_repo.py

# Run settings tests only
pytest tests/test_settings.py

# Run clone tests only
pytest tests/test_clone.py

# Run system health tests
pytest tests/test_system_health.py

# Run integration clone workflow tests
pytest tests/test_integration_clone_workflows.py

# Run web server/UI tests
pytest tests/test_web_server.py
pytest tests/test_ui_renderer.py tests/test_ui_progress.py tests/test_ui_confirmation.py
```

### Run Specific Test Classes or Methods

```bash
# Run a specific test class
pytest tests/test_devices.py::TestUnmountDevice

# Run a specific test method
pytest tests/test_devices.py::TestUnmountDevice::test_unmount_failure_is_silent

# Run tests matching a pattern
pytest -k "unmount"
```

### Run Tests by Markers

```bash
# Run async tests (pytest-asyncio)
pytest -m asyncio

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Exclude slow tests
pytest -m "not slow"

# Run hardware tests (requires actual hardware)
pytest -m hardware
```

### Async & Web/UI Tests

- **Async tests** use `pytest-asyncio` with `@pytest.mark.asyncio` and
  `pytest_asyncio.fixture` for coroutine fixtures.
- **aiohttp tests** rely on the `aiohttp_client` fixture from `pytest-aiohttp`
  to spin up test servers for web endpoints and WebSocket handlers.
- **UI tests** are logic-focused and use mocked display contexts (Pillow images
  and `unittest.mock`), so they do not require physical OLED hardware.

### Parallel Test Execution

```bash
# Install pytest-xdist for parallel execution
pip install pytest-xdist

# Run tests in parallel (4 workers)
pytest -n 4
```

### Test Output Options

```bash
# Short traceback format
pytest --tb=short

# Only show line of failure
pytest --tb=line

# No traceback
pytest --tb=no

# Stop on first failure
pytest -x

# Stop after N failures
pytest --maxfail=3
```

## Coverage Reports

### Coverage Report Formats

#### Terminal Report

```bash
# Basic coverage report
pytest --cov=rpi_usb_cloner

# With line numbers of missing coverage
pytest --cov=rpi_usb_cloner --cov-report=term-missing

# Show only files with less than 100% coverage
pytest --cov=rpi_usb_cloner --cov-report=term:skip-covered
```

#### HTML Report

```bash
# Generate interactive HTML report
pytest --cov=rpi_usb_cloner --cov-report=html

# Report is generated in htmlcov/index.html
```

#### XML Report (for CI/CD)

```bash
# Generate XML report for CI systems
pytest --cov=rpi_usb_cloner --cov-report=xml

# Report is generated as coverage.xml
```

### Coverage Configuration

Coverage settings are configured in `pyproject.toml`:

- **Source**: `rpi_usb_cloner/` directory
- **Omit**: Test files, caches, site-packages
- **Branch Coverage**: Enabled
- **Minimum Coverage**: No minimum enforced (yet)

### Latest Coverage Status

To view the most recent coverage results:

1. Open the latest **Tests** workflow run in GitHub Actions.
2. Review the **Coverage Summary** step in the job logs for a quick terminal overview.
3. Download the `coverage-reports` artifact to view the HTML report locally:
   - Extract the artifact and open `htmlcov/index.html` in your browser.

If the project is configured with a coverage service (e.g., Codecov), use the badge or service link in `README.md` to view the latest CI coverage results.

## Test Organization

### Test Structure

```
tests/
├── __init__.py
├── conftest.py                   # Shared fixtures and configuration
├── test_actions_drive.py         # Drive action tests
├── test_actions_image.py         # Image action tests
├── test_actions_import.py        # Import action tests
├── test_actions_settings.py      # Settings action tests
├── test_clone.py                 # Clone operation tests
├── test_clone_models.py          # Clone domain model tests
├── test_clone_operations.py      # Clone operations tests
├── test_clone_progress.py        # Clone progress tracking tests
├── test_clone_safety.py          # Clone safety validation tests
├── test_clonezilla_backup.py     # Clonezilla backup tests
├── test_clonezilla_file_utils.py # Clonezilla file utilities tests
├── test_clonezilla_image_discovery.py # Clonezilla image discovery tests
├── test_clonezilla_models.py     # Clonezilla model tests
├── test_clonezilla_partition_table.py # Clonezilla partition table tests
├── test_clonezilla_restore.py    # Clonezilla restore tests
├── test_clonezilla_verification.py # Clonezilla verification tests
├── test_command_runners.py       # Command runner tests
├── test_devices.py               # Device detection and management tests
├── test_discovery.py             # mDNS peer discovery tests
├── test_domain_models.py         # Domain model tests
├── test_erase.py                 # Device erase tests
├── test_exceptions.py            # Custom exception tests
├── test_format.py                # Device format tests
├── test_image_repo.py            # Image repository tests
├── test_imageusb.py              # ImageUSB tests
├── test_integration_clone_workflows.py # Integration clone workflows
├── test_logging.py               # Logging setup and filtering tests
├── test_main.py                  # Main entry point tests
├── test_menu_navigator.py        # Menu navigation logic tests
├── test_mount.py                 # Mount utility tests
├── test_mount_security.py        # Mount security tests
├── test_peer_transfer_client.py  # HTTP transfer client tests
├── test_peer_transfer_server.py  # HTTP transfer server tests
├── test_services_drives.py       # Drive service tests
├── test_settings.py              # Settings management tests
├── test_status_bar.py            # Status bar UI tests
├── test_system_health.py         # System health monitoring tests
├── test_toggle.py                # Toggle switch UI tests
├── test_transfer.py              # Transfer operations tests
├── test_transfer_services.py     # USB-to-USB transfer service tests
├── test_ui_confirmation.py       # Confirmation dialog tests
├── test_ui_display.py            # Display UI tests
├── test_ui_keyboard.py           # Keyboard UI tests
├── test_ui_progress.py           # Progress screen tests
├── test_ui_renderer.py           # UI renderer tests
├── test_validation.py            # Validation helper tests
├── test_verification.py          # Verification workflow tests
├── test_wifi.py                  # Wi-Fi service tests
├── test_wifi_direct.py           # WiFi Direct P2P tests
└── test_web_server.py            # Web server + WebSocket tests
```

### Test File Naming

- Test files: `test_*.py`
- Test classes: `Test*`
- Test functions: `test_*`

### Test Categories

Tests are organized by module and categorized with markers:

- **`@pytest.mark.unit`** - Fast, isolated unit tests
- **`@pytest.mark.integration`** - Tests involving multiple components
- **`@pytest.mark.slow`** - Tests that take >1 second
- **`@pytest.mark.hardware`** - Tests requiring actual hardware

## Writing Tests

### Available Fixtures

Common fixtures are defined in `tests/conftest.py`:

#### Device Fixtures

```python
def test_with_usb_device(mock_usb_device):
    # mock_usb_device provides a complete USB device dict
    assert mock_usb_device["name"] == "sda"

def test_with_system_disk(mock_system_disk):
    # mock_system_disk provides a non-removable system disk
    assert mock_system_disk["rm"] == "0"
```

#### Subprocess Fixtures

```python
def test_successful_command(mock_subprocess_success):
    # Subprocess calls will succeed
    result = subprocess.run(["echo", "test"])
    assert result.returncode == 0

def test_failed_command(mock_subprocess_failure):
    # Subprocess calls will fail with CalledProcessError
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(["false"], check=True)
```

#### File System Fixtures

```python
def test_settings_file(temp_settings_file, sample_settings_data):
    # temp_settings_file is a Path to temporary settings file
    # sample_settings_data is a dict with typical settings
    temp_settings_file.write_text(json.dumps(sample_settings_data))
```

### Mocking Best Practices

#### Mock Subprocess Calls

```python
def test_device_detection(mocker):
    mock_run = mocker.patch("rpi_usb_cloner.storage.devices.run_command")
    mock_result = Mock()
    mock_result.stdout = '{"blockdevices": [...]}'
    mock_run.return_value = mock_result

    devices = get_block_devices()
    assert len(devices) > 0
```

#### Mock File Operations

```python
def test_settings_load(temp_settings_file, monkeypatch):
    # Use monkeypatch to override SETTINGS_PATH
    monkeypatch.setattr("rpi_usb_cloner.config.settings.SETTINGS_PATH", temp_settings_file)

    # Write test data
    temp_settings_file.write_text('{"key": "value"}')

    # Test loading
    load_settings()
    assert get_setting("key") == "value"
```

### Test Patterns

#### Testing Exceptions

```python
def test_invalid_input_raises():
    with pytest.raises(ValueError, match="invalid"):
        process_input("invalid")
```

#### Testing Command Output

```python
def test_command_output(mocker, capsys):
    mocker.patch("subprocess.run")

    run_operation()

    captured = capsys.readouterr()
    assert "Success" in captured.out
```

#### Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("vfat", "FAT32"),
    ("ext4", "ext4"),
    ("ntfs", "NTFS"),
])
def test_filesystem_format(input, expected):
    assert format_filesystem_type(input) == expected
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.8'

      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt

      - name: Run tests with coverage
        run: |
          pytest --cov=rpi_usb_cloner --cov-report=xml

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

### Pre-commit Hook

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Run tests before commit
pytest tests/ -x --tb=short
if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi
```

Make it executable:

```bash
chmod +x .git/hooks/pre-commit
```

## Platform-Specific Testing

### Windows Development

When developing on Windows, some tests will be automatically skipped due to POSIX-specific dependencies:

```bash
# Run tests (some will be skipped on Windows)
pytest

# Expected output on Windows:
# 1278 passed, 25 skipped, 10 failed (platform-specific)
```

**Skipped Tests**:
- Tests requiring `os.geteuid()` (root permission checks)
- Tests requiring `os.statvfs()` (filesystem space checks)
- Tests requiring symlink creation (without admin privileges)

### Linux/macOS (Full Test Suite)

```bash
# Run full test suite (all tests should pass)
pytest

# Expected output on Linux:
# 1303 passed, 0 skipped
```

### CI/CD Environment

The project uses GitHub Actions with Ubuntu for continuous integration:

```yaml
# .github/workflows/tests.yml
- name: Run tests
  run: pytest --cov=rpi_usb_cloner --cov-report=xml
```

## Troubleshooting

### Common Issues

#### Import Errors on Non-Raspberry Pi Systems

**Problem**: `ModuleNotFoundError: No module named 'RPi'`

**Solution**: The test suite includes mocks for hardware dependencies in `conftest.py`. Ensure you're running tests through pytest, not directly with Python:

```bash
# ✅ Correct
pytest tests/test_devices.py

# ❌ Wrong - bypasses conftest.py
python tests/test_devices.py
```

#### Slow Tests

**Problem**: Tests take too long

**Solution**: Skip slow tests during development:

```bash
pytest -m "not slow"
```

#### Coverage Not Working

**Problem**: Coverage report shows 0%

**Solution**: Ensure coverage is measuring the correct source:

```bash
pytest --cov=rpi_usb_cloner --cov-report=term
```

#### Platform-Specific Test Failures

**Problem**: Some tests fail on Windows with `AttributeError: module 'os' has no attribute 'geteuid'`

**Solution**: These failures are expected on Windows. The tests are designed to pass on Linux (the target platform). To skip platform-specific tests:

```bash
# Skip POSIX-only tests on Windows
pytest -k "not root and not posix"
```

### Getting Help

- Check pytest documentation: https://docs.pytest.org/
- Review existing tests for patterns
- Ask questions in GitHub issues

### Formatting

Run Black before submitting changes:

```bash
black .
```

Run all pre-commit hooks (Black, Ruff, mypy) in one pass:

```bash
pre-commit run --all-files
```

### Static Type Checking

Run mypy for the main package:

```bash
mypy rpi_usb_cloner
```

## Future Improvements

### Planned Enhancements

1. **Increase Coverage**: Target 80%+ coverage for critical modules
2. **Integration Tests**: Add end-to-end clone operation tests
3. **Performance Tests**: Add benchmarks for clone operations
4. **Mutation Testing**: Use `mutmut` to verify test quality
5. **CI/CD**: Set up automated testing on pull requests
6. **Code Quality**: Integrate linting (ruff, black, mypy)

### Contributing Tests

When contributing new code:

1. Write tests for new functionality
2. Maintain or improve coverage percentage
3. Use descriptive test names
4. Add docstrings explaining what tests verify
5. Use appropriate markers (@pytest.mark.unit, etc.)
6. Run full test suite before submitting PR

---

**Last Updated**: 2026-02-01

### Current Test Metrics

| Metric | Value |
|--------|-------|
| **Total Test Files** | 50 |
| **Tests Passed** | 1,281 |
| **Tests Failed** | 3 (circular import issue) |
| **Tests Skipped** | 29 (POSIX-only features on Windows) |
| **Overall Coverage** | 45.20% |
| **Total Statements** | 12,975 |
| **Covered Statements** | 6,137 |
| **Branch Coverage** | 4,300 branches, ~55% covered |

### Known Test Limitations

#### Platform-Specific Tests (29 skipped on Windows)

| Feature | Tests Affected | Platform |
|---------|----------------|----------|
| `os.geteuid()` | 14 tests | Linux/macOS only |
| `os.statvfs()` | 7 tests | Linux/macOS only |
| Symlink creation | 1 test | Windows (requires admin) |

#### Code Architecture Issues (3 failing)

| Issue | Tests Affected | Status |
|-------|----------------|--------|
| Circular import in `actions/image_actions.py` | 3 tests | 🔴 Needs codebase refactoring |

**Note**: 
- All non-import tests pass on Linux (the target deployment platform)
- The 3 failing tests are due to a circular import that requires codebase refactoring to resolve
- Windows test skips are expected for platform-specific functionality
