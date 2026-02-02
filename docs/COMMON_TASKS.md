# Common Development Tasks

> **Purpose**: Step-by-step tutorials for common development tasks in the Raspberry Pi USB Cloner codebase.

**Related**: See `CLAUDE.md` for project conventions and `UI_STYLE_GUIDE.md` for display layout patterns.

---

## Table of Contents

1. [Adding a New Menu Item](#adding-a-new-menu-item)
2. [Adding a New Screen Renderer](#adding-a-new-screen-renderer)
3. [Adding a New Storage Operation](#adding-a-new-storage-operation)
4. [Adding a New Setting](#adding-a-new-setting)
5. [Debugging Tips](#debugging-tips)

---

## Adding a New Menu Item

### Step 1: Define menu item in `menu/definitions/`

Edit appropriate file (e.g., `menu/definitions/tools.py`):

```python
from rpi_usb_cloner.menu.model import MenuItem, MenuScreen

def get_tools_menu() -> MenuScreen:
    return MenuScreen(
        title="Tools",
        items=[
            # ... existing items ...
            MenuItem(
                label="New Tool",
                icon="icon_tool",  # Optional, see ui/icons.py
                action="new_tool_action"  # Action name (string)
            ),
        ]
    )
```

### Step 2: Implement action handler in `actions/`

Edit appropriate file (e.g., `actions/tools_actions.py`):

```python
def new_tool_action(context: AppContext) -> None:
    """Handle new tool action."""
    from rpi_usb_cloner.ui.screens.confirmation import render_confirmation

    confirmed = render_confirmation(
        context,
        title="New Tool",
        message="Are you sure?",
        default=False
    )

    if confirmed:
        try:
            result = perform_tool_operation()

            from rpi_usb_cloner.ui.screens.status import render_status
            render_status(context, "Success!", "Operation completed")
        except Exception as e:
            from rpi_usb_cloner.ui.screens.error import render_error_screen
            render_error_screen(context, "Error", str(e), exception=e)
```

### Step 3: Register action in `main.py`

In `rpi_usb_cloner/main.py`, add to action dispatcher:

```python
from rpi_usb_cloner.actions.tools_actions import new_tool_action

ACTION_MAP = {
    # ... existing actions ...
    "new_tool_action": new_tool_action,
}
```

---

## Adding a New Screen Renderer

### Step 1: Create renderer in `ui/screens/`

Create `ui/screens/my_screen.py`:

```python
"""Custom screen renderer."""
from typing import Optional
from PIL import Image, ImageDraw

from rpi_usb_cloner.app.context import AppContext
from rpi_usb_cloner.ui.display import DisplayContext


def render_my_screen(
    app_ctx: AppContext,
    display_ctx: DisplayContext,
    title: str,
    content: str,
    icon: Optional[str] = None
) -> None:
    """Render custom screen."""
    # Create image buffer (128x64, 1-bit monochrome)
    image = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(image)

    # Draw title bar (top 12-16 pixels)
    y_pos = 0
    if icon:
        icon_char = display_ctx.icons.get(icon, "")
        draw.text((2, y_pos), icon_char, font=display_ctx.icon_font, fill=1)
        x_offset = 16
    else:
        x_offset = 2

    draw.text((x_offset, y_pos), title, font=display_ctx.font_small, fill=1)
    y_pos += 14

    # Draw separator line
    draw.line([(0, y_pos), (128, y_pos)], fill=1)
    y_pos += 2

    # Draw content
    draw.text((2, y_pos), content, font=display_ctx.font_small, fill=1)

    # Update display
    display_ctx.device.display(image)
    app_ctx.current_screen_image = image
```

### Step 2: Use in action handler

```python
from rpi_usb_cloner.ui.screens.my_screen import render_my_screen

def my_action(context: AppContext) -> None:
    render_my_screen(
        context,
        context.display,
        title="My Screen",
        content="Hello, World!",
        icon="icon_info"
    )
```

---

## Adding a New Storage Operation

### Step 1: Implement operation in `storage/`

Create `storage/my_operation.py`:

```python
"""Custom storage operation."""
import subprocess
from typing import Callable, Optional

from rpi_usb_cloner.storage.clone.command_runners import run_with_progress


def my_storage_operation(
    device: str,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> None:
    """
    Perform custom storage operation.

    Args:
        device: Device path (e.g., "/dev/sda")
        progress_callback: Optional progress callback(current, total)

    Raises:
        subprocess.CalledProcessError: If operation fails
        ValueError: If device is invalid
    """
    # Validate device
    if not device.startswith("/dev/"):
        raise ValueError(f"Invalid device path: {device}")

    if not os.path.exists(device):
        raise ValueError(f"Device not found: {device}")

    command = ["my_tool", "--device", device]

    if progress_callback:
        run_with_progress(command, progress_callback)
    else:
        subprocess.run(command, check=True, capture_output=True, text=True)
```

### Step 2: Add service layer wrapper (optional)

In `services/drives.py`:

```python
def perform_my_operation(device_name: str) -> None:
    """Perform operation on device (service layer)."""
    from rpi_usb_cloner.storage.my_operation import my_storage_operation
    from rpi_usb_cloner.storage.devices import get_device_by_name

    device = get_device_by_name(device_name)
    if not device:
        raise ValueError(f"Device not found: {device_name}")

    device_path = f"/dev/{device['name']}"
    my_storage_operation(device_path)
```

### Step 3: Write tests

Create `tests/test_my_operation.py`:

```python
"""Tests for custom storage operation."""
import pytest
from unittest.mock import Mock

from rpi_usb_cloner.storage.my_operation import my_storage_operation


class TestMyOperation:
    def test_success(self, mocker):
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = Mock(returncode=0, stdout="Success")

        my_storage_operation("/dev/sda")

        mock_run.assert_called_once()

    def test_invalid_device(self):
        with pytest.raises(ValueError, match="Invalid device path"):
            my_storage_operation("invalid")

    def test_device_not_found(self):
        with pytest.raises(ValueError, match="Device not found"):
            my_storage_operation("/dev/nonexistent")
```

---

## Adding a New Setting

### Step 1: Add default value in `config/settings.py`

```python
DEFAULT_SETTINGS = {
    # ... existing settings ...
    "my_new_setting": "default_value",
}
```

### Step 2: Add getter/setter helpers (optional)

```python
def get_my_setting() -> str:
    return get_setting("my_new_setting", default="default_value")

def set_my_setting(value: str) -> None:
    set_setting("my_new_setting", value)
    save_settings()
```

### Step 3: Add menu item

In `menu/definitions/settings.py`:

```python
MenuItem(
    label=f"My Setting: {get_my_setting()}",
    action="change_my_setting"
)
```

### Step 4: Implement action handler

In `actions/settings_actions.py`:

```python
def change_my_setting(context: AppContext) -> None:
    from rpi_usb_cloner.ui.keyboard import render_keyboard

    new_value = render_keyboard(
        context,
        title="My Setting",
        initial_value=get_my_setting()
    )

    if new_value:
        set_my_setting(new_value)

        from rpi_usb_cloner.ui.screens.status import render_status
        render_status(context, "Saved", f"My Setting: {new_value}")
```

---

## Debugging Tips

### Enable Debug Logging

```bash
sudo -E python3 rpi-usb-cloner.py --debug
```

### View Web UI Debug Console

```
http://<pi-ip>:8000/?debug=1
```

Or persist in browser console:

```javascript
localStorage.setItem("rpiUsbClonerDebug", "1")  // Enable
localStorage.removeItem("rpiUsbClonerDebug")    // Disable
```

### Access Logs on Raspberry Pi

```bash
# If running as systemd service
sudo journalctl -u rpi-usb-cloner.service -f

# If running in terminal - logs appear in stdout/stderr
```

### Common Debug Points

**Device Detection**:
```python
from rpi_usb_cloner.storage.devices import list_usb_disks
devices = list_usb_disks()
print(f"Found {len(devices)} devices: {devices}")
```

**Menu Navigation**:
```python
from rpi_usb_cloner.menu.navigator import MenuNavigator
print(f"Current menu: {navigator.current_screen.title}")
print(f"Menu stack depth: {len(navigator.menu_stack)}")
```

**Settings**:
```python
from rpi_usb_cloner.config.settings import get_all_settings
print(f"All settings: {get_all_settings()}")
```
