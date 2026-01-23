# Circular Import Issue Blocking Actions Testing

**Date**: 2026-01-23
**Priority**: HIGH - Blocks testing of critical data safety operations

---

## Problem

Attempting to test `rpi_usb_cloner.actions.drive_actions` and `rpi_usb_cloner.actions.image_actions` triggers a circular import error:

```
AttributeError: partially initialized module 'rpi_usb_cloner.ui.menus' has no attribute 'BUTTON_POLL_DELAY'
(most likely due to a circular import)
```

## Import Cycle

The circular dependency chain is:

1. `actions/drive_actions.py` → imports `ui.menus`
2. `ui/menus.py` → imports `menu.model`
3. `menu/__init__.py` → imports `menu.definitions`
4. `menu/definitions/drives.py` → imports `menu.actions`
5. `menu/actions/drives.py` → imports `ui.screens`
6. `ui/screens/status.py` → imports `ui.menus` (**CYCLE**)

Additionally, there appears to be confusion between two separate `actions` modules:
- `rpi_usb_cloner/actions/` (newer location)
- `rpi_usb_cloner/menu/actions/` (older location)

Both exist and reference each other, creating further entanglement.

## Impact

**CRITICAL**: Cannot write tests for:
- `actions/drive_actions.py` (641 LOC, 0% coverage) - Copy, erase, format, unmount operations
- `actions/image_actions.py` (682 LOC, 0% coverage) - Backup, restore, verify operations

These modules perform **destructive data operations** and desperately need test coverage to prevent data loss bugs.

## Attempted Tests (Blocked)

The following test files were written but cannot be imported due to the circular dependency:

1. **`test_drive_actions.py`** (removed)
   - Tests for clone validation (source ≠ destination)
   - Confirmation dialogs for destructive operations
   - Root permission checks
   - Error handling and user notifications
   - Device validation

2. **`test_image_actions.py`** (removed)
   - Clonezilla backup/restore validation
   - Image name validation (alphanumeric only)
   - Repository drive protection (prevent backing up repo drive)
   - Partition mode selection
   - Destructive action confirmations

These tests are **essential for data safety** but blocked by the architectural issue.

## Solutions

### Option 1: Break the Circular Import (Recommended)

**Move `BUTTON_POLL_DELAY` constant**:
- Extract constants from `ui/menus.py` to a separate `ui/constants.py` module
- Update imports in `ui/screens/status.py` to use `ui.constants`

**Benefits**:
- Minimal code changes
- Preserves existing architecture
- Enables testing of actions modules

**Files to modify**:
```python
# Create: ui/constants.py
BUTTON_POLL_DELAY = 0.05

# Update: ui/screens/status.py
from rpi_usb_cloner.ui import constants
poll_delay: float = constants.BUTTON_POLL_DELAY

# Update: ui/menus.py
from .constants import BUTTON_POLL_DELAY
```

### Option 2: Consolidate Actions Modules

**Merge `menu/actions/` into `actions/`**:
- Eliminates duplicate `actions` namespaces
- Clarifies module responsibilities
- May require extensive refactoring

**Benefits**:
- Cleaner architecture long-term
- Single source of truth for actions

**Risks**:
- Large refactoring effort
- Potential for breaking changes

### Option 3: Lazy Imports

**Use function-level imports in problematic modules**:

```python
# Instead of:
from rpi_usb_cloner.ui import menus

# Use:
def my_function():
    from rpi_usb_cloner.ui import menus
    # Use menus here
```

**Benefits**:
- Quick workaround
- Minimal changes

**Drawbacks**:
- Hides the problem instead of fixing it
- Performance overhead
- Harder to maintain

## Recommended Action Plan

1. **Immediate** (1 hour):
   - Implement Option 1: Extract `BUTTON_POLL_DELAY` to `ui/constants.py`
   - Verify circular import is resolved
   - Re-add test files for drive_actions and image_actions

2. **Short-term** (1 week):
   - Run newly enabled tests
   - Achieve >80% coverage on actions modules
   - Document any additional circular dependencies discovered

3. **Long-term** (1 month):
   - Consider Option 2: Consolidate actions modules
   - Refactor to prevent future circular imports
   - Add architectural tests to detect circular dependencies

## Testing Workaround (Current)

Until the circular import is fixed, tests for actions modules **cannot be written**. The following tests ARE working:

✅ **`test_menu_navigator.py`** (32 tests, 100% pass)
- Menu navigation logic
- Submenu handling
- Scroll offset calculations
- Dynamic item providers

All other test files remain functional (no circular import issues).

## References

- **TEST_COVERAGE_ANALYSIS.md** - Identifies actions as Priority 1 for testing (HIGH RISK)
- **CLAUDE.md** - Documents architecture and module structure
- Original test files (removed due to import error):
  - Had been committed with comprehensive test cases
  - Need to be restored once circular import is resolved

---

**Next Steps**: Fix circular import per Option 1, then restore comprehensive actions testing.
