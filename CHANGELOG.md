# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GitHub Actions CI/CD infrastructure with automated testing
- Code quality checks with ruff, black, isort, and mypy
- Security scanning with safety and bandit
- Automated release management with Release Drafter
- Semantic versioning with automatic version bumping
- Changelog generation from release notes
- Issue and PR templates for better contribution workflow
- Dependabot for automated dependency updates
- Pre-commit hooks configuration

### Changed
- Applied black code formatting to entire codebase
- Fixed 209+ linting issues across the project
- Updated workflows to handle errors gracefully

### Fixed
- CI workflow system dependencies for Ubuntu
- Security check failures with proper error handling
- Code quality checks now provide feedback without blocking builds

## [1.0.0] - Initial Release

### Added
- USB drive cloning functionality
- Clonezilla image backup and restore support
- OLED display interface (SSD1306/SH1106)
- Drive management (format, erase, info)
- Settings management
- WiFi configuration
- Screensaver functionality
- Security-hardened mount/unmount operations
- Comprehensive test suite for security features

[Unreleased]: https://github.com/2wenty2wo/Rpi-USB-Cloner/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/2wenty2wo/Rpi-USB-Cloner/releases/tag/v1.0.0
