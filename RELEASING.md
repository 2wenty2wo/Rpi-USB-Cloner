# Release Process

This document describes how to create a new release of Rpi-USB-Cloner.

## Automated Release Process

This project uses automated semantic versioning and changelog generation. Here's how it works:

### 1. Conventional Commits

Use [Conventional Commits](https://www.conventionalcommits.org/) format for all commit messages:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: A new feature (minor version bump)
- `fix`: A bug fix (patch version bump)
- `docs`: Documentation only changes
- `style`: Changes that don't affect code meaning (formatting, etc.)
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `perf`: Performance improvement
- `test`: Adding or updating tests
- `chore`: Changes to build process or auxiliary tools
- `BREAKING CHANGE`: Breaking API change (major version bump)

**Examples:**
```bash
git commit -m "feat: add ISO file support for imaging"
git commit -m "fix: resolve mount permission issues"
git commit -m "docs: update installation instructions"
git commit -m "feat!: redesign storage API" # Breaking change
```

### 2. Pull Request Labels

When creating a PR, GitHub Actions will automatically suggest labels based on:
- Changed files (e.g., `documentation` for `.md` files)
- Branch names (e.g., `feature/` → `enhancement`)
- Commit messages

You can also manually add labels:
- `major` / `breaking` → Major version bump (X.0.0)
- `minor` / `feature` / `enhancement` → Minor version bump (0.X.0)
- `patch` / `fix` / `bug` → Patch version bump (0.0.X)

### 3. Release Drafter

As PRs are merged to `main`, the [Release Drafter](https://github.com/release-drafter/release-drafter) workflow automatically:

1. Creates/updates a **draft release** on GitHub
2. Calculates the next version based on PR labels and commit messages
3. Categorizes changes into sections:
   - 🚀 Features
   - 🐛 Bug Fixes
   - 📚 Documentation
   - 🔧 Maintenance
   - etc.
4. Lists contributors

**View the draft release:**
Go to [GitHub Releases](https://github.com/2wenty2wo/Rpi-USB-Cloner/releases) to see the automatically generated draft.

### 4. Publishing a Release

When you're ready to release:

1. **Go to GitHub Releases page**
   ```
   https://github.com/2wenty2wo/Rpi-USB-Cloner/releases
   ```

2. **Edit the draft release**
   - Review the automatically generated release notes
   - Edit the description if needed
   - Verify the version number is correct

3. **Publish the release**
   - Click "Publish release"

4. **Automated actions trigger:**
   - Version file (`rpi_usb_cloner/__version__.py`) is updated
   - CHANGELOG.md is updated with the release notes
   - Changes are committed back to `main`
   - Distribution packages are built
   - (Optional) Package is uploaded to PyPI

### 5. What Gets Updated Automatically

When you publish a release, the workflow automatically:

✅ Updates `rpi_usb_cloner/__version__.py` with the new version
✅ Adds a new entry to `CHANGELOG.md` with release notes
✅ Commits changes back to `main` branch
✅ Builds distribution packages (`.tar.gz` and `.whl`)
✅ Uploads build artifacts to the release

## Manual Release Process (Alternative)

If you need to create a release manually:

1. **Update the version:**
   ```bash
   # Edit rpi_usb_cloner/__version__.py
   echo '__version__ = "1.2.3"' > rpi_usb_cloner/__version__.py
   ```

2. **Update CHANGELOG.md:**
   ```bash
   # Add your changes under a new version heading
   vim CHANGELOG.md
   ```

3. **Commit and tag:**
   ```bash
   git add rpi_usb_cloner/__version__.py CHANGELOG.md
   git commit -m "chore: bump version to 1.2.3"
   git tag v1.2.3
   git push origin main --tags
   ```

4. **Create GitHub release:**
   - Go to GitHub Releases
   - Click "Draft a new release"
   - Select the tag you just created
   - Add release notes
   - Publish

## Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0): Breaking changes, incompatible API changes
- **MINOR** (0.X.0): New features, backwards-compatible
- **PATCH** (0.0.X): Bug fixes, backwards-compatible

## Release Checklist

Before publishing a release:

- [ ] All CI checks are passing
- [ ] CHANGELOG.md is up to date (or will be auto-generated)
- [ ] Documentation reflects any new features or changes
- [ ] Breaking changes are clearly documented
- [ ] Version number follows semantic versioning

## Publishing to PyPI (Future)

When ready to publish to PyPI:

1. **Set up PyPI token:**
   - Create a PyPI account
   - Generate an API token
   - Add `PYPI_TOKEN` to GitHub Secrets

2. **Enable PyPI upload:**
   - Edit `.github/workflows/release.yml`
   - Uncomment the "Publish to PyPI" section

3. **Publish:**
   - The workflow will automatically upload to PyPI on release

## Troubleshooting

**Q: The version didn't update automatically**
- Check that the release workflow completed successfully
- Ensure the tag format is `vX.Y.Z` (with the `v` prefix)

**Q: The draft release isn't being created**
- Verify PRs are being merged to `main` branch
- Check the Release Drafter workflow logs

**Q: How do I force a major version bump?**
- Add the `major` or `breaking` label to PRs
- Use `BREAKING CHANGE:` in commit messages
- Add `!` after the type: `feat!: breaking change`

## Resources

- [Conventional Commits](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [Release Drafter](https://github.com/release-drafter/release-drafter)
