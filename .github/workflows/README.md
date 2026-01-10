# GitHub Actions Workflows

This directory contains automated workflows that run when you push code or create pull requests.

## Current Workflows

### 🧪 Tests (`tests.yml`)

**Purpose**: Automatically run the test suite on every code change

**When it runs**:
- On push to `main`, `master`, or any `claude/*` branch
- On pull requests to `main` or `master`

**What it does**:
1. Sets up a clean Ubuntu environment with Python 3.11
2. Installs test dependencies (pytest, pytest-cov, etc.)
3. Runs all tests in the `tests/` directory
4. Reports pass/fail status

**How to view results**:
1. Go to https://github.com/2wenty2wo/Rpi-USB-Cloner/actions
2. Click on the latest workflow run
3. See detailed logs for each step

## Understanding Workflow Status

| Icon | Status | Meaning |
|------|--------|---------|
| 🟡 ● | Pending | Workflow is queued or running |
| ✅ ✓ | Success | All tests passed! |
| ❌ ✗ | Failure | One or more tests failed |
| 🔴 ⊘ | Cancelled | Workflow was manually stopped |

## Troubleshooting

### Workflow doesn't start
- Check that `.github/workflows/tests.yml` exists
- Ensure the branch name matches the `on:` triggers

### Tests fail in CI but pass locally
- Check Python version (CI uses 3.11)
- Check for missing dependencies in the workflow
- Look for environment-specific issues

### How to skip CI for a commit
Add `[skip ci]` to your commit message:
```bash
git commit -m "docs: Update README [skip ci]"
```

## Next Steps

Once basic testing works, you can:
- Add coverage reporting
- Add code quality checks (linting)
- Add build/deployment steps
- Add status badges to README
