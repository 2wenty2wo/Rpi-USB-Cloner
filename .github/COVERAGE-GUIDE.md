# Coverage Reporting Guide

## 🎯 What is Coverage?

**Code coverage** measures what percentage of your code is executed during tests. It helps you find:
- ✅ Which code is tested
- ⚠️ Which code is NOT tested
- 🎯 Where to add more tests

## 📊 Reading Coverage Reports

### Coverage Percentage Meaning

| Coverage | Color | Meaning |
|----------|-------|---------|
| 90-100% | 🟢 Green | Excellent! Most code tested |
| 70-89% | 🟡 Yellow | Good, but room to improve |
| 50-69% | 🟠 Orange | Fair, many gaps |
| 0-49% | 🔴 Red | Poor, needs more tests |

### Example Coverage Output

```
Name                              Stmts   Miss  Cover   Missing
───────────────────────────────────────────────────────────────
config/settings.py                   35      0   100%
storage/devices.py                  205     17    92%   100-103, 205-206
storage/clone.py                    616    450    27%   278-367, 371-387
───────────────────────────────────────────────────────────────
TOTAL                              7167   6637     7%
```

**Understanding the columns:**
- **Stmts**: Total lines of code
- **Miss**: Lines NOT covered by tests
- **Cover**: Percentage tested
- **Missing**: Specific line numbers without tests

## 👀 Viewing Coverage in CI

### Step 1: Go to GitHub Actions
https://github.com/2wenty2wo/Rpi-USB-Cloner/actions

### Step 2: Click on Latest Workflow Run
Look for "feat: Add coverage reporting to CI/CD workflow"

### Step 3: Expand "Coverage Summary" Step
You'll see:
```
📊 Coverage Report:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
rpi_usb_cloner/config/settings.py           100.00%
rpi_usb_cloner/services/drives.py           100.00%
rpi_usb_cloner/storage/clone/models.py      100.00%
rpi_usb_cloner/storage/clone/operations.py   96.13%
rpi_usb_cloner/storage/devices.py            91.70%
rpi_usb_cloner/storage/clone/command_runners.py  90.46%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOTAL                                        22.50%
```

### Step 4: Download Detailed HTML Report
1. Scroll to bottom of workflow run page
2. Find "Artifacts" section
3. Click "coverage-reports" to download
4. Extract the ZIP file
5. Open `htmlcov/index.html` in your browser

## 🌐 HTML Coverage Report (Interactive!)

The HTML report shows:
- **Red lines** = Not covered by tests ❌
- **Green lines** = Covered by tests ✅
- **Yellow lines** = Partially covered
- **Click any file** to see line-by-line coverage

### Example: Finding Untested Code

1. Open `htmlcov/index.html`
2. Click on `storage/clone.py` (27% coverage)
3. Red highlighted lines = Need tests!
4. See exactly which functions are untested

## 📈 Coverage Badges in README

Your README now shows:

```markdown
![Tests](https://github.com/.../workflows/tests.yml/badge.svg)
![Coverage](https://img.shields.io/badge/coverage-22.50%25-yellow)
![Tests Passing](https://img.shields.io/badge/tests-608%20passing-brightgreen)
```

These badges:
- Show at a glance if tests pass
- Display current coverage %
- Update automatically on each commit

## 🎯 Using Coverage to Improve Tests

### Workflow for Increasing Coverage

1. **Run tests with coverage locally:**
   ```bash
   pytest --cov=rpi_usb_cloner --cov-report=html
   open htmlcov/index.html
   ```

2. **Find red lines** (untested code)

3. **Write tests** for those lines

4. **Run tests again** to see coverage improve

5. **Commit and push** - CI shows new coverage %

### Example: Targeting Higher Coverage

Current status:
```
settings.py               100% ✅ (Done!)
services/drives.py        100% ✅ (Done!)
clone/models.py           100% ✅ (Done!)
clone/operations.py        96% ✅ (Excellent!)
clone/verification.py      93% ✅ (Great!)
clone/erase.py             92% ✅ (Great!)
devices.py                 92% ✅ (Great!)
clone/command_runners.py   90% ✅ (Great!)
clonezilla/partition_table.py  62% 🟡 (Good start)
mount.py                   59% 🟡 (Good start)
actions/                    0% 🔴 (Not tested)
ui/                         0% 🔴 (Not tested)
```

**Goal**: Get UI and action modules tested

**Strategy**:
1. Focus on testable logic in UI/actions
2. Mock hardware dependencies (OLED, GPIO)
3. Write tests for:
   - Action handlers (drive actions, image actions)
   - Menu navigation logic
   - Error handling in UI code

## 📊 Coverage Trends

Track coverage over time:

| Date | Coverage | Change | Tests |
|------|----------|--------|-------|
| Jan 11 | 22.50% | +15.38% | 608 |
| Jan 10 | 7.12% | +7.12% | 183 |
| Jan 9 | 0.00% | - | 0 |

**Goal**: Coverage tripled in 2 days! Continue increasing by 1-2% each week!

## ⚙️ Coverage Configuration

Coverage settings in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["rpi_usb_cloner"]  # What to measure
omit = [
    "*/tests/*",              # Don't measure test files
    "*/__pycache__/*",        # Ignore cache
]
branch = true                # Measure branch coverage

[tool.coverage.report]
precision = 2                # Show 2 decimal places
show_missing = true          # Show missing lines
exclude_lines = [
    "pragma: no cover",      # Skip marked lines
    "def __repr__",          # Skip repr methods
    "if TYPE_CHECKING:",     # Skip type checking blocks
]
```

## 🚀 Advanced: Branch Coverage

**Line coverage** = "Was this line executed?"
**Branch coverage** = "Were all if/else branches taken?"

Example:
```python
def check_value(x):
    if x > 0:        # Line executed ✓
        return "positive"  # Branch 1
    else:
        return "negative"  # Branch 2
```

For 100% branch coverage, you need tests where:
- `x > 0` is True
- `x > 0` is False

Our tests measure branch coverage automatically!

## 📝 Coverage Best Practices

### DO:
- ✅ Aim for 80%+ coverage on critical code
- ✅ Test error paths (what happens when things fail?)
- ✅ Use coverage to find untested edge cases
- ✅ Review coverage reports on every PR

### DON'T:
- ❌ Don't chase 100% coverage everywhere (diminishing returns)
- ❌ Don't write tests just to increase coverage
- ❌ Don't skip testing edge cases
- ❌ Don't ignore coverage drops in PRs

### Sweet Spots by Module Type

| Module Type | Target Coverage |
|-------------|-----------------|
| Core logic (clone.py) | 80-90% |
| Data handling (devices.py) | 90-100% |
| Configuration (settings.py) | 100% |
| UI code (display.py) | 50-70% |
| Hardware interfaces (gpio.py) | 30-50% |

## 🔍 Debugging Low Coverage

### "Why is coverage so low?"

1. **Large untested files**
   - Solution: Add tests incrementally

2. **Hardware-dependent code**
   - Solution: Mock hardware interactions

3. **UI/Display code**
   - Solution: Test logic separately from rendering

4. **Legacy code**
   - Solution: Add tests when you modify it

### "Coverage went down after my change!"

1. **Added new code without tests**
   - Add tests for new functionality

2. **Deleted tests**
   - Restore necessary tests

3. **Total lines increased more than tested lines**
   - Normal! Just add tests for new code

## 🎓 Next Steps

1. **Review current coverage** in GitHub Actions
2. **Download HTML report** and explore
3. **Pick one file** with low coverage
4. **Write 5 new tests** for that file
5. **Push changes** and watch coverage increase!

## 📚 Resources

- [Coverage.py Documentation](https://coverage.readthedocs.io/)
- [Testing Guide](../TESTING.md)
- [Pytest Coverage Plugin](https://pytest-cov.readthedocs.io/)

---

**Remember**: Coverage is a tool, not a goal. The goal is **reliable, well-tested code**! 🎯

**Current Status**: 22.50% coverage, 608 tests passing ✅
