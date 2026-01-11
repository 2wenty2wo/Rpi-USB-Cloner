# Contributing to Rpi-USB-Cloner

Thanks for your interest in contributing! This document summarizes the existing development workflow and expectations based on the project documentation.

## Setup Requirements

- **Python:** 3.8+ (see badge and CI configuration in `README.md`).
- **Dependencies:**
  - Runtime dependencies:
    ```bash
    pip install -r requirements.txt
    ```
  - Development/testing dependencies:
    ```bash
    pip install -r requirements-dev.txt
    ```

> Tip: The README recommends using a virtual environment (e.g., `python3 -m venv .venv`).

## Running Tests

Follow the full testing guide in `TESTING.md`, which covers pytest commands, markers, coverage reports, and troubleshooting.

## Code Style and Formatting

Project guidance in `TESTING.md` recommends:

- Run **Black** before submitting changes:
  ```bash
  black .
  ```
- Optionally run **pre-commit** hooks (Black, Ruff, mypy):
  ```bash
  pre-commit run --all-files
  ```
- Run **mypy** for type checks:
  ```bash
  mypy rpi_usb_cloner
  ```

If you do not run these locally, expect CI or maintainers to request them during review.

## Reporting Issues

Please open a GitHub issue and include:

- A clear description of the problem and expected behavior.
- Steps to reproduce.
- Logs or screenshots when applicable.
- Hardware and OS details (Raspberry Pi model, OS version, attached peripherals).

## Submitting Pull Requests

1. Fork the repository and create a feature branch.
2. Make your changes with tests.
3. Run the relevant formatting and checks (see **Code Style and Formatting**).
4. Open a pull request with a clear description of the change and any testing performed.

## Branching and Commit Messages

There are no explicit branching or commit message conventions documented. Use clear, descriptive branch names and commit messages.
