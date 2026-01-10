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
- **pytest-mock** (>=3.12.0) - Mocking helpers
- **pytest-timeout** (>=2.2.0) - Test timeout management
- **coverage[toml]** (>=7.3.0) - Code coverage measurement

## Running Tests

### Run Specific Test Files

```bash
# Run device tests only
pytest tests/test_devices.py

# Run settings tests only
pytest tests/test_settings.py

# Run clone tests only
pytest tests/test_clone.py
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
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Exclude slow tests
pytest -m "not slow"

# Run hardware tests (requires actual hardware)
pytest -m hardware
```

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

### Current Coverage Status

As of the latest test run:

- **Overall Coverage**: 7.12%
- **settings.py**: 100% ✅
- **devices.py**: 91.70% ✅
- **mount.py**: 58.87%
- **clone.py**: 27.00%
- **clonezilla.py**: 0.00% ⚠️

**Priority**: Increase coverage for critical modules (clone.py, clonezilla.py)

## Test Organization

### Test Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures and configuration
├── test_devices.py          # Device detection and management tests
├── test_clone.py            # Clone operation tests
├── test_settings.py         # Settings management tests
└── test_mount_security.py   # Mount security tests (existing)
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

### Getting Help

- Check pytest documentation: https://docs.pytest.org/
- Review existing tests for patterns
- Ask questions in GitHub issues

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

**Last Updated**: 2026-01-10
**Test Count**: 183 passing tests
**Coverage**: 7.12% (improving!)
